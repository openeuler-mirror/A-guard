#!/usr/bin/python3
# ******************************************************************************
# Copyright (c) Huawei Technologies Co., Ltd. 2020-2022. All rights reserved.
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
from core.install import InstallVerify


@click.command("initrepo", help="Update repo source file")
def init_repo():
    """
    Initialize the build repo file
    """
    click.echo("[INFO] start update repo")
    result = InstallVerify().update_repo()
    if not result:
        click.echo(click.style("Failed to update repo source", fg="red"))
        sys.exit(1)

    click.echo(click.style("Update repo source successful", fg="green"))


__all__ = ("init_repo",)