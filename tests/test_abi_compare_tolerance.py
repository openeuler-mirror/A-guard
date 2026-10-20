# *****************************************************************************
# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# licensed under the Mulan PSL v2.
# *****************************************************************************

"""abi_compare 版本解析容错块单元测试。

被测对象是 ci_guard/ci-guard.sh 的 abi_compare 中 rpm 版本解析与归档上传段
（从源文件按锚点抽取真实代码执行，防止测试与实现脱节）。

背景：Jenkins 构建 job 的 shell 包装带 set -e，Action 链路（bash build_entry.sh
子进程）无 -e。容错块用 if ! 条件链包裹 rpm -q，保证 rpm 损坏时两条链路行为一致：
仅日志告警 + 跳过 osv.json/details_analyse 归档上传，不中止脚本，new rpm 上传不受影响。
"""

import os
import subprocess

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CI_GUARD_SH = os.path.join(_REPO_ROOT, "ci_guard", "ci-guard.sh")

# 抽取锚点：起于 osv.json 归档守卫，止于 compare_result 上传（含中间的 new rpm 上传块）
_START_ANCHOR = "if [[ -e $result_dir/report-$old_dir-$new_dir/osv.json"
_END_ANCHOR = "if [[ -e $compare_result ]]"
_FIX_MARKER = "if ! old_version=$(rpm -q"

# rpm stub：RPM_FAIL=none 全部成功；all 全部失败（模拟损坏）；new 仅 new rpm 失败
_RPM_STUB = """\
#!/bin/bash
file=$2
fmt=$4
if [ "$RPM_FAIL" = "all" ] || { [ "$RPM_FAIL" = "new" ] && [[ "$file" == *new_rpms* ]]; }; then
    echo "error: $file: not an rpm package (or package manifest)" >&2
    exit 1
fi
case "$fmt" in
    *version*) echo "6.5.2" ;;
    *release*) echo "16.oe2403sp1" ;;
esac
"""

# bash 骨架：环境变量注入场景变量 + stub，errexit 可选，尾部放达末标记。
# 模板不含 % 与 format 占位（bash 语法冲突），块体用 %%BLOCK%% 字面拼接
_HARNESS_TEMPLATE = """\
#!/bin/bash
if [ -n "$ERREXIT" ]; then set -e; fi
old_dir="$T_OLD_DIR/"
new_dir="$T_NEW_DIR/"
result_dir="$T_RESULT_DIR"
repo="testrepo"
repo_server="srv"
repo_server_test_tail=""
tbranch="OE2403sp1"
committer="tester"
arch="x86_64"
variant_suffix=""
prid="42"
retry_command() { printf '%s\\n' "$1" >>"$T_SCPLOG"; }
export PATH="$T_BINDIR:$PATH"
%%BLOCK%%
echo "BLOCK_REACHED_END"
"""


def _extract_block():
    """从 ci-guard.sh 抽取被测代码块；源文件结构变化时给出明确失败信息。"""
    with open(_CI_GUARD_SH, encoding="utf-8") as handler:
        lines = handler.read().splitlines()
    try:
        start = next(
            index for index, line in enumerate(lines)
            if line.strip().startswith(_START_ANCHOR)
        )
        end = next(
            index for index, line in enumerate(lines)
            if index > start and line.strip().startswith(_END_ANCHOR)
        )
    except StopIteration:
        pytest.fail("ci-guard.sh 中未找到 abi_compare 版本解析块的锚点，请同步更新本测试")
    block = "\n".join(lines[start:end])
    if _FIX_MARKER not in block:
        pytest.fail("抽到的代码块缺少 if ! 容错链（改动可能被回退），请检查 ci-guard.sh")
    return block


