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

# Document process results
RECORDS_COURSE = os.path.join(PROJECT_WORK_DIR, "records-course")

# Pr Directory where the file is stored during the merge
GIT_FETCH = os.path.join(PROJECT_WORK_DIR, "pull-fetch")

# Maximum number of retries for http requests
STOP_MAX_ATTEMPT_NUMBER = 3

# The interval to wait during retry
WAIT_FIXED = 30

# Location for saving the downloaded rpm package
DOWNLOAD_RPM_DIR = os.path.join(PROJECT_WORK_DIR, "rpms")

OS_VARIANR_MAP = {"openEuler-22.03-LTS-SP1": "openEuler:22.03-LTS-Next",
                  "openEuler-22.03-LTS-SP2": "openEuler:22.03-LTS-SP2",
                  "openEuler-22.03-LTS-SP3": "openEuler:22.03-LTS-SP3",
                  "openEuler-22.03-LTS-SP4": "openEuler:22.03-LTS-SP4",
                  "openEuler-22.03-LTS-SP4-64KB": "openEuler:22.03-LTS-SP4",
                  "openEuler-22.03-LTS-Next": "openEuler:22.03-lts-next-dailybuild",
                  "openEuler-20.03-LTS-SP4": "openEuler:20.03-LTS-SP4",
                  "openEuler-24.03-LTS": "openEuler:24.03-LTS",
                  "openEuler-24.03-LTS-Next": "openEuler:24.03-LTS-Next",
                  "openEuler-24.03-LTS-SP1": "openEuler:24.03-LTS-SP1",
                  "openEuler-24.09": "openEuler:24.09",
                  "openEuler-25.03": "openEuler:25.03",
                  "openEuler-24.03-LTS-SP2": "openEuler:24.03-LTS-SP2",
                  "openEuler-25.09": "openEuler:25.09",
                  "openEuler-24.03-LTS-SP3": "openEuler:24.03-LTS-SP3",
                  "openEuler-24.03-LTS-SP4": "openEuler:24.03-LTS-SP4",
                  "openEuler-26.09": "openEuler:26.09-DevStation",
                  "openEuler-26.09-DevStation": "openEuler:26.09-DevStation",
                  "master": "openEuler:mainline"}

BOOTSTRAP_MAP = config.bootstrap_nodes or {}

# abi change effects number
max_abi_change_effects_number = 5

# max change effects number
max_change_effects_number = 20

# max random number
max_random_number = 15
