#!/usr/bin/python3
# ******************************************************************************
# Copyright (c) Huawei Technologies Co., Ltd. 2020-2020. All rights reserved.
# licensed under the Mulan PSL v2.
# You can use this software according to the terms and conditions of the Mulan PSL v2.
# You may obtain a copy of Mulan PSL v2 at:
#     http://license.coscl.org.cn/MulanPSL2
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FIT FOR A PARTICULAR
# PURPOSE.
# See the Mulan PSL v2 for more details.
# ******************************************************************************/
import sys
import click
from core.hotpatch import MakeHotPatchProject


@click.command("hotpatch", help="build package")
@click.option("-xd", "--x86-debuginfo", help="x86 debuginfo package path")
@click.option("-ad", "--aarch64-debuginfo", help="aarch64 debuginfo package path")
@click.option("-t", "--issue-title", help="hot patch issue title")
@click.option("-d", "--issue-date", help="hot patch issue create date")
@click.option("-r", "--repo", help="need to do hotpatch repo")
def hotpatch(x86_debuginfo, aarch64_debuginfo, issue_title, issue_date, repo):
    """
    Rpm build
    :param pull_request:  pr link to be build
    :param target_branch: target branch of the build
    :param x86_debuginfo: x86 debuginfo package path
    :param aarch64_debuginfo: aarch64 debuginfo package path
    :param issue_title: hotpatch issue title
    :param issue_date: hotpatch issue date
    """
    click.echo("[INFO] start check build")
    build_obj = MakeHotPatchProject(x86_debuginfo, aarch64_debuginfo, issue_title, issue_date, repo)
    build_obj.build()


__all__ = ("hotpatch",)
