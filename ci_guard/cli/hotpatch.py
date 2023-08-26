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
from core.verify_meta import VerifyHotPatchMeta


@click.command("hotpatch", help="make hotpatch")
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
    click.echo("[INFO] start make hotpatch")
    build_obj = MakeHotPatchProject(x86_debuginfo, aarch64_debuginfo, issue_title, issue_date, repo)
    build_obj.build()

@click.command("verify_meta", help="verify meta file")
@click.option("-i", "--meta-file", help="hot patch metadata file")
@click.option("-o", "--output", help="hot patch output file")
@click.option("-p", "--patch-file", help="patch file list")
@click.option("-m", "--mode", help="hot patch type")
def verify_meta(meta_file, output, patch_file, mode):
    """
    Rpm build
    :param pull_request:  pr link to be build
    :param target_branch: target branch of the build
    :param x86_debuginfo: x86 debuginfo package path
    :param aarch64_debuginfo: aarch64 debuginfo package path
    :param issue_title: hotpatch issue title
    :param issue_date: hotpatch issue date
    """
    click.echo("[INFO] start verify meta file")
    build_obj = VerifyHotPatchMeta(meta_file, output, patch_file, mode)
    build_obj.verify()

__all__ = ("hotpatch", "verify_meta", )
