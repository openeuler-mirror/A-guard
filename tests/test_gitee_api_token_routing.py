from types import SimpleNamespace

import pytest

from api import Api
from api import gitee as gitee_module
from api.gitee import Gitee


class _Recorder(object):
    def __init__(self):
        self.calls = []
        self.return_value = {}

    def __call__(self, url, method="get", data=None, text=False, level="warning", **kwargs):
        self.calls.append({"url": url, "headers": kwargs.get("headers")})
        return self.return_value


@pytest.fixture
def recorder(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(Api, "_request", staticmethod(rec))
    return rec


@pytest.fixture
def empty_config(monkeypatch):
    monkeypatch.setattr(gitee_module, "config", SimpleNamespace(gitee_token=None))


READ_CALLS = [
    ("get_single_pr_info", (1,)),
    ("get_all_tag", (1, ["ci_processing"])),
    ("get_issue", ("12345",)),
]

WRITE_CALLS = [
    ("create_pr_comment", (1, "comment body")),
    ("modify_pr_comment", (1, "comment body")),
    ("create_tag", (1, "ci_processing")),
    ("remove_tag", (1, "ci_failed")),
]


@pytest.mark.parametrize("method,args", READ_CALLS)
def test_read_methods_use_read_token(recorder, method, args):
    api = Gitee("repo", read_token="read-token", write_token="write-token")

    getattr(api, method)(*args)

    assert recorder.calls[0]["headers"] == {"Authorization": "Bearer read-token"}


@pytest.mark.parametrize("method,args", WRITE_CALLS)
def test_write_methods_use_write_token(recorder, method, args):
    api = Gitee("repo", read_token="read-token", write_token="write-token")

    getattr(api, method)(*args)

    assert recorder.calls[0]["headers"] == {"Authorization": "Bearer write-token"}


def test_constructor_allows_empty_token(empty_config):
    Gitee("repo")


def test_method_fails_fast_without_token(empty_config, recorder):
    api = Gitee("repo")

    with pytest.raises(RuntimeError, match="read token not provided"):
        api.get_single_pr_info(1)

    assert recorder.calls == []


def test_config_fallback_uses_gitee_token(recorder, monkeypatch):
    monkeypatch.setattr(gitee_module, "config", SimpleNamespace(gitee_token="config-token"))

    api = Gitee("repo")
    api.get_single_pr_info(1)
    api.create_pr_comment(1, "comment body")

    assert recorder.calls[0]["headers"] == {"Authorization": "Bearer config-token"}
    assert recorder.calls[1]["headers"] == {"Authorization": "Bearer config-token"}


def test_legacy_positional_token_routes_both(recorder):
    api = Gitee("repo", "src-openeuler", "legacy-token")

    api.get_single_pr_info(1)
    api.create_pr_comment(1, "comment body")

    assert recorder.calls[0]["headers"] == {"Authorization": "Bearer legacy-token"}
    assert recorder.calls[1]["headers"] == {"Authorization": "Bearer legacy-token"}
