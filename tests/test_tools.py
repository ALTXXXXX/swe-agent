# tests/test_tools.py
import pytest
from pathlib import Path
from tools import _list_files, _write_file, _read_file, _edit_file, _run_shell

def test_list_files_dir_not_found():
    result = _list_files({"file_path": "nonexistent_dir"})
    assert "Error" in result

def test_list_files_works(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hi')")
    result = _list_files({"file_path": str(tmp_path / "src")})
    assert "main.py" in result
    assert "[dir]" not in result

def test_write_and_read_file(tmp_path):
    fp = str(tmp_path / "new" / "test.txt")
    _write_file({"file_path": fp, "content": "hello"})
    result = _read_file({"file_path": fp})
    assert "hello" in result

def test_edit_file_unique_match(tmp_path):
    fp = str(tmp_path / "a.txt")
    Path(fp).write_text("old text here")
    result = _edit_file({"file_path": fp, "old_string": "old", "new_string": "new"})
    assert "Successfully" in result
    assert Path(fp).read_text() == "new text here"

def test_edit_file_duplicate_should_fail(tmp_path):
    fp = str(tmp_path / "a.txt")
    Path(fp).write_text("old old old")
    result = _edit_file({"file_path": fp, "old_string": "old", "new_string": "new"})
    assert "Error" in result

def test_run_shell_success():
    from tools import _run_shell
    result = _run_shell({"command": "echo hello"})
    assert "hello" in result

def test_run_shell_failure():
    from tools import _run_shell
    result = _run_shell({"command": "this_cmd_does_not_exist_xyz"})
    assert "failed" in result.lower()

def test_run_shell_timeout():
    from tools import _run_shell
    result = _run_shell({"command": "ping -n 10 127.0.0.1", "timeout": 1})
    assert "timed out" in result.lower()