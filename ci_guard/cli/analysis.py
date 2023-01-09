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
import os.path
import sys

import click

from conf import config
from core.analysis import Analysis
from exception import FileError


@click.command("analysis", help="Analysis of package variation content and scope of impact")
@click.option(
    "-df",
    "--diff-file",
    default=config.compare_result,
    show_default=True,
    help="Output file of the package difference comparison tool comparison results",
)
def diff_analysis(diff_file):
    click.echo("[INFO] Start compare package")
    if not diff_file or not os.path.exists(diff_file):
        raise FileError(
            msg=f"Package comparison result file: {diff_file} does not exist, please confirm the file path"
        )
    analysis_obj = Analysis(diff_file=diff_file)
    effect_detail = analysis_obj.depended_analysis()
    if effect_detail.get("need_verify"):
        click.echo(click.style(f"Need to continue to verify,{effect_detail}", fg="red"))
    else:
        click.echo(click.style(f"No verification needed,{effect_detail}", fg="green"))
        sys.exit(1)

__all__ = "diff_analysis"
