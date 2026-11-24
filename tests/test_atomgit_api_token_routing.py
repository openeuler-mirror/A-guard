import json
from types import SimpleNamespace

import pytest

from api import Api
from api import atomgit as atomgit_module
from api.atomgit import Atomgit


class _Recorder(object):
    def __init__(self):
        self.calls = []
        self.return_value = {}

    def __call__(self, url, method="get", data=None, text=False, level="warning", **kwargs):
        self.calls.append(
            {
                "url": url,
                "method": method,
                "data": data,
                "headers": kwargs.get("headers"),
                "kwargs": kwargs,
            }
        )
        return self.return_value


@pytest.fixture
def recorder(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(Api, "_request", staticmethod(rec))
    return rec


@pytest.fixture
def empty_config(monkeypatch):
    monkeypatch.setattr(
        atomgit_module,
        "config",
        SimpleNamespace(atomgit_token=None, atomgit_write_token=None),
    )


READ_CALLS = [
    ("get_single_pr_info", (1,)),
    ("get_pr_files", (1,)),
    ("get_all_tag", (1, ["ci_processing"])),
    ("get_issue", ("12345",)),
]

WRITE_CALLS = [
    ("create_pr_comment", (1, "comment body")),
    ("modify_pr_comment", (1, "comment body")),
    ("create_tag", (1, "ci_processing")),
    ("remove_tag", (1, "ci_failed")),
]

ALL_CALLS = READ_CALLS + WRITE_CALLS


@pytest.mark.parametrize("method,args", READ_CALLS)
def test_read_methods_use_read_token(recorder, method, args):
    api = Atomgit("repo", read_token="read-token", write_token="write-token")

    getattr(api, method)(*args)

    assert len(recorder.calls) == 1
    assert recorder.calls[0]["headers"] == {"Authorization": "Bearer read-token"}


@pytest.mark.parametrize("method,args", WRITE_CALLS)
def test_write_methods_use_write_token(recorder, method, args):
    api = Atomgit("repo", read_token="read-token", write_token="write-token")

    getattr(api, method)(*args)

    assert len(recorder.calls) == 1
    assert recorder.calls[0]["headers"] == {"Authorization": "Bearer write-token"}


def test_constructor_allows_empty_tokens(empty_config):
    Atomgit("repo")


def test_read_method_fails_fast_without_read_token(recorder):
    api = Atomgit("repo", write_token="write-token")

    with pytest.raises(RuntimeError, match="read token not provided"):
        api.get_single_pr_info(1)

    assert recorder.calls == []


def test_write_method_fails_fast_without_write_token(recorder):
    api = Atomgit("repo", read_token="read-token")

    with pytest.raises(RuntimeError, match="write token not provided"):
        api.create_pr_comment(1, "comment body")

    assert recorder.calls == []


@pytest.mark.parametrize("method,args", READ_CALLS)
def test_read_only_api_keeps_read_available(recorder, method, args):
    """反向测试：只有 READ token 时，全部读方法正常。"""
    api = Atomgit("repo", read_token="read-token")

    getattr(api, method)(*args)

    assert recorder.calls[0]["headers"] == {"Authorization": "Bearer read-token"}


@pytest.mark.parametrize("method,args", WRITE_CALLS)
def test_read_only_api_fails_all_writes(recorder, method, args):
    """反向测试：WRITE 缺失（等价于误用 READ）时，全部写方法 fail-fast。"""
    api = Atomgit("repo", read_token="read-token")

    with pytest.raises(RuntimeError, match="write token not provided"):
        getattr(api, method)(*args)

    assert recorder.calls == []


def test_legacy_positional_token_routes_both(recorder):
    api = Atomgit("repo", "src-openeuler", "legacy-token")

    api.get_single_pr_info(1)
    api.create_pr_comment(1, "comment body")

    assert recorder.calls[0]["headers"] == {"Authorization": "Bearer legacy-token"}
    assert recorder.calls[1]["headers"] == {"Authorization": "Bearer legacy-token"}


def test_split_tokens_take_precedence_over_legacy_token(recorder):
    api = Atomgit(
        "repo", "src-openeuler", "legacy-token",
        read_token="read-token", write_token="write-token",
    )

    api.get_single_pr_info(1)
    api.create_pr_comment(1, "comment body")

    assert recorder.calls[0]["headers"] == {"Authorization": "Bearer read-token"}
    assert recorder.calls[1]["headers"] == {"Authorization": "Bearer write-token"}


def test_config_fallback_uses_read_and_write_token(recorder, monkeypatch):
    monkeypatch.setattr(
        atomgit_module,
        "config",
        SimpleNamespace(atomgit_token="config-read", atomgit_write_token="config-write"),
    )

    api = Atomgit("repo")
    api.get_single_pr_info(1)
    api.create_pr_comment(1, "comment body")

    assert recorder.calls[0]["headers"] == {"Authorization": "Bearer config-read"}
    assert recorder.calls[1]["headers"] == {"Authorization": "Bearer config-write"}


def test_requests_do_not_carry_access_token(recorder):
    api = Atomgit("repo", read_token="read-token", write_token="write-token")

    for method, args in ALL_CALLS:
        getattr(api, method)(*args)

    assert len(recorder.calls) == len(ALL_CALLS)
    for call in recorder.calls:
        assert "access_token" not in call["url"]
        payload = json.dumps(
            {"data": call["data"], "kwargs": call["kwargs"]}, default=str, ensure_ascii=False
        )
        assert "access_token" not in payload


def test_package_committer_does_not_use_token(recorder):
    recorder.return_value = {"data": []}

    Atomgit("repo", read_token="read-token", write_token="write-token").package_committer(["pkg"])

    assert len(recorder.calls) == 1
    assert recorder.calls[0]["headers"] is None
