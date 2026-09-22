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
from pathlib import Path

import yaml
from api import Api
from conf import config
from logger import logger

from core import (
    ProcessRecords,
    extract_repo_pull,
)


class CheckLicense:
    """
    check package license
    """
    def __init__(self, arch, variant=None) -> None:
        self._arch = arch or config.arch
        self._variant = variant or config.variant
        self._pull = None
        self._repo = None
        self._ebs_server = config.ebs_server
        self._license_url = f"{config.sbom_server}/sbom-repo-api/licenseCheck"
        self._exclude_repos = self._load_exclude_repos()

    @staticmethod
    def _load_exclude_repos():
        """
        Load the license exclude repository whitelist from yaml file.
        Returns:
            list: repo names, e.g. ["foo", "bar"]. Empty list if not found or error.
        """
        exclude_file = Path(__file__).parents[1].joinpath("conf", "license_exclude.yaml")
        if not exclude_file.exists():
            return []
        try:
            with open(exclude_file, encoding="utf-8") as f:
                content = yaml.safe_load(f) or {}
            repos = content.get("exclude_repos")
            return repos if isinstance(repos, list) else []
        except Exception as e:
            logger.warning(f"Failed to load license exclude file: {e}")
            return []

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
        response = Api._post(self._license_url, data, timeout=900)
        if not response:
            logger.error(response)
            logger.error("Failed to check_license")
            return False
        logger.info(response)

        result = response.get("result")
        if result is None:
            logger.error("response.get('result') returned None")
            return False
        result = result.upper()
        if result == "FAILED":
            logger.error("result = %s", result)
            package_license_list = response.get("packageLicenseList")
            for one_lic in package_license_list:
                lic_result = one_lic.get("result")
                if lic_result is None:
                    logger.error("one_lic.get('result') returned None")
                    continue
                lic_result = lic_result.upper()
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

        # 白名单仓豁免：license 检查必然失败的 repo，标注 exclude（等同通过，不阻断门禁）。
        # 仍执行真实检查：若仓库整改后检查成功，照常记录 success，豁免自动失效。
        if result == "FAILED" and self._repo in self._exclude_repos:
            logger.warning(f"Repo {self._repo} is in the license exclude whitelist, "
                           "mark license check result as exclude.")
            license_results.append(
                dict(
                    arch=self._arch,
                    result="exclude",
                )
            )
            process_record = ProcessRecords(self._repo, self._pull)
            process_record.update_check_options(
                steps="package_license_check",
                check_result=dict(
                    license_detail=license_results, current_result="exclude"
                ),
            )
            return True

        if not_allow_list or unknow_list:
            logger.error('Check license failed, please refer to this document to handle license:'
                    '"https://atomgit.com/openeuler/compliance/blob/master/doc/rectification/license-rectification.md"')
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

            logger.info(f"repo_url: {repo_url}")
        except IOError as error:
            logger.error(error)

        # check_license
        logger.info("Start invoke the sbom toll to check packages license")
        return self._license_sbom(repo_url)

