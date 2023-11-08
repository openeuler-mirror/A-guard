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
from conf import config

# Working directory
PROJECT_WORK_DIR = config.workspace

# Project local path
OSC_CO_PATH = os.path.join(PROJECT_WORK_DIR, "osc-project")

# Document process results
RECORDS_COURSE = os.path.join(PROJECT_WORK_DIR, "records-course")

# Pr Directory where the file is stored during the merge
GIT_FETCH = os.path.join(PROJECT_WORK_DIR, "pull-fetch")

# Maximum number of retries for http requests
STOP_MAX_ATTEMPT_NUMBER = 3

# The interval to wait during retry
WAIT_FIXED = 2

# Location for saving the downloaded rpm package
DOWNLOAD_RPM_DIR = os.path.join(PROJECT_WORK_DIR, "rpms")

# master L1-L4 project name
MAINLINE_PROJECT_NAMES = [
    "openEuler:Mainline",
    "openEuler:Extras",
    "openEuler:BaseTools",
    "openEuler:C",
    "openEuler:Common_Languages_Dependent_Tools",
    "openEuler:Erlang",
    "openEuler:Golang",
    "openEuler:Java",
    "openEuler:KernelSpace",
    "openEuler:Lua",
    "openEuler:Meson",
    "openEuler:MultiLanguage",
    "openEuler:Nodejs",
    "openEuler:Ocaml",
    "openEuler:Testing:Perl",
    "openEuler:Python",
    "openEuler:Qt",
    "openEuler:Ruby",
]

OS_VARIANR_MAP = {"openEuler-22.03-LTS-SP1": "openEuler:22.03-LTS-Next",
                  "openEuler-22.03-LTS-SP2": "openEuler:22.03-LTS-SP2",
                  "openEuler-22.03-LTS-SP3": "openEuler:22.03-LTS-SP3",
                  "openEuler-22.03-LTS-Next": "openEuler:22.03-lts-next-dailybuild",
                  "openEuler-20.03-LTS-SP4": "openEuler:20.03-LTS-SP4",
                  "master": "openEuler:mainline"}

BOOTSTRAP_MAP = {
        "http://192.168.137.75:20029": "ems1",
        "http://192.168.46.177:20029": "ems2",
        "http://192.168.164.96:20029": "ems3",
}

# abi change effects number
max_abi_change_effects_number = 5

# max change effects number
max_change_effects_number = 20

# max random number
max_random_number = 15
