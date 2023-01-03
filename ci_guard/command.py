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
import os
import subprocess
from logger import logger


def _analysis_out(pipe_result, container: list, console):
    line = pipe_result.readline().decode("utf-8", errors="ignore").strip()
    if not line:
        return False
    if console:
        logger.info(line)
    if line != os.linesep:
        container.append(line)
    return True


def command(cmds: list, input=None, cwd=None, console=True, synchronous=True):
    """
    Executing shell commands
    :param cmd_list: Command set
    :param cwd: Directory where the command is executed
    :returns: Result is a tuple,exp: (status code,output,err)
    """

    try:
        pipe = subprocess.Popen(
            cmds,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
        )
    except FileNotFoundError:
        cmds = " ".join(cmds)
        logger.error(f"Command not found:{cmds}.")
        error = f"Command not found:{cmds}."
        return 1, None, error
    if input:
        pipe.stdin.write(input)

    if synchronous:
        output, error = [], []
        while True:
            if pipe.poll() is not None:
                break
            while True:
                if not _analysis_out(pipe.stdout, output, console):
                    break
        if pipe.poll():
            while True:
                if not _analysis_out(pipe.stderr, error, console):
                    break
        output = os.linesep.join(output)
        error = os.linesep.join(error)
    else:
        output, error = pipe.communicate()

    return pipe.returncode, output, error


__all__ = ("command",)
