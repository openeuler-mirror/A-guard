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
import logging
import logging.config
from colorlog import ColoredFormatter


default_log_handler = logging.StreamHandler()
default_log_handler.setFormatter(
    logging.Formatter(
        "%(asctime)s [File:]%(filename)s Line:%(lineno)d"
        "-%(levelname)s- [Details]: %(message)s",
        datefmt="%a, %d %b %Y %H:%M:%S",
    )
)


def get_logger(name="ci_tools", log_conf=None):
    """
    Gets a log for a particular record format
    :param ci_tools: log name
    :param log_conf: log config file
    """
    if log_conf:
        logging.config.fileConfig(log_conf)
    _logger = logging.getLogger(name=name)
    level = _logger.getEffectiveLevel()

    if any(handler.level <= level for handler in _logger.handlers):
        _logger.setLevel(logging.INFO)

    return _logger


class CusColoredFormatter(ColoredFormatter):
    """
    Logger color formatter
    """

    def __init__(
        self,
        fmt=None,
        datefmt=None,
        style="%",
        log_colors=None,
        reset=True,
        secondary_log_colors=None,
    ):
        log_colors = {
            "DEBUG": "reset",
            "INFO": "reset",
            "WARNING": "bold_yellow",
            "ERROR": "bold_red",
            "CRITICAL": "bold_red",
        }
        super(CusColoredFormatter, self).__init__(
            fmt, datefmt, style, log_colors, reset, secondary_log_colors
        )


logger = get_logger(
    log_conf=os.path.join(os.path.dirname(__file__), "conf", "log.conf")
)
__all__ = ("get_logger", "logger", "CusColoredFormatter")
