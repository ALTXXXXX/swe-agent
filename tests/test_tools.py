# tests/test_tools.py
from pathlib import Path

from tools import (
    edit_file,
    execute_tool,
    list_files,
    read_file,
    run_shell,
    write_file,
)


def test_list_files_dir_not_found():
    result = list_files(file_path="nonexistent_dir")
    assert "Error" in result


def test_list_files_works(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hi')")
    result = list_files(file_path=str(tmp_path / "src"))
    assert "main.py" in result
    assert "[dir]" not in result


def test_write_and_read_file(tmp_path):
    fp = str(tmp_path / "new" / "test.txt")
    write_file(file_path=fp, content="hello")
    result = read_file(file_path=fp)
    assert "hello" in result


def test_write_file_reports_line_count(tmp_path):
    fp = str(tmp_path / "lines.txt")
    result = write_file(file_path=fp, content="a\nb\nc")
    assert "(3 lines)" in result
    assert "| a" in result


def test_edit_file_unique_match(tmp_path):
    fp = str(tmp_path / "a.txt")
    Path(fp).write_text("old text here")
    result = edit_file(file_path=fp, old_string="old", new_string="new")
    assert "Successfully" in result
    assert Path(fp).read_text() == "new text here"


def test_edit_file_duplicate_should_fail(tmp_path):
    fp = str(tmp_path / "a.txt")
    Path(fp).write_text("old old old")
    result = edit_file(file_path=fp, old_string="old", new_string="new")
    assert "Error" in result


def test_run_shell_success():
    result = run_shell(command="echo hello")
    assert "hello" in result


def test_run_shell_failure():
    result = run_shell(command="this_cmd_does_not_exist_xyz")
    assert "failed" in result.lower()


def test_run_shell_timeout():
    result = run_shell(command="ping -n 10 127.0.0.1", timeout=1)
    assert "timed out" in result.lower()


def test_execute_tool_unknown_tool():
    result = execute_tool("not_a_tool", {})
    assert "不存在" in result


def test_execute_tool_missing_argument():
    result = execute_tool("read_file", {})
    assert "参数错误" in result


def test_execute_tool_extra_argument():
    result = execute_tool("read_file", {"file_path": "x", "unexpected": 1})
    assert "参数错误" in result


def test_execute_tool_non_dict_arguments():
    result = execute_tool("read_file", ["not", "a", "dict"])
    assert "参数错误" in result
