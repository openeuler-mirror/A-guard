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
    OscError,
    ProjectNameError,
)
from api import Api

from core import (
    ProcessRecords,
    extract_repo_pull,
    ProjectMapping,
    get_test_project_name,
)
from core.pull_link import Pull
from retrying import RetryError


def catch_error(func):
    def warp(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (
            RetryError,
            AttributeError,
            IndexError,
            TypeError,
            RuntimeError,
            KeyError,
        ) as error:
            raise RuntimeError(f"An error occurred while building the package {error}")

    return warp


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


class ObsBuildVerify(BuildMeta):
    """
    Package build check
    """

    src_openeuler_ulr = "https://gitee.com/src-openeuler"

    def __init__(
        self,
        pull_request,
        target_branch,
        arch,
        multiple,
        ignore=False,
        account=None,
        password=None,
    ) -> None:
        super(ObsBuildVerify).__init__()
        self.account = account or config.build_env_account
        self.password = password or config.build_env_passwd
        self.api = OpenBuildService(account=self.account, password=self.password)
        self.pull = Pull()
        self.gitee = Gitee()
        self.test_branch = ""
        self.arch = arch
        self.p_project = ProjectMapping()
        self.origin_package, self.pr_num = extract_repo_pull(pull_request)
        self.target_branch = target_branch
        self.multiple = multiple
        self.ignore = ignore
        if not all([self.account, self.password, self.origin_package, self.pr_num]):
            raise RuntimeError(
                "Please check whether the path, account and password of obs are fully configured,\
                    Failed to get PR information"
            )

    @staticmethod
    def project_config(project_name):
        """
        Get the project's project_config
        Args:
            project_name: project name
        Returns:
            content: Project configuration dictionary
        """
        try:
            yaml_path = (
                Path(__file__).parents[1].joinpath("conf", "project_config.yaml")
            )
            with open(yaml_path, encoding="utf-8") as file:
                content = yaml.load(file.read(), Loader=yaml.FullLoader)
                return content.get(project_name)
        except (FileNotFoundError, yaml.YAMLError) as error:
            logger.error(f"failed get project_config.yaml {error}")
            raise RuntimeError("data write yaml error")

    @staticmethod
    def _mkdir_osc_path():
        """
        Prepare the required folder for the osc command
        Raises:
            OscError: osc command fails
        """
        try:
            os.makedirs(OSC_CO_PATH, exist_ok=True)
        except PermissionError:
            raise OscError("Makedirs permission error: {OSC_CO_PATH}")

    def _get_packiage_service(self, find_patch, package):
        """
        Get the service of the original package
        Args:
            find_patch: Folder name
            package: package name 

        Raises:
            OscError: osc command fails
        """
        _ = os.path.isdir(os.path.join(OSC_CO_PATH, find_patch)) and shutil.rmtree(
            os.path.join(OSC_CO_PATH, find_patch)
        )
        cmds = ["osc", "co", find_patch, package]
        logger.info("osc co %s %s", find_patch, package)
        ret, _, _ = command(cmds, cwd=os.path.join(OSC_CO_PATH))

        if ret:
            raise OscError(
                f"Failed to get the service file of the package {package} under the {find_patch} branch"
            )

    def branch_package(self, find_repo, package):
        """
        Branch the parent project's package to the test project
        Args:
            find_repo: parent project name
            package: package name
        Raises:
             BranchPackageError: branch package error
        """

        branch_package_result = self.api.branch_package(
            project=find_repo, package=package, target_project=self.test_branch
        )
        if branch_package_result.get("status") == "failed":
            raise BranchPackageError(f"{package} branch error")

    def delete_project_package(self, project, package):
        """
        Remove packages from subprojects
        Args:
            project: project name
            package: package name

        Raises:
            DeletePackageError: failed to delete package in project
        """
        delete_package_result = self.api.del_project(project=project, package=package)
        if delete_package_result.get("status") == "failed":
            raise DeletePackageError(f"{package} delete error")

    def delete_package_from_project(self, project, exists_packages=list()):
        """
        Remove a specific package in a subproject
        Args:
            project: package name
            exists_packages: Packages that already exist in the project
        """
        packages = self.api.get_package_info(project=project)
        if exists_packages:
            packages = [
                relation_package
                for relation_package in exists_packages
                if relation_package in packages[:]
            ]
        for pkg in packages:
            if pkg:
                self.delete_project_package(project=project, package=pkg)

    def test_project_meta(self, find_branch, repositorys):
        """
        concatenated dictionary used to fill into the meta file of the project to create a new project
        Args:
            find_branch: project name
            repositorys: Archived repositories

        Returns:
            project_meta: Project meta configuration
        """
        project_meta = {
            "repository": [
                {
                    "path": repositorys
                    if repositorys
                    else {find_branch: f"standard_{self.arch}"},
                    "name": f"standard_{self.arch}",
                    "arch": self.arch,
                }
            ],
            "project": self.test_branch,
            "title": "Branch project for package",
            "description": "This project was created for package",
            "person": {"userid": self.api.account},
            "publish": "disable",
        }
        return project_meta

    def find_repo(self, package):
        """
        find the OBS branch that the REPO repository belongs to
        Args:
            package: pcakage name

        Returns:
            branch: branch name eg:"openEuler:Mainline"
        """
        obs_branch = self.p_project.branch_project(self.target_branch)
        for branch in obs_branch:
            if self.api.get_package_meta(branch, package):
                logger.info(f"This package {package} is under the project {branch}")
                return branch
        return False

    def query_project_state(self, project):
        """
        Query the build status of software packages every five seconds
        Args:
            project: project name

        Returns:
            project_results: Build information for all packages under the project
        """
        package_build_statuses = ["succeeded", "failed", "unresolvable", "excluded"]
        package_buid_result = ["building"]
        project_results = list()
        logger.info(
            f"http://117.78.1.88/project/show/{project} Package is building, please wait......."
        )
        while package_buid_result:
            time.sleep(5)
            project_results = self.api.get_project_build_state(project)
            package_buid_result = [
                package_result.get("result")
                for package_result in project_results
                if package_result.get("result") not in package_build_statuses
            ]
        package_build_results = list()
        for project_result in project_results[:]:
            # Query the build time of a package
            if project_result.get("result") == "excluded":
                logger.info(
                    f"package {project_result.get('package')} state is excluded"
                )
                build_time = 0
            else:
                build_time = self.api.package_build_time(
                    project,
                    project_result.get("arch"),
                    project_result.get("package"),
                    project_result.get("result"),
                )
            package_state = (
                "success"
                if project_result.get("result") == "succeeded"
                else "excluded"
                if project_result.get("result") == "excluded"
                else "failed"
            )

            project_result.update(build_time=build_time, result=package_state)
            package_build_results.append(project_result)
        logger.info(f"The result of the package build is: {package_build_results}")
        return package_build_results

    def get_project_repository(self, branch_meta):
        """
        Get the repository of the parent project
        Args:
            find_branch: project name

        Returns:
            repository: project repository
        """
        _repository = dict()
        for _res in (
            branch_meta.get("detail", dict())
            .get("repository", dict())
            .get(self.arch, list())
        ):
            _repository.update(_res)
        return _repository

    def epol_branch_map(self):
        """
        eopl branch map
        Returns:
            epol_branch_map: Corresponding epol branch name
        """
        return self.p_project.branch_project(self.target_branch)[0]

    def _put_project_config(self, find_branch, choose_all=False):
        """
        modify the configuration of the project
        Args:
            find_branch (_type_): _description_

        Raises:
            CreateProjectError: _description_

        """
        get_config = ""
        if choose_all:
            if self.target_branch == "master":
                get_config = self.project_config("openEuler:Epol")
            else:
                get_config = self.api.get_project_config(self.epol_branch_map())
        else:
            if self.target_branch == "master" and find_branch in MAINLINE_PROJECT_NAMES:
                get_config = self.api.get_project_config("openEuler:Mainline")
            elif self.target_branch == "master" and find_branch == "openEuler:Epol":
                get_config = self.project_config("openEuler:Epol")
            elif self.target_branch == "master" and find_branch == "openEuler:Factory":
                get_config = self.project_config("openEuler:Factory")
            else:
                get_config = self.api.get_project_config(find_branch)
        put_config = self.api.put_project_config(self.test_branch, get_config)
        if put_config.get("status") == "failed":
            raise CreateProjectError(
                f"Failed to modify the {find_branch} project configuration"
            )

    def _get_project_repositorys(self, find_branch, choose_all=False):
        """
        Get the project's repositorys
        Args:
            find_branch: Find the branch name
            choose_all (bool, optional): Whether to get the most fetched configuration for the current branch. 
                        Defaults to False.
        Returns:
            repositorys: Project's meta, The project's meta, meta and repositorys serve the same purpose
        """
        if choose_all:
            if self.target_branch == "master":
                repositorys = self.p_project.project_repository(
                    "openEuler:Epol", self.arch
                )
            else:
                repositorys = self.get_project_repository(
                    self.api.project_meta(self.epol_branch_map())
                )
            return repositorys
        else:
            if self.target_branch == "master" and find_branch == "openEuler:Factory":
                repositorys = self.p_project.project_repository(find_branch, self.arch)
            elif self.target_branch == "master" and find_branch == "openEuler:Epol":
                repositorys = self.p_project.project_repository(find_branch, self.arch)
            elif (
                self.target_branch == "master" and find_branch in MAINLINE_PROJECT_NAMES
            ):
                repositorys = self.p_project.project_repository(
                    "openEuler:Mainline", self.arch
                )
            else:
                repositorys = self.get_project_repository(
                    self.api.project_meta(find_branch)
                )
            return repositorys

    def create_project(self, find_branch):
        """
        If the target project is found, the branch will be pulled from the target project.
        If not, the epoL project will be created under the TARGET Gitee project corresponding to the OBS project.
        After the branch is pulled, the warehouse will be deleted
        Args:
            find_branch (str): The target project name , or None if not found
        Returns:
            find_branch: The target project name , or None if not found
            create_project_result: create project result
        """
        find_branch = find_branch if find_branch else self.epol_branch_map()
        repositoryes = self._get_project_repositorys(find_branch)
        create_project_result = self.api.modify_project_meta(
            self.test_branch,
            self.test_project_meta(find_branch, repositoryes),
        )
        self._put_project_config(find_branch)
        self.delete_package_from_project(self.test_branch)
        return find_branch, create_project_result

    def copy_pr_osc(self, origin_package, branch_name):
        """
        Copy the new package to the local repo repository

        Args:
            origin_package: origin package name
            branch_name: Subproject name

        Returns:
           cp_code: cp operated code
           cp_error: cp operated error message
        """
        git_local_path = os.path.join(os.path.join(GIT_FETCH, origin_package))
        cp_code, _, cp_error = command(
            ["cp", "-r", git_local_path, os.path.join(OSC_CO_PATH, branch_name)]
        )
        return cp_code, cp_error

    def osc_add_package(self, origin_package, branch_name):
        """
        Upload a new package using the OSC
        Args:
            origin_package: The package name
            branch_name: Branch name

        Returns:
            ci_code, ci_error: osc upload result
        """
        osc_path = os.path.join(OSC_CO_PATH, branch_name)
        command(
            ["osc", "add", origin_package], cwd=os.path.join(OSC_CO_PATH, branch_name)
        )
        ci_code, _, ci_error = command(
            ["osc", "ci", "-m", f"new repo {origin_package} commit"], cwd=osc_path
        )
        return ci_code, ci_error

    def _handle_package_meta(self, find_branch, origin_package):
        """
        _service file reorganisation

        <services>
            <service name="tar_scm_kernel_repo">
                <param name="scm">repo</param>
                <param name="url">next/openEuler/perl-Archive-Zip</param>
            </service>
        </services>

        :param project: obs project
        :param obs_work_dir: obs working directory
        :param code_path: 代码目录
        :return: The code directory
        """
        _service_file_path = os.path.join(
            OSC_CO_PATH, find_branch, origin_package, "_service"
        )
        tree = ElementTree.parse(_service_file_path)

        logger.info("before update meta------")
        ElementTree.dump(tree)
        sys.stdout.flush()

        services = tree.findall("service")

        for service in services:
            if service.get("name") == "tar_scm_repo_docker":
                service.set("name", "tar_local")
            elif service.get("name") == "tar_scm_repo":
                service.set("name", "tar_local")
            elif service.get("name") == "tar_scm_kernel_repo":
                service.set("name", "tar_local_kernel")
            elif service.get("name") == "tar_scm_kernels_repo":
                service.set("name", "tar_local_kernels")
            elif service.get("name") == "tar_scm":
                service.set("name", "tar_local_kernel")

            for param in service.findall("param"):
                if param.get("name") == "scm":
                    param.text = "local"
                elif param.get("name") == "tar_scm":
                    param.text = "tar_local"
                elif param.get("name") == "url":
                    if (
                        "openEuler_kernel" in param.text
                        or "LTS_kernel" in param.text
                        or "openEuler-kernel" in param.text
                        or "openEuler-20.09_kernel" in param.text
                    ):
                        param.text = "{}/{}".format(
                            GIT_FETCH, "code"
                        )  # kernel special logical
                    else:
                        gitee_repo = re.sub(r"\.git", "", param.text.split("/")[-1])
                        param.text = "{}/{}".format(GIT_FETCH, gitee_repo)

        logger.info("after update meta------")

        ElementTree.dump(tree)
        sys.stdout.flush()
        tree.write(_service_file_path)

    def _prepare_build_environ(self, find_branch, package_name):
        """
        Preparing the obs build environment
        :param project: The obs project
        :param obs_work_dir: The obs working directory
        :return:
        """
        _process_perl_path = os.path.join(
            os.path.dirname(__file__), "process_service.pl"
        )
        _service_file_path = os.path.join(
            OSC_CO_PATH, find_branch, package_name, "_service"
        )
        _git_package_path = os.path.join(GIT_FETCH, package_name)
        cmds = [
            "perl",
            _process_perl_path,
            "-f",
            _service_file_path,
            "-p",
            find_branch,
            "-m",
            package_name,
            "-w",
            _git_package_path,
        ]
        ret, _, _ = command(cmds=cmds)
        if ret:
            logger.error("prepare build environ error, %s", ret)
            raise OscError("prepare build environ error")

    def upload_pr_code_project(
        self, find_branch, src_openeuler_ulr, origin_package, pr_num, branch_name
    ):
        """
        Pull the new code, upload it to the test project, and query the compile status
        src_openeuler_ulr origin_package pr_num origin_package
        Args:
            find_branch: find obs project
            src_openeuler_ulr: src openeuler url
            origin_package: package name 
            pr_num: pr number
            branch_name: _description_

        Raises:
            BranchPackageError: _description_
            OscError: _description_
        """
        self._mkdir_osc_path()
        self._get_packiage_service(find_branch, origin_package)
        logger.info("Start fetching newly submitted pr code, please wait.....")
        if origin_package == "kernel":
            self.pull.download_kernel_repo_of_tag(
                pr_num, f"{src_openeuler_ulr}/{origin_package}", origin_package
            )
        else:
            if not self.pull.fetch_pull(
                f"{src_openeuler_ulr}/{origin_package}", pr_num, origin_package
            ):
                raise BranchPackageError("failed to pull latest package")
        self._handle_package_meta(find_branch, origin_package)
        self._prepare_build_environ(find_branch, origin_package)
        co_code, _, co_error = command(["osc", "co", branch_name], cwd=OSC_CO_PATH)
        cp_code, cp_error = self.copy_pr_osc(origin_package, branch_name)
        osc_package_path = os.path.join(OSC_CO_PATH, branch_name, origin_package)
        _ = [
            shutil.rmtree(os.path.join(osc_package_path, files))
            for files in os.listdir(osc_package_path)[:]
            if os.path.isdir(os.path.join(osc_package_path, files))
        ]
        ci_code, ci_error = self.osc_add_package(origin_package, branch_name)
        _ = [
            os.path.isdir(path) and shutil.rmtree(path)
            for path in [OSC_CO_PATH, GIT_FETCH][:]
        ]
        if any([co_code, co_error, cp_code, cp_error, ci_code, ci_error]):
            raise OscError(
                f"An error occurred while using the osc command: {co_error} {cp_error} {ci_error}"
            )

    def get_relation_link(self, pr_number, repo, test_branch, exist_packages=None):
        """
        Upload the related PR to the test project
        Args:
            pr_number: package pr number
            repo: repo 
            test_branch: test branch name 
            exist_packages: Test the packages that already exist under the project. Defaults to None.

        Returns:
            relation_prs: relation package pr
        """
        if exist_packages is None:
            exist_packages = []
        relation_prs = list()
        relations = self.pull.relation_verify(pr_number, repo)
        for relation_pr in relations.get("be_link_pr", list()):
            if relation_pr["package"] in exist_packages:
                self.api.del_project(self.test_branch, relation_pr["package"])
            find_branch = self.find_repo(relation_pr["package"])
            if find_branch:
                self.upload_pr_code_project(
                    self.src_openeuler_ulr,
                    relation_pr["package"],
                    relation_pr["pull"],
                    test_branch,
                )
                relation_prs.append(relation_pr["package"])
        return relation_prs

    def build_prep_single(self, find_branch):
        """
        single package build
        Args:
            find_branch: Package presence obs project
        """
        
        self.test_branch = get_test_project_name(self.origin_package, self.pr_num)
        find_branch, create_project_result = self.create_project(find_branch)
        if create_project_result.get("status") == "failed":
            raise CreateProjectError(f"{self.test_branch} test project creation failed")
        self.upload_pr_code_project(
            find_branch,
            self.src_openeuler_ulr,
            self.origin_package,
            self.pr_num,
            self.test_branch,
        )
        # Single package compilation result query
        package_build_results = self.query_project_state(self.test_branch)
        _ = [
            logger.info(f"package build results {package_build_result}")
            for package_build_result in package_build_results
        ]
        # Change the configuration of the test project Get all binary archives
        if self.target_branch != "master" or (
            self.target_branch == "master" and find_branch != "openEuler:Factory"
        ):
            full_configuration_project = self.epol_branch_map()
            repositorys = self._get_project_repositorys(
                full_configuration_project, choose_all=True
            )
            self.api.modify_project_meta(
                self.test_branch,
                self.test_project_meta(full_configuration_project, repositorys),
            )
            self._put_project_config(self.test_branch, choose_all=True)
        relation_prs = self.get_relation_link(
            self.pr_num, self.origin_package, self.test_branch
        )
        if relation_prs:
            return self.query_project_state(self.test_branch)
        return package_build_results

    def build_prep_multi(self, depend_list, find_branch):
        """
        Multiple package build
        Args:
            depend_list: Dependent packages
            find_branch: find_branch

        Raises:
            ProjectNameError: Test project does not exist

        Returns:
            package_states: Package build results
        """
        self.test_branch = get_test_project_name(self.origin_package, self.pr_num)
        project_meta_response = self.api.project_meta(project=self.test_branch)
        if project_meta_response.get("status") == "failed":
            logger.error("fail to find test branch!")
            raise ProjectNameError(f"fail to find test branch!")
        exist_packages = self.api.get_package_info(project=self.test_branch)
        relation_prs = self.get_relation_link(
            pr_number=self.pr_num,
            repo=self.origin_package,
            test_branch=self.test_branch,
            exist_packages=exist_packages,
        )
        logger.info(f"{self.test_branch} packages: {exist_packages}")
        exist_packages.extend(relation_prs)
        exist_packages = list(set(exist_packages))
        for depend_pkg in depend_list[:]:
            if depend_pkg in exist_packages:
                continue
            find_repo = self.find_repo(depend_pkg)
            if not find_repo:
                logger.error(f"fail to find package {depend_pkg}")
                continue
            if (
                self.target_branch == "master"
                and find_branch != "openEuler:Factory"
                and find_repo == "openEuler:Factory"
            ):
                logger.info(
                    f"This dependent package {depend_pkg} is in openEuler:Factory, please analyze it yourself"
                )
                continue
            try:
                self.branch_package(find_repo=find_repo, package=depend_pkg)
            except BranchPackageError:
                logger.error(f"branch {find_repo} {depend_pkg} failed")
        package_states = self.query_project_state(self.test_branch)
        # Checking the status of the last package build
        for package_state in package_states:
            if package_state.get("result") != "success":
                find_repo = self.find_repo(package_state.get("package"))
                if not find_repo or not self.api.build_package_lastlog(
                    find_repo,
                    package_state.get("package"),
                    package_state.get("arch"),
                ):
                    logger.error(
                        f"{package_state.get('package')}: The build result of the last package was"
                        f" not obtained, or the build result failed"
                    )
        return package_states

    def multi_data_combination(self, build_results):
        """
        Multiple package compilation result reorganisation
        Args:
            build_results: package build result 

        Returns:
            package_build_results: Reassembled package compilation results
        """
        package_build_results = dict()
        for sig_build_result in build_results:
            package_committer = self.gitee.package_committer(
                [sig_build_result.get("package")]
            )
            package_build_results.update(
                {
                    sig_build_result.get("package"): {
                        "build_result": sig_build_result.get("result"),
                        "log_url": sig_build_result.get("log_url"),
                        "commitor": package_committer.get(
                            sig_build_result.get("package")
                        ),
                    }
                }
            )
        return package_build_results

    @catch_error
    def build(self):
        """
        Package build
        a single source package or a list of multiple source packages
        Raises:
            ProjectNameError: Project Name Error

        Returns:
            result of build:
        """
        process_record = ProcessRecords(self.origin_package, self.pr_num)
        if not self.p_project.branch_project(self.target_branch):
            raise ProjectNameError(
                f"given branch name {self.target_branch} wrong,please check again!"
            )
        find_branch = self.find_repo(self.origin_package)
        if not find_branch:
            raise RuntimeError("The package is not in the obs project, please add this package to the obs project first")
        if self.multiple:
            depend_list, _ = process_record.depend()
            build_results = self.build_prep_multi(depend_list, find_branch)
            package_build_results = self.multi_data_combination(build_results)
            steps = "multi_build_check"
        else:
            package_build_results = self.build_prep_single(find_branch)
            steps = "single_build_check"
        current_result = "success"
        result_field, package_build_resultes = (
            ("build_result", list(package_build_results.values()))
            if isinstance(package_build_results, dict)
            else ("result", package_build_results)
        )
        for package_build_result in package_build_resultes:
            if package_build_result.get(result_field) not in ["success", "excluded"]:
                current_result = "failed"
                break
        check_result = dict(
            build_detail=package_build_results, current_result=current_result
        )
        process_record.update_check_options(steps=steps, check_result=check_result)
        return check_result