def _run_block(tmp_path, errexit=False, rpm_fail="all", details=False):
    """搭建场景并执行抽取块，返回 (CompletedProcess, scp 调用记录列表)。"""
    old_dir = tmp_path / "old_rpms"
    new_dir = tmp_path / "new_rpms"
    result_dir = tmp_path / "oecp_result"
    bin_dir = tmp_path / "bin"
    for directory in (old_dir, new_dir, result_dir, bin_dir):
        directory.mkdir()
    (old_dir / "testrepo-6.5.2-9.oe2403sp1.x86_64.rpm").touch()
    (new_dir / "testrepo-6.5.2-16.oe2403sp1.x86_64.rpm").touch()

    # report 目录名内嵌 old/new 路径（对齐生产 oecp cli 的命名方式；
    # bash 侧 old_dir/new_dir 均带尾斜杠，此处拼接须一致）
    report_dir = result_dir / ("report-{}/-{}/".format(old_dir, new_dir))
    os.makedirs(report_dir)
    (report_dir / "osv.json").touch()
    if details:
        (result_dir / "details_analyse").mkdir()

    stub = bin_dir / "rpm"
    stub.write_text(_RPM_STUB)
    stub.chmod(0o755)

    scp_log = tmp_path / "scp.log"
    script = tmp_path / "harness.sh"
    script.write_text(_HARNESS_TEMPLATE.replace("%%BLOCK%%", _extract_block()))

    env = dict(
        os.environ,
        T_OLD_DIR=str(old_dir),
        T_NEW_DIR=str(new_dir),
        T_RESULT_DIR=str(result_dir),
        T_BINDIR=str(bin_dir),
        T_SCPLOG=str(scp_log),
        RPM_FAIL=rpm_fail,
        ERREXIT="1" if errexit else "",
    )
    proc = subprocess.run(
        ["bash", str(script)], env=env, capture_output=True, text=True, timeout=30
    )
    scp_entries = (
        scp_log.read_text().splitlines() if scp_log.exists() else []
    )
    return proc, scp_entries


class TestAbiCompareVersionParseTolerance:
    """rpm 损坏场景：两条 errexit 语义下均不中止 job、跳过归档、new rpm 照常上传。"""

    def test_corrupt_rpm_with_errexit_does_not_abort(self, tmp_path):
        proc, scp_entries = _run_block(tmp_path, errexit=True, rpm_fail="all")
        assert proc.returncode == 0
        assert "BLOCK_REACHED_END" in proc.stdout
        assert "skip osv.json archive upload" in proc.stdout
        assert not [entry for entry in scp_entries if "osv.json" in entry]
        assert any("new_rpms" in entry for entry in scp_entries)

    def test_corrupt_rpm_without_errexit_does_not_abort(self, tmp_path):
        proc, scp_entries = _run_block(tmp_path, errexit=False, rpm_fail="all")
        assert proc.returncode == 0
        assert "BLOCK_REACHED_END" in proc.stdout
        assert "skip osv.json archive upload" in proc.stdout
        assert not [entry for entry in scp_entries if "osv.json" in entry]
        assert any("new_rpms" in entry for entry in scp_entries)

    def test_partial_failure_new_rpm_corrupt_takes_warn_branch(self, tmp_path):
        proc, scp_entries = _run_block(tmp_path, errexit=True, rpm_fail="new")
        assert proc.returncode == 0
        assert "skip osv.json archive upload" in proc.stdout
        assert not [entry for entry in scp_entries if "osv.json" in entry]

    def test_rpm_diagnostic_error_preserved_in_output(self, tmp_path):
        proc, _ = _run_block(tmp_path, errexit=True, rpm_fail="all")
        assert "not an rpm package" in proc.stderr

    def test_valid_rpm_uploads_archive_with_versioned_name(self, tmp_path):
        proc, scp_entries = _run_block(tmp_path, errexit=True, rpm_fail="none")
        assert proc.returncode == 0
        assert "skip osv.json archive upload" not in proc.stdout
        osv_entries = [entry for entry in scp_entries if "osv.json" in entry]
        assert osv_entries, "版本解析成功时必须上传 osv.json 归档"
        assert "testrepo_6.5.2-16.oe2403sp1_6.5.2-16.oe2403sp1.json" in osv_entries[0]
        assert not [entry for entry in scp_entries if "details_analyse" in entry]

    def test_valid_rpm_uploads_details_analyse_when_present(self, tmp_path):
        _, scp_entries = _run_block(
            tmp_path, errexit=True, rpm_fail="none", details=True
        )
        assert any("details_analyse" in entry for entry in scp_entries)
