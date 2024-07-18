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
from core.license import CheckLicense


@click.option(
    "-a",
    "--arch",
    help="System architecture",
    type=click.Choice(["x86_64", "aarch64"], case_sensitive=False),
    default="x86_64",
    show_default=True,
    required=True,
)
@click.option("-pr", "--pull-request", "pull_request", help="The full url of the pull")
@click.command("license", help="check package license")
def license(arch, pull_request):
    """
    Check package license
    :param arch: x86_64 or aarch64
    :param pull_request: Full pr link
    """
    click.echo("start check license")
    license_check = CheckLicense(arch=arch).check_license(pull_request=pull_request)
    if license_check:
        message = "package license check successful."
        click.echo(click.style(message, fg="green"))
    else:
        message = "package license check failed."
        click.echo(click.style(message, fg="red"))
        sys.exit(0)


__all__ = ("license",)
