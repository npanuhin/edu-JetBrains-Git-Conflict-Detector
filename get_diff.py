import subprocess
import requests


LOG = False


def run_cmd(cmd: list[str] | tuple[str, ...], error_message: str = '') -> str | None:
    try:
        return subprocess.run(cmd, capture_output=True, check=True, text=True).stdout

    except subprocess.CalledProcessError as e:
        if error_message:
            print(error_message)
        if isinstance(e.cmd, (list, tuple)):
            print(f'"{" ".join(e.cmd)}"', end=' ')
        else:
            print(f'"{e.cmd}"', end=' ')
        print(f'failed with exit code {e.returncode}')
        print(e.stderr)
        return None


def get_merge_base(branch_a: str, branch_b: str, repo_path: str) -> str | None:
    if (result := run_cmd(
        ('git', '-C', repo_path, 'merge-base', branch_a, branch_b),
        f'Could not find merge base for {branch_a} and {branch_b}'
    )) is None:
        return None
    return result.strip()


def get_modified_files_local(branch_local: str, merge_base_commit: str, repo_path: str) -> list[str] | None:
    if (result := run_cmd(
        ('git', '-C', repo_path, 'diff', '--name-only', merge_base_commit, branch_local)
    )) is None:
        return None
    return list(filter(None, map(str.strip, result.splitlines())))


def get_modified_files_remote(
    owner: str, repo: str, branch_remote: str, merge_base_commit: str, access_token: str
) -> list[str] | None:

    headers = {'Authorization': f'token {access_token}'}

    response = requests.get(
        f'https://api.github.com/repos/{owner}/{repo}/branches/{branch_remote.split("/")[1]}',
        headers=headers
    )
    if response.status_code != 200:
        print(f'Failed to get branch info for rmeote branch {branch_remote}')
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
        # print(f'Failed to get branch info for rmeote branch {branch_remote}')
        print(response.text)
        return None

    data = response.json()
    assert data['status'] == 'ahead'

    return [item['filename'] for item in data['files']]


def main(
    branch_a: str,
    branch_b: str,
    owner: str,
    repo: str,
    access_token: str,
    local_repo_path: str = '.',
):
    merge_base_commit = get_merge_base(branch_a, branch_b, local_repo_path)
    if merge_base_commit is None:
        return
    if LOG:
        print(f'Found merge base commit: {merge_base_commit}')

    branch_a_modified_files = get_modified_files_remote(owner, repo, branch_a, merge_base_commit, access_token)
    if branch_a_modified_files is None:
        return
    print(f'Files modified on "{branch_a}": {branch_a_modified_files}')

    branch_b_modified_files = get_modified_files_local(branch_b, merge_base_commit, local_repo_path)
    if branch_b_modified_files is None:
        return
    print(f'Files modified on "{branch_b}": {branch_b_modified_files}')

    # conflicting_files = local_changes & remote_changes
    # return conflicting_files


if __name__ == '__main__':
    branch_a = 'origin/branchA'
    branch_b = 'branchB'
    owner = 'npanuhin'
    repo = 'edu-JetBrains-Git-Conflict-Detector'
    access_token = ''

    main(branch_a, branch_b, owner, repo, access_token)
