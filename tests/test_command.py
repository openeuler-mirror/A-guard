import os
import sys

from command import _analysis_out, command


class FakePipe:
    def __init__(self, data):
        self._data = data

    def readline(self):
        return self._data


class TestAnalysisOut:
    def test_empty_line_returns_false(self):
        container = []
        assert _analysis_out(FakePipe(b""), container, False) is False
        assert container == []

    def test_non_empty_line_is_appended(self):
        container = []
        assert _analysis_out(FakePipe(b"hello\n"), container, False) is True
        assert container == ["hello"]

    def test_utf8_decode_errors_are_ignored(self):
        container = []
        assert _analysis_out(FakePipe(b"abc\xffdef\n"), container, False) is True
        assert container == ["abcdef"]

    def test_console_true_logs_line(self, monkeypatch):
        logged = []
        monkeypatch.setattr("command.logger.info", lambda msg: logged.append(msg))
        _analysis_out(FakePipe(b"visible\n"), [], True)
        assert logged == ["visible"]


class TestCommandSync:
    def test_success_captures_stdout(self):
        returncode, output, error = command(
            [sys.executable, "-c", "print('unit-test-ok')"], console=False
        )
        assert returncode == 0
        assert "unit-test-ok" in output
        assert error == ""

    def test_failure_captures_stderr(self):
        returncode, output, error = command(
            [sys.executable, "-c", "import sys; sys.stderr.write('boom'); sys.exit(2)"],
            console=False,
        )
        assert returncode == 2
        assert "boom" in error

    def test_multi_line_stdout_joined_with_linesep(self):
        returncode, output, _ = command(
            [sys.executable, "-c", "print('a'); print('b')"], console=False
        )
        assert returncode == 0
        assert output.split(os.linesep) == ["a", "b"]

    def test_runs_in_given_cwd(self, tmp_path):
        returncode, output, _ = command(
            [sys.executable, "-c", "import os; print(os.getcwd())"],
            console=False,
            cwd=str(tmp_path),
        )
        assert returncode == 0
        assert os.path.normcase(os.path.realpath(output)) == os.path.normcase(
            os.path.realpath(str(tmp_path))
        )


class TestCommandAsync:
    def test_async_returns_bytes(self):
        returncode, output, error = command(
            [sys.executable, "-c", "print('async-ok')"],
            console=False,
            synchronous=False,
        )
        assert returncode == 0
        assert b"async-ok" in output
        assert error == b""


class TestCommandNotFound:
    def test_missing_command_returns_error(self):
        returncode, output, error = command(
            ["this_command_really_does_not_exist_9527"], console=False
        )
        assert returncode == 1
        assert output is None
        assert "Command not found" in error
