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
import json
from api import Api
from logger import logger
from core import (
    extract_repo_pull,
    ProcessRecords,
)
from conf import config


class CheckLicense:
    """
    check package license
    """
    def __init__(self, arch) -> None:
        self._arch = arch or config.arch
        self._pull = None
        self._repo = None
        self._ebs_server = "https://eulermaker.compass-ci.openeuler.openatom.cn"
        self._license_url = "https://sbom-repo-service.test.osinfra.cn/sbom-repo-api/licenseCheck"

    def _record(self, license_results, steps):
        current_result = all(
            [
                True if license["result"] == "success" else False
                for license in license_results
            ]
        )

        setp_result = "success" if current_result else "failed"
        process_record = ProcessRecords(self._repo, self._pull)
        process_record.update_check_options(
            steps=steps,
            check_result=dict(
                license_detail=license_results, current_result=setp_result
            ),
        )
        logger.info(f"CURRENT RESULT:{current_result}")
        return current_result

    def _license_sbom(self, repo_url):
        not_allow_list = []
        unknow_list = []
        allow_list = []
        license_results = []

        data = dict(url=repo_url)
        response = Api._post(self._license_url, data, timeout=600)
        if not response:
            logger.error(response)
            logger.error(f"Failed to check_license")
            return False
        logger.info(response)

        result = response.get("result")
        if result == "FAILED":
            logger.error("result = %s", result)
            package_license_list = response.get("packageLicenseList")
            for one_lic in package_license_list:
                lic_result = one_lic.get("result")
                if lic_result == "NOT_ALLOW":
                    not_allow_list.append(one_lic)
                elif lic_result == "UNKNOW":
                    unknow_list.append(one_lic)
                else:
                    allow_list.append(one_lic)
        else:
            logger.info("result = %s", result)

        if not_allow_list:
            logger.error("not_allow_list = %s", not_allow_list)
        if unknow_list:
            logger.error("unkown_list = %s", unknow_list)
        if not_allow_list or unknow_list:
            logger.error('Check license failed, please refer to this document to handle license:'
                    '"https://gitee.com/openeuler/compliance/blob/master/doc/rectification/license-rectification.md"')
        else:
            logger.info("Check license successful.")

        license_results.append(
            dict(
                arch=self._arch,
                result=result.lower(),
            )
        )

        return self._record(license_results, "package_license_check")

    def check_license(self, pull_request):
        """
        check package license
        :param pull_request: Submitted pull links
        """
        try:
            self._repo, self._pull = extract_repo_pull(pull_request)
        except TypeError:
            logger.warning(f"Not a valid pull link: {pull_request}.")
            return
        
        # get repo_url
        repo_url = ''
        try:
            with open(
                    os.path.join(config.workspace, "ci-tools.repo"), "r", encoding="utf-8"
            ) as file:
                for line in file.readlines():
                    if line.strip().startswith("baseurl"):
                        repo_url = line.strip().split("=")[1]
                        if repo_url:
                            break
            
            repo_url = repo_url.replace(config.ebs_server, self._ebs_server) + "/" if repo_url else ""

            logger.info(repo_url)
        except IOError as error:
            logger.error(error)

        # check_license
        logger.info("Start invoke the sbom toll to check packages license")
        return self._license_sbom(repo_url)

