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
from cli.hotpatch import hotpatch, verify_meta
from cli.install import install
from cli.build import build
from cli.comment import notify
from cli.analysis import diff_analysis
from cli.pull_link import pull_link
from cli.download import download_rpm
from cli.initrepo import init_repo
from cli.license import license
from cli.base import CiGroup


ci = CiGroup(help="""Auto ci commands""")


def main():
    """
    The starting method of a terminal command
    """
    ci.main(args=sys.argv[1:])


__all__ = (
    "CiGroup",
    "install",
    "main",
    "build",
    "notify",
    "diff_analysis",
    "pull_link",
    "download_rpm",
    "init_repo",
    "hotpatch",
    "verify_meta",
    "license",
)
