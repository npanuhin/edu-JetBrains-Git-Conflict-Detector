import argparse
import subprocess
import requests


LOG = True


GITHUB_API_STATUS_MAPPING = {
    'added',
    'removed',
    'modified',
    'renamed',
    'copied',
    'changed',
    'unchanged'
}


def run_cmd(cmd: list[str] | tuple[str, ...], error_message: str = '') -> str | None:
    try:
        return subprocess.run(cmd, capture_output=True, check=True, text=True).stdout.strip()

    except subprocess.CalledProcessError as e:
        if error_message:
            print(error_message)
        print(f'Command "{" ".join(e.cmd)}" failed with exit code {e.returncode}')
        print(e.stderr)
        return None


def get_merge_base(branch_a: str, branch_b: str, repo_path: str) -> str | None:
    return run_cmd(
        ('git', '-C', repo_path, 'merge-base', branch_a, branch_b),
        f'Could not find merge base for {branch_a} and {branch_b}'
    )


def get_modified_files_local(branch_local: str, merge_base_commit: str, repo_path: str) -> dict[str, str] | None:
    cmd_output = run_cmd(
        ('git', '-C', repo_path, 'diff', '--name-status', merge_base_commit, branch_local)
    )
    if cmd_output is None:
        return None

    modified_files = {}

    for line in cmd_output.splitlines():
        if line.strip():
            status, filename = line.split('\t')
            modified_files[filename] = status

    return modified_files


def get_modified_files_remote(
    owner: str, repo: str, branch_remote: str, merge_base_commit: str, access_token: str
) -> dict[str, str] | None:
    headers = {'Authorization': f'token {access_token}'}
    branch_name = branch_remote.split('/')[-1]

    response = requests.get(
        f'https://api.github.com/repos/{owner}/{repo}/branches/{branch_name}',
        headers=headers
    )
    if response.status_code != 200:
        print(f'Failed to get branch info for remote branch {branch_remote}')
        print(response.text)
        return None

    last_commit = response.json()['commit']['sha']
    if LOG:
        print(f'Last commit on remote branch {branch_remote}: {last_commit}')

    response = requests.get(
        f'https://api.github.com/repos/{owner}/{repo}/compare/{merge_base_commit}...{last_commit}',
        headers=headers
    )
    if response.status_code != 200:
        print(f'Failed to get comparison info for commits {merge_base_commit}...{last_commit}')
        print(response.text)
        return None

    response_data = response.json()
    assert response_data['status'] == 'ahead'

    return {item['filename']: item['status'] for item in response_data['files']}


def main():
    parser = argparse.ArgumentParser(
        description='Detect files modified in both local and remote branches independently.'
    )
    parser.add_argument('branch_a', help='Remote branch (e.g., origin/branchA)')
    parser.add_argument('branch_b', help='Local branch (e.g., branchB)')
    parser.add_argument('owner', help='GitHub repository owner')
    parser.add_argument('repo', help='GitHub repository name')
    parser.add_argument('access_token', help='GitHub personal access token')
    parser.add_argument('--repo-path', default='.', help='Local repository path (default: current directory)')
    args = parser.parse_args()

    merge_base_commit = get_merge_base(args.branch_a, args.branch_b, args.repo_path)
    if merge_base_commit is None:
        return
    if LOG:
        print(f'Found merge base commit: {merge_base_commit}')

    branch_a_modified_files = get_modified_files_remote(
        args.owner, args.repo, args.branch_a, merge_base_commit, args.access_token
    )
    if branch_a_modified_files is None:
        return
    branch_b_modified_files = get_modified_files_local(args.branch_b, merge_base_commit, args.repo_path)
    if branch_b_modified_files is None:
        return

    if LOG:
        print('--- Modified Files Report ---')
        print(f'Files modified in remote branch "{args.branch_a}":')
        for filename, status in branch_a_modified_files.items():
            print(f'{status}\t{filename}')
        print(f'Files modified in local branch "{args.branch_b}":')
        for filename, status in branch_b_modified_files.items():
            print(f'{status}\t{filename}')
        print()

    # conflicting_files = branch_a_modified_files & branch_b_modified_files
    # print('--- Potential Conflicts ---')
    # if conflicting_files:
    #     print(f'The following files were modified independently in both branches: {sorted(conflicting_files)}')
    # else:
    #     print('No conflicting files found.')


if __name__ == '__main__':
    main()
