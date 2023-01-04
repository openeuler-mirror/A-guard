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
import os
import click
import constant
from core.install import InstallVerify, UnifyBuildInstallVerify
from core import ProcessRecords
from conf import config


@click.command("install", help="Install binary package")
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
@click.option(
    "-tb", "--target-branch", "target_branch", help="The target branch of pull"
)
@click.option(
    "-p",
    "--packages",
    multiple=True,
    help="List of packages for installation verification",
)
@click.option(
    "--multiple/--no-multiple",
    default=False,
    help="Multi package installation check. Single package installation by default",
)
@click.option(
    "--ignore/--no-ignore",
    default=False,
    help="Ignoring the installation check, the installation procedure is performed by default",
)
def install(arch, pull_request, target_branch, packages, multiple, ignore):
    """
    Single package/multi-package installation verification
    :param pull_request: Full pr link
    :param target_branch: target branch
    :param packages: Single or multiple packages
    :param multiple: This value is True for multi-package installation checks
    :param ignore: Ignore the installation check when true
    """
    click.echo("Start check install")
    if multiple:
        build_depend, install_depend = ProcessRecords(
            package=config.repo, pr=str(config.pr)
        ).depend()
        build_depend.extend(install_depend)
        packages = tuple(build_depend)
    if not packages:
        click.echo(click.style("Missing software package", fg="red"))
        exit(1)

    # Selecting the build environment
    build_env = InstallVerify if config.build_env == "obs" else UnifyBuildInstallVerify
    install_verify = build_env(arch=arch, target_branch=target_branch, ignore=ignore)

    install_check = install_verify.install(
        pull_request=pull_request, multiple=multiple, packages=packages
    )
    install_status_log = os.path.join(
        constant.PROJECT_WORK_DIR, "install-logs", "installed"
    )
    if os.path.exists(install_status_log):
        os.remove(install_status_log)
    if install_check:
        message = (
            "Multiple package installation check successful."
            if multiple
            else "Single package installation check successful."
        )
        click.echo(click.style(message, fg="green"))
    else:
        message = (
            "Multiple package installation check failed."
            if multiple
            else "Single package installation check failed."
        )
        click.echo(click.style(message, fg="red"))
        sys.exit(1)


__all__ = ("install",)
