import pytest

from exception import (
    BranchPackageError,
    CiError,
    ConfigError,
    CreateProjectError,
    DeletePackageError,
    FileError,
    LinkError,
    ModifyProjectError,
    OscError,
    ParameterError,
    ProjectNameError,
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
            OscError,
            ProjectNameError,
            CreateProjectError,
            DeletePackageError,
            BranchPackageError,
            ModifyProjectError,
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

    def test_osc_error_prefix(self):
        assert str(OscError("exit 1")) == "osc command execution error: exit 1"

    def test_project_name_error_prefix(self):
        assert str(ProjectNameError("n/a")) == "Project name is error: n/a"

    def test_create_project_error_prefix(self):
        assert str(CreateProjectError("denied")) == "failed create Project: denied"

    def test_delete_package_error_prefix(self):
        assert str(DeletePackageError("in use")) == "delete Package Error: in use"

    def test_branch_package_error_prefix(self):
        assert str(BranchPackageError("conflict")) == "branch Package Error: conflict"

    def test_modify_project_error_prefix(self):
        message = str(ModifyProjectError("locked"))
        assert message == "failed to modify the meta value of the project: locked"


class TestParameterError:
    def test_message_contains_kwargs(self):
        err = ParameterError(name="pkg", pr=123)
        message = str(err)
        assert "Incoming parameter error:" in message
        assert "'name': 'pkg'" in message
        assert "'pr': 123" in message
        assert "please check and try again" in message

    def test_empty_kwargs(self):
        message = str(ParameterError())
        assert "Incoming parameter error: {}" in message
