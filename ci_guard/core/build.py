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
# ******************************************************************************/#!/usr/bin/python3
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

import datetime
import itertools
import os

import sys
import re
import shutil
import yaml
import time
import uuid
import datetime
import json
from xml.etree import ElementTree
from logger import logger
from abc import ABCMeta, abstractmethod
from pathlib import Path
from api.build_env import OpenBuildService
from api.gitee import Gitee
from command import command
from conf import config
from .install import UnifyBuildInstallVerify

from core import ProcessRecords, extract_repo_pull
from command import command
from retrying import RetryError
from contextlib import contextmanager
from json import JSONDecodeError
from core.pull_link import Pull

from retrying import retry

from constant import GIT_FETCH, MAINLINE_PROJECT_NAMES, OS_VARIANR_MAP, OSC_CO_PATH
from exception import (
    BranchPackageError,
    CreateProjectError,
    DeletePackageError,
    ModifyProjectError,
    OscError,
    ProjectNameError,
)
from api import Api

from core import ProcessRecords, extract_repo_pull
from core.pull_link import Pull
from retrying import RetryError


class BuildMeta(metaclass=ABCMeta):
    @abstractmethod
    def build(self):
        pass

    @abstractmethod
    def build_prep_single(self):
        pass

    @abstractmethod
    def build_prep_multi(self):
        pass


