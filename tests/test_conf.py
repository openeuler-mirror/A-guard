import pytest

from conf import Configs, PreloadingSettings


@pytest.fixture
def yaml_path(tmp_path):
    def _write(content, name="config.yaml"):
        path = tmp_path / name
        path.write_text(content, encoding="utf-8")
        return str(path)

    return _write


class TestLoadSettings:
    def test_loads_valid_yaml(self, yaml_path):
        path = yaml_path("platform: gitee\npr: 42\n")
        assert Configs.load_settings(path) == {"platform": "gitee", "pr": 42}

    def test_invalid_yaml_raises_value_error(self, yaml_path):
        path = yaml_path("platform: [unclosed\n")
        with pytest.raises(ValueError, match="Configuration file parsing error"):
            Configs.load_settings(path)


class TestConfigs:
    def test_gitcode_normalized_to_atomgit(self, yaml_path):
        configs = Configs(yaml_path("platform: gitcode\n"))
        assert configs.platform == "atomgit"

    def test_other_platform_is_preserved(self, yaml_path):
        configs = Configs(yaml_path("platform: gitee\n"))
        assert configs.platform == "gitee"

    def test_user_values_override_defaults(self, yaml_path):
        configs = Configs(yaml_path("pr: 7\n"))
        assert configs.pr == 7


class TestPreloadingSettings:
    def test_lazy_loading_from_env(self, yaml_path, monkeypatch):
        monkeypatch.setenv("CI-SETTINGS", yaml_path("platform: gitee\npr: 42\n"))
        settings = PreloadingSettings()

        assert settings.config_ready is False
        assert settings.pr == 42
        assert settings.config_ready is True

    def test_missing_config_file_raises(self, tmp_path, monkeypatch):
        missing = tmp_path / "no-such-dir" / "config.yaml"
        monkeypatch.setenv("CI-SETTINGS", str(missing))
        settings = PreloadingSettings()

        with pytest.raises(RuntimeError, match="CI-SETTINGS"):
            _ = settings.platform

    def test_default_config_used_without_env(self, monkeypatch):
        monkeypatch.delenv("CI-SETTINGS", raising=False)
        settings = PreloadingSettings()

        assert settings.platform == "atomgit"

    def test_setattr_updates_value(self, yaml_path, monkeypatch):
        monkeypatch.setenv("CI-SETTINGS", yaml_path("pr: 1\n"))
        settings = PreloadingSettings()
        assert settings.pr == 1

        settings.pr = 9
        assert settings.pr == 9

    def test_delattr_then_getattr_returns_none(self, yaml_path, monkeypatch):
        monkeypatch.setenv("CI-SETTINGS", yaml_path("pr: 1\n"))
        settings = PreloadingSettings()
        _ = settings.pr

        del settings.pr
        assert settings.pr is None

    def test_reload_picks_up_file_changes(self, tmp_path, monkeypatch):
        path = tmp_path / "config.yaml"
        path.write_text("pr: 1\n", encoding="utf-8")
        monkeypatch.setenv("CI-SETTINGS", str(path))
        settings = PreloadingSettings()
        assert settings.pr == 1

        path.write_text("pr: 2\n", encoding="utf-8")
        settings.reload()
        assert settings.pr == 2
