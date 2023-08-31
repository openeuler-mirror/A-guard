#! /usr/bin/env python
# coding=utf-8
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
# ******************************************************************************

import re


class CompareVersion:
    @staticmethod
    def vr_compare(x_version, comparison_operator, y_version):

        if "-" not in x_version or "-" not in y_version:
            x_version = re.split("-", x_version)[0]
            y_version = re.split("-", y_version)[0]

        if ":" not in x_version:
            x_version = "0:" + x_version
        if ":" not in y_version:
            y_version = "0:" + y_version

        version_array_x = re.split(r"\.|\:|\-", x_version)
        version_array_y = re.split(r"\.|\:|\-", y_version)
        len_x_version_array = len(version_array_x)
        len_y_version_array = len(version_array_y)
        len_min = min(len_x_version_array, len_y_version_array)

        if version_array_x == version_array_y:
            if comparison_operator in ('EQ', 'GE', 'LE'):
                return True
            return False

        for i in range(len_min):
            x = version_array_x[i]
            y = version_array_y[i]

            if x.isdigit() and y.isdigit():
                if not x.startswith("0") and not y.startswith("0"):
                    x = int(x)
                    y = int(y)

            if x == y:
                continue
            if x > y and comparison_operator in ('GT', 'GE') or \
                    x < y and comparison_operator in ('LT', 'LE'):
                return True
            return False

        # If the numbers of the same length are equal
        if len_x_version_array > len_min and comparison_operator in ('GT', 'GE') or \
                len_y_version_array > len_min and comparison_operator in ('LT', 'LE'):
            return True
        return False