class EbsBuildVerify(BuildMeta):
    def __init__(
        self, pull_request, target_branch, arch, multiple, ignore=False
    ) -> None:
        super(EbsBuildVerify).__init__()
        self.pull_request = pull_request
        self.target_branch = target_branch
        self.arch = arch
        self.multiple = multiple
        self.ignore = ignore
        self.pull = Pull()
        self.api = Api()
        self.origin_package, self.pr_num = extract_repo_pull(pull_request)

    @property
    def test_project_name(self):
        """
        Name of test project
        Returns:
            test_project_name: name of test project
        """
        return f"{self.target_branch}:{self.arch}:{self.origin_package}:{self.pr_num}"

    def create_projrct(self):
        """
        Create a test project
        """
        base_dict = self.dict_data_constitute(
            self.origin_package, pr_id=self.pr_num, my_spec_type="my_specs"
        )
        os_variant_name = (
            OS_VARIANR_MAP.get(self.target_branch)
            if OS_VARIANR_MAP.get(self.target_branch)
            else "openEuler:22.09"
        )
        base_dict.update(
            {
                "spec_branch": self.target_branch,
                "build_targets": [
                    {"os_variant": os_variant_name, "architecture": self.arch}
                ],
            }
        )
        self.operate_package_project(base_dict, operate="create")

    @staticmethod
    def _combine_data_json_path():
        """
        The json file path
        """
        return str(Path(__file__).parents[0].joinpath(f"{str(uuid.uuid1().hex)}.json"))

    @retry(stop_max_attempt_number=3, wait_fixed=6000)
    def _command_result(self, cmds):
        """
        Execute the ccb command and return the result
        Args:
            cmds: The ccb command that needs to be executed

        Raises:
            RuntimeError: The command execution failed and an exception was thrown
        Returns:
            response: After json.loads, return the data
        """
        code, output, error = command(cmds, console=False)
        try:
            response = json.loads(output)
            if isinstance(response, list):
                response = {"code": "0", "data": response, "msg": None}
            elif not code and response.get("code") in [0, 4013]:
                logger.info(
                    f"{' '.join(cmds)} command execute success: {response.get('msg') or response.get('data')}"
                )
            else:
                raise RuntimeError(f"{cmds} command execute failed  {output}")
        except JSONDecodeError as error:
            raise RuntimeError(
                f"{cmds} command, return json data {output} is wrong,{error}"
            )
        return response

    @contextmanager
    def update_package_operation(self, data, cmds, file_path):
        """
        Using the context mechanism, write the data to the json file,
        execute the command, and finally delete the file
        Args:
            data: After the combined data, you need to write to the json file
            cmds: The ccb command that needs to be executed
            file_path: The json file path
        """
        with open(file_path, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4)
        try:
            yield self._command_result(cmds)
        except TypeError as error:
            raise RuntimeError(f"{cmds} command execution failure,because {error}")
        finally:
            if Path(file_path).is_file():
                Path(file_path).unlink()

    def operate_package_project(self, content, operate="update"):
        """
        Update the packages under the project
        Args:
            content: After the combination is completed, the data is sent
            operate: The operations that need to be performed on the project Defaults to "update".

        Raises:
            RuntimeError: _description_
        """
        _json_path = self._combine_data_json_path()
        operate_project_cmds = [
            "ccb",
            operate,
            "projects",
            self.test_project_name,
            "--json",
            _json_path,
        ]

        try:
            with self.update_package_operation(
                content, operate_project_cmds, _json_path
            ) as response:
                logger.info(f"{response.get('data') or response.get('msg')}")
        except (TypeError, OSError, IOError, PermissionError) as error:
            raise RuntimeError(f"Failed to update project, because {error}")

    def trigger_build(self, package_name=None):
        """
        Trigger the compilation of single or all software under the project
        Args:
            package_name: The package that needs to trigger the compilation is required Defaults to None.

        Returns:
            build_id: Triggers the compiled build_id
        """
        base_trigger_build_cmds = [
            "ccb",
            "build-single" if package_name else "build",
            f"os_project={self.test_project_name}",
            f"packages={package_name}" if package_name else "build_type=full",
        ]
        output = self._command_result(base_trigger_build_cmds)
        return list(output.get("data").keys())

    def dict_data_constitute(self, spec_name, pr_id=None, my_spec_type="my_specs+"):
        """
        Combine the data that needs to be written to the json file
        Args:
            spec_name: The name of the package
            pr_id: pr id. Defaults to None.
            my_spec_type: Upload or delete packages under a test project. Defaults to "my_specs+".

        Returns:
            base_dict: Dictionary data after combination
        """
        base_dict = {
            my_spec_type: [
                {
                    "spec_name": spec_name,
                    "spec_url": f"https://gitee.com/{config.warehouse_owner}/{spec_name}.git",
                    "spec_branch": self.target_branch,
                }
            ]
        }
        base_dict.update(
            package_overrides={spec_name: {"pr_id": pr_id}}
        ) if pr_id else base_dict
        return base_dict

    def _package_build_time(self, close_time, boot_time):
        """
        Calculates the compilation time of the package
        Args:
            close_time: build end time
            boot_time: build start time

        Returns:
            build_time: The build time of the package
        """
        build_time = 0
        try:
            boot_time = datetime.datetime.strptime(boot_time, "%Y-%m-%dT%H:%M:%S+0800")
            close_time = datetime.datetime.strptime(
                close_time, "%Y-%m-%dT%H:%M:%S+0800"
            )
            build_time = (close_time - boot_time).seconds
        except TypeError as error:
            logger.error(f"{boot_time} {close_time} Time parsing failed {error}")
        return build_time

    def query_project_detail_result(self, build_detail, build_id):
        """
        Query the compilation result of the package (log address and compilation time)
        Args:
            build_detail: package build detail
            build_id: triger build id

        Returns:
            final_build_detail_results: final package build detail results
        """

        query_project_detail_cmds = [
            "ccb",
            "select",
            "jobs",
            f"build_id={build_id[0]}",
            "-f",
            "spec_name,close_time,boot_time,id",
        ]
        build_detail_results = self._command_result(query_project_detail_cmds)
        # Data combinations
        final_build_detail_results = list()

        for _build_detail, build_detail_result in itertools.product(
            build_detail, build_detail_results["data"]
        ):
            if _build_detail["package"] == build_detail_result["_source"].get(
                "spec_name"
            ):
                job_id = build_detail_result["_source"].get("id")
                _build_detail[
                    "log_url"
                ] = f"{config.ebs_server}/package/build-record?osProject={self.test_project_name}&packageName={_build_detail['package']}&jobId={job_id}"
                _build_detail["build_time"] = self._package_build_time(
                    build_detail_result["_source"].get("close_time"),
                    build_detail_result["_source"].get("boot_time"),
                )
                final_build_detail_results.append(_build_detail)

        # update repo
        logger.info("Start updating the repo source......")
        unifybuild = UnifyBuildInstallVerify()
        if not unifybuild.update_repo(build_id[0]):
            return final_build_detail_results
        # Record the build id in the configuration file
        self._record_build_id(build_id[0])
        return final_build_detail_results

    def get_relation_link(self, pr_number, repo):
        """
        Upload the related PR to the test project
        link_pr:[ //
                {
                    "status":"merge",
                    "package:"rpmA",
                    "pull":"1"
                }
            ],
            be_link_pr:[ //
                {
                    "status":"merge",
                    "package:"rpmA",
                    "pull":"1"
                }
            ]
        """
        relation_prs = list()
        relations = self.pull.relation_verify(pr_number, repo)
        for relation_pr in relations.get("be_link_pr", list()):
            # Upload the package
            if not self._check_warehouse_exists(relation_pr.get("package")):
                logger.info(
                    f"This {relation_pr.get('package')} repository does not exist"
                )
                continue
            self.operate_package_project(
                content=self.dict_data_constitute(
                    relation_pr.get("package"),
                    pr_id=relation_pr.get("pull"),
                )
            )
            relation_prs.append(relation_pr.get("package"))
        return relation_prs

    def query_build_project_result(self, build_id):
        """
        Query the compilation results of the package
        package build code interpretation:
                JOB_BLOCKED = 100 # build
                JOB_BUILDING = 101 # build
                JOB_SIGNING = 102 # build
                JOB_SUCCESS = 103 # build/install
                JOB_FAILED = 104 # build/install
                JOB_UNRESOLVABLE = 105 # build/install
                JOB_EXCLUDED = 106 # build/install
                JOB_ABORTED = 107 # build
                JOB_UNKNOWN = 108 # install
                JOB_CYCLE_SUCCESS = 109 # build/install
                JOB_CYCLE_FAILED = 110 # build/install
                JOB_FINAL = [JOB_SUCCESS, JOB_FAILED, JOB_EXCLUDED, JOB_ABORTED]
        project build code interpretation:
                BUILD_BUILDING = 200
                BUILD_SUCCESS = 201
                BUILD_FAILED = 202
                BUILD_ABORTED = 203
                BUILD_BLOCKED = 204
                BUILD_EXCLUDED = 205
        Args:
            build_id: triger build id
        Returns:
            build_detail: package build detail
        """
        query_build_project_cmds = [
            "ccb",
            "select",
            "builds",
            f"build_id={build_id[0]}",
            "-f",
            "status,build_packages",
        ]
        package_build_status_stop, project_build_status_stop = [
            103,
            104,
            105,
            106,
            107,
        ], [201, 202, 203, 205]
        package_statuses, project_statuses = [101], [200]
        logger.info("The packages under the project are  building, please wait...")
        build_detail = []
        while package_statuses or project_statuses:
            time.sleep(10)
            package_statuses = list()
            build_project_result = self._command_result(query_build_project_cmds)
            for build_packages in build_project_result["data"]:
                for _detail in (
                    build_packages.get("_source", {}).get("build_packages", {}).values()
                ):
                    if (
                        _detail.get("build", {}).get("status", 101)
                        not in package_build_status_stop
                    ):
                        package_statuses.append(
                            _detail.get("build", {}).get("status", 101)
                        )
            project_statuses = [
                _result["_source"].get("status")
                for _result in build_project_result["data"]
                if _result["_source"].get("status") not in project_build_status_stop
            ]
        for build_packages in build_project_result["data"]:
            for build_package, _detail in (
                build_packages.get("_source", {}).get("build_packages", {}).items()
            ):
                if _detail.get("build", {}).get("status") in [103, 109]:
                    resulte = "success"
                elif _detail.get("build", {}).get("status") in [
                    104,
                    105,
                    107,
                    108,
                    110,
                ]:
                    resulte = "failed"
                elif _detail.get("build", {}).get("status") == 106:
                    resulte = "exclude"
                else:
                    resulte = "unknown"
                build_detail.append(
                    {
                        "package": build_package,
                        "arch": self.arch,
                        "result": resulte,
                    }
                )
        logger.info("Full compilation results completed")
        return build_detail

    def get_project_packages(self, spec_type):
        """
        Get all packages under the project
        Args:
            spec_type: The key value of the information that needs to be obtained

        Returns:
            exist_packages: all package
        """
        project_packages_cmds = [
            "ccb",
            "select",
            "projects",
            self.test_project_name,
            "-f",
            "my_specs",
        ]
        out_put = self._command_result(project_packages_cmds)
        exist_packages = list()
        for _put in out_put["data"]:
            for package in _put.get("_source", {}).get("my_specs", []):
                exist_packages.append(package.get(spec_type))
        return exist_packages

    def clear_project(self):
        """
        Delete all packages under the test project
        """
        spec_names = self.get_project_packages("spec_name")
        if not spec_names:
            logger.info("There are no packages under this repository")
            return
        content = {
            "my_specs-": [
                {
                    "spec_name": spec_name,
                    "spec_url": f"https://gitee.com/{config.warehouse_owner}/{spec_name}.git",
                }
                for spec_name in spec_names
            ]
        }
        self.operate_package_project(content)

    def _record_build_id(self, build_id):
        """
        record build id
        Args:
            build_id: trigger build id

        Raises:
            RuntimeError: Throw a record id exception
        """
        try:
            yaml_path = Path(__file__).parents[1].joinpath("config.yaml")
            with open(yaml_path, encoding="utf-8") as file:
                content = yaml.load(file.read(), Loader=yaml.SafeLoader)
                content["build_id"] = build_id
            with open(yaml_path, "w", encoding="utf-8") as f:
                yaml.dump(data=content, stream=f, allow_unicode=True)
        except (FileNotFoundError, yaml.YAMLError) as error:
            raise RuntimeError(f"data write yaml error {error}")

    def _check_warehouse_exists(self, package_name):
        """
        Check whether the warehouse exists
        Args:
            package_name: package_name

        Returns:
            True or False: Presence returns true Non-existent returns false
        """
        if self.api._get(
            f"https://gitee.com/{config.warehouse_owner}/{package_name}", text=True
        ):
            return True
        return False

    def build_prep_single(self):
        """
        Single-package build process
        Raises:
            RuntimeError: The package triggered compilation failure

        Returns:
            packages_build_results: packages build results
        """
        # Determine if a repository exists
        if not self._check_warehouse_exists(self.origin_package):
            raise RuntimeError(f"This {self.origin_package} repository does not exist")
        logger.info("[INFO] create_projrct")
        self.create_projrct()
        # 2. Empty the project
        logger.info("[INFO] clear_project")
        self.clear_project()
        # 3. Upload the pr package
        logger.info("[INFO] Upload the pr package")
        self.operate_package_project(
            content=self.dict_data_constitute(self.origin_package, pr_id=self.pr_num)
        )
        # 4. Upload pr link package
        relation_prs = self.get_relation_link(self.pr_num, self.origin_package)
        # 5. Triggers build
        build_id = (
            self.trigger_build()
            if relation_prs
            else self.trigger_build(package_name=self.origin_package)
        )
        if not build_id:
            raise RuntimeError("build error")
        # 6. Wait for the build result, wait for the build
        build_detail = self.query_build_project_result(build_id)

        # 7. build the details result query
        packages_build_results = self.query_project_detail_result(
            build_detail, build_id
        )

        return packages_build_results

    def build_prep_multi(self, depend_list):
        """
        Multi-package build
        Args:
            depend_list: a list of dependent packages

        Raises:
            RuntimeError: The package triggered build failure

        Returns:
            build_detail: package build result
        """
        # Get all packages under the project
        exist_packages = self.get_project_packages("spec_name")
        # Upload the pr link package
        relation_prs = self.get_relation_link(
            pr_number=self.pr_num,
            repo=self.origin_package,
        )
        finally_exist_packages = list(set(sum([exist_packages, relation_prs], [])))
        for depend_pkg in depend_list:
            if depend_pkg in finally_exist_packages:
                continue
            else:
                try:
                    if not self._check_warehouse_exists(
                        depend_pkg.replace("python3-", "python-")
                    ):
                        logger.info(f"This {depend_pkg} repository does not exist")
                        continue
                    self.operate_package_project(
                        content=self.dict_data_constitute(depend_pkg)
                    )
                except RuntimeError:
                    logger.error(f"{depend_pkg} upload failed")
        if not depend_list and not relation_prs:
            build_id = [config.build_id]
        else:
            build_id = self.trigger_build()
        if not build_id:
            raise RuntimeError("build error")
        build_detail = self.query_build_project_result(build_id)
        packages_results = self.query_project_detail_result(build_detail, build_id)
        build_detail = dict()
        for packages_result in packages_results:
            _result = dict(
                build_result=packages_result.get("result"),
                log_url=packages_result.get("log_url"),
            )
            build_detail.update({packages_result.get("package"): _result})
        return build_detail

    def build(self):
        """
        The package compiles the entire process
        Returns:
            check_result: The result of the entire process of package build
        """
        process_record = ProcessRecords(self.origin_package, self.pr_num)
        if self.multiple:
            depend_list, _ = process_record.depend()
            package_build_results = self.build_prep_multi(depend_list)
            steps = "multi_build_check"
        else:
            package_build_results = self.build_prep_single()
            steps = "single_build_check"
        result_field, package_build_resultes = (
            ("build_result", list(package_build_results.values()))
            if isinstance(package_build_results, dict)
            else ("result", package_build_results)
        )
        current_result_judge = any(
            package_build_result.get(result_field) not in ["success", "excluded"]
            for package_build_result in package_build_resultes
        )
        current_result = "failed" if current_result_judge else "success"
        check_result = dict(
            build_detail=package_build_results, current_result=current_result
        )
        process_record.update_check_options(steps=steps, check_result=check_result)
        return check_result
