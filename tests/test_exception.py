import pytest

from exception import (
    CiError,
    ConfigError,
    FileError,
    LinkError,
    RequestError,
)


class TestCiErrorBase:
    def test_raise_and_catch(self):
        with pytest.raises(CiError):
            raise CiError("something went wrong")

    def test_message_is_preserved(self):
        err = CiError("something went wrong")
        assert str(err) == "something went wrong"


class TestSubclassHierarchy:
    @pytest.mark.parametrize(
        "error_cls",
        [
            RequestError,
            ConfigError,
            FileError,
            LinkError,
        ],
    )
    def test_is_ci_error_subclass(self, error_cls):
        assert issubclass(error_cls, CiError)


class TestErrorMessages:
    def test_request_error_prefix(self):
        assert str(RequestError("timeout")) == "Error calling URL: timeout"

    def test_config_error_prefix(self):
        message = str(ConfigError("bad key"))
        assert "Configuration file content parsing error: bad key" in message
        assert "Please check the configuration file" in message

    def test_file_error_prefix(self):
        assert str(FileError("missing")) == "File operation error: missing"

    def test_link_error_prefix(self):
        assert str(LinkError("broken")) == "Link pull error: broken"
