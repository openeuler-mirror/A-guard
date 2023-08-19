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
from functools import update_wrapper
import click
from cli import (
    hotpatch,
    build,
    diff_analysis,
    install,
    notify,
    pull_link,
    download_rpm,
    init_repo,
)


class CmdGroupInfo:
    """
    Command group information
    """

    def __init__(self, **kwargs) -> None:
        self.__dict__.update(**kwargs)


def ci_context(fun):
    """
    ci command line context management
    """

    @click.pass_context
    def context_wrapper(ctx, *args, **kwargs):
        ctx.ensure_object(CmdGroupInfo)
        return ctx.invoke(fun, ctx.obj, *args, **kwargs)

    return update_wrapper(context_wrapper, fun)


class CiGroup(click.Group):
    """
    Command line parameter group to simplify common parameters
    """

    version_option = click.Option(
        ["--version", "-V"],
        help="Show the ci version",
        expose_value=False,
        is_flag=True,
        is_eager=True,
    )

    def __init__(self, default_commands=True, **extra) -> None:
        params = list(extra.pop("params", None) or ())
        params.append(CiGroup.version_option)
        super().__init__(params=params, **extra)
        if default_commands:
            self._add_command()

    def _add_command(self):
        self.add_command(hotpatch)
        self.add_command(install)
        self.add_command(build)
        self.add_command(notify)
        self.add_command(diff_analysis)
        self.add_command(pull_link)
        self.add_command(download_rpm)
        self.add_command(init_repo)

    def main(self, *args, **kwargs):
        """
        Command invocation entry,Contains commands and parameters
        """
        return super(CiGroup, self).main(*args, **kwargs)
