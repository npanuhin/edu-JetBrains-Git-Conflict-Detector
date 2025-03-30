from dataclasses import dataclass
from enum import Enum
import subprocess
import argparse

import requests


LOG = False


class FileStatus(Enum):
    ADDED = 'added'
    REMOVED = 'removed'
    MODIFIED = 'modified'
    RENAMED = 'renamed'
    COPIED = 'copied'
    CHANGED = 'changed'
    UNCHANGED = 'unchanged'

    @classmethod
    def from_git(cls, status: str) -> 'FileStatus':
        status = status[0]
        if status == 'X':
            raise ValueError('Encountered git status status "X", which seems to indicate a bug in git')
        if status not in _GIT_MAPPING:
            raise ValueError(f'Unknown git status status: {status}')
        return _GIT_MAPPING[status]

    @classmethod
    def from_github(cls, status: str) -> 'FileStatus':
        try:
            return cls(status)
        except ValueError:
            raise ValueError(f'Unknown GitHub API file status: {status}')


_GIT_MAPPING = {
    'A': FileStatus.ADDED,
    'D': FileStatus.REMOVED,
    'M': FileStatus.MODIFIED,
    'R': FileStatus.RENAMED,
    'C': FileStatus.COPIED,
    'T': FileStatus.CHANGED,
    'U': FileStatus.UNCHANGED,
}


@dataclass
class FileChange:
    status: FileStatus
    path: str
    old_path: str | None = None

    @classmethod
    def from_git(cls, raw_status: str, paths: list[str]) -> 'FileChange':
        status = FileStatus.from_git(raw_status)

        if status in (FileStatus.RENAMED, FileStatus.COPIED):
            if len(paths) != 2:
                raise ValueError(f'Expected two paths for status "{status}", got "{paths}"')
            return cls(status=status, old_path=paths[0], path=paths[1])

        elif len(paths) != 1:
            raise ValueError(f'Expected one path for status "{status}", got "{paths}"')

        return cls(status=status, path=paths[0])

    @classmethod
    def from_github(cls, raw_status: str, filename: str, previous_filename: str | None = None) -> 'FileChange':
        status = FileStatus.from_github(raw_status)

        if (previous_filename is not None) ^ (status in (FileStatus.RENAMED, FileStatus.COPIED)):
            raise ValueError(
                f'While handling file "{filename}"\n'
                f'Expected {"" if previous_filename is None else "no"} previous filename for status "{status.value}"'
            )

        return cls(status=status, old_path=previous_filename, path=filename)

    def __str__(self) -> str:
        max_status_length = max(len(status.value) for status in FileStatus)
        return (
            f'{self.status.value.ljust(max_status_length).capitalize()}  '
            f'{self.old_path + " -> " if self.old_path else ""}'
            f'{self.path}'
        )


def run_cmd(*cmd: str) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, check=True, text=True).stdout.strip()

    except FileNotFoundError as e:
        raise RuntimeError(f'Command "{cmd[0]}" not found on local machine: {e}')

    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f'Command "{" ".join(e.cmd)}" failed with exit code {e.returncode}\n'
            f'Command line error:\n'
            f'{e.stderr}'
        )


def get_merge_base(branch_a: str, branch_b: str, repo_path: str) -> str:
    try:
        return run_cmd('git', '-C', repo_path, 'merge-base', branch_a, branch_b)
    except RuntimeError as e:
        raise RuntimeError(f'Could not find merge base for "{branch_a}" and "{branch_b}"\n{e}')


def get_modified_files_local(branch_local: str, merge_base_commit: str, repo_path: str) -> list[FileChange]:
    try:
        cmd_output = run_cmd('git', '-C', repo_path, 'diff', '--name-status', merge_base_commit, branch_local)
    except RuntimeError as e:
        raise RuntimeError(f'Failed to get `git diff` output for branch "{branch_local}"\n{e}')

    modified_files = []

    try:
        for line in cmd_output.splitlines():
            if line.strip():
                status, filename = line.split('\t', 1)
                modified_files.append(FileChange.from_git(status, filename.split('\t')))
    except ValueError as e:
        raise RuntimeError(f'Failed to parse `git diff` output for branch "{branch_local}"\n{e}')

    return modified_files


