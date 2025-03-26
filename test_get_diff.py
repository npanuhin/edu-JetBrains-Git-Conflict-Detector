from unittest.mock import patch, MagicMock
# import subprocess
import pytest

from get_diff import run_cmd, get_merge_base, get_modified_files_local, get_modified_files_remote, \
    FileChange, FileStatus


def test_run_cmd_success():
    result = run_cmd('git', '--version')
    assert result.startswith('git version')


def test_run_cmd_failure():
    with pytest.raises(RuntimeError):
        run_cmd('git', 'smth')


def test_file_change_from_git():
    change1 = FileChange.from_git('M', ['file.txt'])
    assert change1.status == FileStatus.MODIFIED
    assert change1.path == 'file.txt'

    with pytest.raises(ValueError):
        FileChange.from_git('M', [])

    with pytest.raises(ValueError):
        FileChange.from_git('R', ['old.txt', 'new.txt', 'extra.txt'])


def test_file_change_from_github():
    result = FileChange.from_github('added', 'file.txt')
    assert result.status == FileStatus.ADDED
    assert result.path == 'file.txt'

    with pytest.raises(ValueError):
        FileChange.from_github('added', 'file.txt', 'another_file.txt')

    with pytest.raises(ValueError):
        FileChange.from_github('renamed', 'file.txt', None)


@patch('get_diff.run_cmd')
def test_get_merge_base(mock_run_cmd):
    mock_run_cmd.return_value = 'some_commit_hash'
    assert get_merge_base('branchA', 'branchB', '.') == mock_run_cmd.return_value


@patch('get_diff.run_cmd')
def test_get_modified_files_local(mock_run_cmd):
    mock_run_cmd.return_value = '\n'.join((
        'M\tfile.txt',
        'A\tnewfile.txt',
        'R100\told.txt\tnew.txt'
    ))
    modified_files = get_modified_files_local('branchB', 'merge_base_commit', '.')
    assert len(modified_files) == 3
    assert modified_files[0] == FileChange(FileStatus.MODIFIED, 'file.txt')
    assert modified_files[1] == FileChange(FileStatus.ADDED, 'newfile.txt')
    assert modified_files[2] == FileChange(FileStatus.RENAMED, 'new.txt', 'old.txt')


@patch('get_diff.requests.get')
def test_get_modified_files_remote(mock_requests_get):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        'status': 'ahead',
        'files': [{'status': 'added', 'filename': 'file.txt'}],
        'commit': {'sha': 'some_commit_hash'}
    }
    mock_requests_get.return_value = mock_response

    modified_files = get_modified_files_remote(
        'owner', 'repo', 'branchA', 'merge_base_commit', 'access_token'
    )

    assert len(modified_files) == 1
    assert modified_files[0].status == FileStatus.ADDED
    assert modified_files[0].path == 'file.txt'
