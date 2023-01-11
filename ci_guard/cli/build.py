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
from core.build import BuildVerify


@click.command("build", help="build package")
@click.option(
    "-a",
    "--arch",
    help="package architecture",
    type=click.Choice(["x86_64", "aarch64"], case_sensitive=False),
    default="x86_64",
    show_default=True,
    required=True,
)
@click.option("-pr", "--pull-request", help="Full url of pr")
@click.option("-tb", "--target-branch", help="pr's target branch")
@click.option("--multiple/--no-multiple", default=False, help="Multiple package compilation, single package compilation by default")
@click.option("--ignore/--no-ignore", default=False, help="Whether to ignore the results of multi-package verification")
def build(pull_request, target_branch, arch, multiple, ignore):
    click.echo("[INFO] start check build")
    choose = "multiple" if multiple else "single"
    build_obj = BuildVerify(pull_request, target_branch, arch, multiple, ignore)
    print(pull_request, target_branch, arch, multiple)
    check_result = build_obj.build()
    if check_result.get("current_result") in ["success", "excluded"]:
         # package build successfully
        click.echo(click.style(f"{choose} package build successfully", fg="green"))
    else:
        click.echo(click.style(f"{choose} package build failed", fg="red"))
        sys.exit(1)


__all__ = "build"