def get_modified_files_remote(
    owner: str, repo: str, branch_remote: str, merge_base_commit: str, access_token: str
) -> list[FileChange]:
    headers = {'Authorization': f'token {access_token}'} if access_token else {}
    branch_name = branch_remote.split('/')[-1]

    response = requests.get(
        f'https://api.github.com/repos/{owner}/{repo}/branches/{branch_name}',
        headers=headers
    )
    if response.status_code != 200:
        raise RuntimeError(f'Failed to get branch info for remote branch "{branch_remote}"\n{response.text}')

    last_commit = response.json()['commit']['sha']
    if LOG:
        print(f'Last commit on remote branch {branch_remote}: {last_commit}')

    response = requests.get(
        f'https://api.github.com/repos/{owner}/{repo}/compare/{merge_base_commit}...{last_commit}',
        headers=headers
    )
    if response.status_code != 200:
        raise RuntimeError(
            f'Failed to get comparison info for commits "{merge_base_commit}...{last_commit}"\n{response.text}'
        )

    response_data = response.json()
    assert response_data['status'] == 'ahead'

    modified_files = []

    try:
        for item in response_data['files']:
            modified_files.append(
                FileChange.from_github(item['status'], item['filename'], item.get('previous_filename'))
            )
    except ValueError as e:
        raise RuntimeError(f'Failed to parse GitHub API response for remote branch "{branch_remote}"\n{e}')

    return modified_files


def main():
    parser = argparse.ArgumentParser(
        description='Detect files modified in both local and remote branches independently.'
    )
    parser.add_argument('branch_b', help='Local branch, which will be checked for conflicts')
    parser.add_argument('branch_a', help='Remote branch, which we compare against')
    parser.add_argument('owner', help='GitHub repository owner')
    parser.add_argument('repo', help='GitHub repository name')
    parser.add_argument(
        '--access_token', default='',
        help='GitHub personal access token (only public repositories access by default)'
    )
    parser.add_argument(
        '--repo_path', default='.',
        help='Local repository path (default: current directory)'
    )
    args = parser.parse_args()

    if '/' in args.branch_b:
        print('Local branch names should not contain "/" character')
        return

    if '/' not in args.branch_a:
        args.branch_a = f'origin/{args.branch_a}'

    try:
        merge_base_commit = get_merge_base(args.branch_a, args.branch_b, args.repo_path)
    except RuntimeError as e:
        print(f'Failed to find merge base commit\n{e}')
        return
    if LOG:
        print(f'Found merge base commit: {merge_base_commit}')

    try:
        branch_a_modified_files = get_modified_files_remote(
            args.owner, args.repo, args.branch_a, merge_base_commit, args.access_token
        )
    except RuntimeError as e:
        print(f'Failed to get modified files for remote branch "{args.branch_a}"\n{e}')
        return

    try:
        branch_b_modified_files = get_modified_files_local(args.branch_b, merge_base_commit, args.repo_path)
    except RuntimeError as e:
        print(f'Failed to get modified files for local branch "{args.branch_b}"\n{e}')
        return

    if LOG:
        print(
            f'\n--- Modified Files Report ---\n'
            f'\n>> Files modified in remote branch "{args.branch_a}":\n'
            f'{"\n".join(map(str, branch_a_modified_files))}\n'
            f'\n>> Files modified in local branch "{args.branch_b}":\n'
            f'{"\n".join(map(str, branch_b_modified_files))}'
        )

    branch_a_by_file = {file_change.path: file_change for file_change in branch_a_modified_files}

    print(f'{"\n" if LOG else ""}--- Potential Conflicts ---\n')

    max_branch_name_length = max(len(args.branch_a), len(args.branch_b)) + 1
    for change in branch_b_modified_files:
        if change.path in branch_a_by_file:
            print(
                f'Conflict: {change.path}\n'
                f'  {(args.branch_a + ":").ljust(max_branch_name_length)} {branch_a_by_file[change.path]}\n'
                f'  {(args.branch_b + ":").ljust(max_branch_name_length)} {change}\n',
            )


if __name__ == '__main__':
    main()
