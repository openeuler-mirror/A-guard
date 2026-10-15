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
import glob
import itertools
import json
import os
import time
import uuid
from abc import ABCMeta, abstractmethod
from contextlib import contextmanager
from json import JSONDecodeError
from pathlib import Path

import yaml
from api import Api
from api.atomgit import Atomgit
from command import command
from conf import config
from constant import OS_VARIANR_MAP
from logger import logger
from retrying import RetryError, retry

from core import (
    ProcessRecords,
    extract_repo_pull,
)
from core.pull_link import Pull


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
    """
    Build abstract classes that define build methods, single-package builds, and multi-package builds
    """
    @abstractmethod
    def build(self):
        """
        Rpm package building
        """
        pass

    @abstractmethod
    def build_prep_single(self):
        """
        Single rpm build
        """
        pass

    @abstractmethod
    def build_prep_multi(self):
        """
        Multi rpm build
        """
        pass

    @staticmethod
    def _load_spec_name_mapping():
        """
        Load spec file name → actual spec package name mapping from yaml file.
        Returns:
            dict: mapping dict, e.g. {"foo": "bar"}. Empty dict if file not found or error.
        """
        mapping_file = Path(__file__).parents[1].joinpath("conf", "spec_name_mapping.yaml")
        if not mapping_file.exists():
            return {}
        try:
            with open(mapping_file, encoding="utf-8") as f:
                mapping = yaml.safe_load(f)
            return mapping if isinstance(mapping, dict) else {}
        except Exception as e:
            logger.warning(f"Failed to load spec name mapping file: {e}")
            return {}

    def _get_target_packages(self):
        """
        Get the list of package names corresponding to the .spec files changed in the PR.
        Applies spec_name_mapping.yaml to correct file names that differ from actual package names.
        Returns:
            List[str]: target package names, e.g. ["bar", "kernel-rt"]
        """
        try:
            atomgit_api = Atomgit(self.origin_package, owner=config.warehouse_owner)
            files = atomgit_api.get_pr_files(self.pr_num)
            if not files or not isinstance(files, list):
                return []
            spec_files = []
            for f in files:
                filename = f.get("filename", "")
                if filename.endswith(".spec"):
                    spec_files.append(os.path.basename(filename)[:-5])
            # Apply spec name mapping correction
            mapping = self._load_spec_name_mapping()
            if mapping:
                target_packages = [mapping.get(name, name) for name in spec_files]
                if target_packages != spec_files:
                    logger.info(
                        f"Spec name mapping applied: {spec_files} → {target_packages}"
                    )
                return target_packages
            return spec_files
        except Exception as e:
            logger.warning(f"Failed to get PR changed files: {e}")
            return []

    def _map_variant_package(self, package_name):
        """
        Map a package name to its variant package name in build results.
        Only kernel packages with a variant (e.g. 64k) are affected.
        """
        if self.origin_package == "kernel" and self.variant:
            mapping = {
                "kernel": f"kernel-{self.variant}",
                "kernel-rt": f"kernel-rt-{self.variant}b",
            }
            return mapping.get(package_name, package_name)
        return package_name

    def filter_by_changed_specs(self, package_build_results):
        """
        Filter build results to only include packages corresponding to
        spec files changed in the PR.

        Falls back to original results if:
        - No spec files were changed
        - Filtered results are empty (mapping mismatch)

        Args:
            package_build_results: list or dict of build results
        Returns:
            Filtered build results
        """
        target_packages = self._get_target_packages()
        if not target_packages:
            logger.info("No changed spec files found, using all build results")
            return package_build_results

        variant_packages = [self._map_variant_package(p) for p in target_packages]
        logger.info(
            f"Target packages: {target_packages}, variant packages: {variant_packages}"
        )

        if isinstance(package_build_results, list):
            available_packages = {r.get("package") for r in package_build_results}
            filtered = [
                r for r in package_build_results
                if r.get("package") in variant_packages
            ]
        elif isinstance(package_build_results, dict):
            available_packages = set(package_build_results.keys())
            filtered = {
                k: v for k, v in package_build_results.items()
                if k in variant_packages
            }
        else:
            return package_build_results

        # If any variant package is not found in build results, mapping may be wrong,
        # fallback to all results to avoid silently dropping packages
        missing = set(variant_packages) - available_packages
        if missing:
            logger.warning(
                f"Target packages {variant_packages} not fully found in build results, "
                f"missing: {missing}, falling back to all results"
            )
            return package_build_results

        if not filtered:
            logger.warning(
                f"No build results match target packages {variant_packages}, "
                f"falling back to all results"
            )
            return package_build_results

        logger.info(f"Filtered build results by target packages: {variant_packages}")
        return filtered

    def _get_target_packages_for_polling(self):
        """
        Get the list of target package names to wait for during build polling.
        Based on PR changed spec files, mapped to package names.
        Returns empty list if no spec info available (fallback to waiting for all).
        """
        target_packages = self._get_target_packages()
        if not target_packages:
            return []
        return [self._map_variant_package(p) for p in target_packages]


class EbsBuildVerify(BuildMeta):
    """
    EBS environment builds rpm packages
    """
    def __init__(
        self, pull_request, target_branch, arch, multiple, ignore=False, variant=None
    ) -> None:
        super(EbsBuildVerify).__init__()
        self.pull_request = pull_request
        self.target_branch = target_branch
        self.arch = arch
        self.multiple = multiple
        self.ignore = ignore
        self.variant = variant or config.variant
        self.platform = config.platform
        self.pull = Pull()
        self.api = Api()
        self.origin_package, self.pr_num = extract_repo_pull(pull_request)
        self.agent = "https://gh-proxy.test.osinfra.cn"

    @property
    def test_project_name(self):
        """
        Name of test project
        Returns:
            test_project_name: name of test project
        """
        variant_part = f":{self.variant}" if self.variant else ""
        if self.platform:
            return f"{self.platform}:{self.target_branch}:{self.arch}{variant_part}:{self.origin_package}:{self.pr_num}"
        else:
            return f"{self.target_branch}:{self.arch}{variant_part}:{self.origin_package}:{self.pr_num}"

    @property
    def platform_url(self):
        """
        platform url
        Returns:
            platform_url: github/gitee/atomgit
        """
        if self.platform == "github":
            return f"https://github.com"
        elif self.platform == "gitee":
            return f"https://gitee.com"
        else:
            return f"https://atomgit.com"
    
    @property
    def os_variant(self):
        """
        os variant
        Returns:
            os_variant_name:         
        """
        if self.platform == "github":
            os_variant_name = OS_VARIANR_MAP.get("openEuler-22.03-LTS-SP2")
        else:
            os_variant_name = ""
            for key, value in OS_VARIANR_MAP.items():
                if self.target_branch.endswith(key):
                    os_variant_name = value

        return os_variant_name

    def create_project(self):
        """
        Create a test project
        """
        logger.info(f"architecture:{self.arch}")
        base_dict = self.dict_data_constitute(
            self.origin_package, pr_id=self.pr_num, my_spec_type="my_specs"
        )
        # Generate project description, truncate if too long to avoid ccb API error
        description = f"{config.warehouse_owner}/{self.origin_package}/pull/{self.pr_num}"
        max_desc_length = 50
        if len(description) > max_desc_length:
            # Keep PR suffix, truncate middle package name
            pr_suffix = f"/pull/{self.pr_num}"
            prefix = f"{config.warehouse_owner}/"
            available_for_pkg = max_desc_length - len(prefix) - len(pr_suffix) - 3  # 3 for "..."
            if available_for_pkg > 0:
                truncated_pkg = self.origin_package[:available_for_pkg] + "..."
                description = f"{prefix}{truncated_pkg}{pr_suffix}"
            else:
                # Even shorter: just keep PR number if really needed
                description = f"PR#{self.pr_num}"
        base_dict.update(
            {
                "spec_branch": self.target_branch,
                "build_targets": [
                    {"os_variant": self.os_variant, "architecture": self.arch}
                ],
                "users":{
                    "admin": "maintainer"
                },
                "build_env_macros+": {
                    "skip_check": "n",
                    "runtime": 21600
                },
                "description": description
            }
        )
        logger.info(f"BASE DICT:{base_dict}")
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
        code, output, error = command(cmds, console=False, synchronous=False)
        logger.debug(f"cmds: {cmds}, output: {output}, error: {error}")
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
            logger.error(f"JSONDecodeError:{error}")
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
                logger.debug(f"{response.get('data') or response.get('msg')}")
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
            "build_targets": [
                {"os_variant": self.os_variant, "architecture": self.arch}
            ],
            my_spec_type: [
                {
                    "spec_name": spec_name,
                    "spec_url": f"{self.platform_url}/{config.warehouse_owner}/{spec_name}.git",
                    # just for test
                    #"spec_url": f"https://gitee.com/src-openeuler/syscontainer-tools.git",
                    "spec_branch": self.target_branch,
                }
            ]
        }
        base_dict.update(
            package_overrides={spec_name: {"pr_id": pr_id}}
            #just for test
            #package_overrides={spec_name: {"pr_id": "116"}}
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
            if not boot_time or not close_time:
                return build_time
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

        logger.info("Record the build id in the configuration file.")
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
                BLOCKED = 100 # build
                BUILDING = 101 # build
                SIGNING = 102 # build
                SUCCESS = 103 # build/install
                FAILED = 104 # build/install
                UNRESOLVABLE = 105 # build/install
                EXCLUDED = 106 # build/install
                ABORTED = 107 # build
                UNKNOWN = 108 # install
                CYCLE_SUCCESS = 109 # build/install
                CYCLE_FAILED = 110 # build/install
                OOM = 112 # build/install
        project build code interpretation:
                BUILDING = 200
                SUCCESS = 201
                FAILED = 202
                ABORTED = 203
                BLOCKED = 204
                EXCLUDED = 205
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
            112,
        ], [201, 202, 203, 205]
        package_statuses, project_statuses = [101], [200]
        logger.info("The packages under the project are building, please wait...")
        build_detail = []
        # 获取 PR 变更的 spec 对应的目标包名，用于提前结束轮询
        target_packages = self._get_target_packages_for_polling()
        if target_packages:
            logger.info(f"Polling will wait for target packages: {target_packages}")

        # 用于跟踪已输出日志的包和等待时间
        logged_packages = set()
        poll_start_time = time.time()
        last_wait_log_time = poll_start_time
        wait_log_interval = 300  # 每5分钟输出一次等待信息
        max_wait_seconds = 5 * 60 * 60 # 最大等待5小时，超时以失败状态退出
        timed_out = False

        def _try_get_log_urls():
            if len(logged_packages) >= len(target_packages):
                return
            try:
                query_jobs_cmds = [
                    "ccb", "select", "jobs", f"build_id={build_id[0]}",
                    "-f", "spec_name,id"
                ]
                code, output, error = command(query_jobs_cmds, console=False, synchronous=False)
                if code != 0:
                    return
                try:
                    jobs_result = json.loads(output)
                except JSONDecodeError:
                    return
                if not jobs_result:
                    return
                if isinstance(jobs_result, list):
                    jobs_result = {"code": "0", "data": jobs_result, "msg": None}
                for job in jobs_result.get("data", []):
                    source = job.get("_source", {})
                    spec_name = source.get("spec_name")
                    job_id = source.get("id")
                    if not spec_name or not job_id or spec_name in logged_packages:
                        continue
                    if target_packages and spec_name not in target_packages:
                        continue
                    log_url = f"{config.ebs_server}/package/build-record?osProject={self.test_project_name}&packageName={spec_name}&jobId={job_id}"
                    public_log_url = log_url.replace(f"{config.ebs_server}/", "https://eulermaker.openeuler.openatom.cn/")
                    logger.info(f"The package '{spec_name}' build log==>'{public_log_url}'")
                    logged_packages.add(spec_name)
            except Exception:
                pass

        while package_statuses or project_statuses:
            if time.time() - poll_start_time >= max_wait_seconds:
                timed_out = True
                logger.error(
                    f"Build polling timed out after {max_wait_seconds // 3600} hours, "
                    "marking unfinished packages as failed"
                )
                break
            time.sleep(10)
            package_statuses = list()
            build_project_result = self._command_result(query_build_project_cmds)
            logger.debug("the build_project_result is {}".format(build_project_result))

            # 尝试获取并输出构建日志链接（job刚创建时可能还查不到，不影响主流程）
            _try_get_log_urls()

            # 每5分钟输出一次等待信息
            current_time = time.time()
            elapsed = current_time - poll_start_time
            if current_time - last_wait_log_time >= wait_log_interval:
                elapsed_minutes = int(elapsed // 60)
                logger.info(f"Build is still in progress, waited {elapsed_minutes} minutes...")
                last_wait_log_time = current_time

            for build_packages in build_project_result["data"]:
                build_pkgs = build_packages.get("_source", {}).get("build_packages", {})
                if target_packages:
                    # 目标包状态全部到达终态则提前退出
                    target_done = all(
                        build_pkgs.get(pkg, {}).get("build", {}).get("status")
                        in package_build_status_stop
                        for pkg in target_packages
                    )
                    if target_done:
                        logger.info(
                            f"Target packages {target_packages} all reached terminal state, "
                            f"exiting polling early"
                        )
                        package_statuses = []
                        project_statuses = []
                        break
                for _detail in build_pkgs.values():
                    if (
                        _detail.get("build", {}).get("status", 101)
                        not in package_build_status_stop
                    ):
                        package_statuses.append(
                            _detail.get("build", {}).get("status", 101)
                        )
            else:
                # 仅在 for 循环未被 break 时才重新计算 project_statuses
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
                    112,
                ]:
                    resulte = "failed"
                elif _detail.get("build", {}).get("status") == 106:
                    resulte = "excluded"
                elif timed_out:
                    # 超时退出时，仍处于构建中的包以失败状态返回
                    resulte = "failed"
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
        logger.info(f"the build detail is {build_detail}")
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
                    "spec_url": f"{self.platform_url}/{config.warehouse_owner}/{spec_name}.git",
                    # just for test
                    #"spec_url": f"https://gitee.com/src-openeuler/syscontainer-tools.git",
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
            yaml_path = Path(__file__).parents[1].joinpath("conf", "config.yaml")
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
            f"{self.platform_url}/{config.warehouse_owner}/{package_name}", text=True
        ):
            return True
        return False

    def _check_warehouse_in_release_management(self):
        """
        Clone release-management repository and check if origin_package exists in target_branch directory
        
        Returns:
            str: "everything", "epol", "factory", or "multi-version"
        """
        from pathlib import Path
        
        # Check if it's a Multi-Version branch
        if self.target_branch.startswith("Multi-Version"):
            logger.info(f"Handling Multi-Version branch: {self.target_branch}")
            return "multi-version"
        
        # Use fixed directory in workspace
        release_management_dir = Path("./release-management")
        
        if release_management_dir.exists() and release_management_dir.is_dir():
            logger.info(f"release-management directory exists, pulling latest code")
            pull_cmd = ["git", "pull"]
            ret, _, error = command(pull_cmd, cwd=str(release_management_dir))
            
            if ret != 0:
                logger.warning(f"Failed to pull latest code, continuing anyway: {error}")
        else:
            logger.info(f"Cloning release-management repository to {release_management_dir}")
            clone_cmd = ["git", "clone", "https://atomgit.com/openeuler/release-management.git", str(release_management_dir)]
            ret, _, error = command(clone_cmd)
            
            if ret != 0:
                logger.error(f"Failed to clone release-management repository: {error}")
                raise RuntimeError(f"Failed to clone release-management repository: {error}")
            
            logger.info(f"Successfully cloned release-management repository")
        
        # Find the directory matching target_branch
        release_management_path = release_management_dir
        branch_dir = None
        
        # Try exact match first
        if (release_management_path / self.target_branch).exists() and (release_management_path / self.target_branch).is_dir():
            branch_dir = release_management_path / self.target_branch
        
        if not branch_dir:
            logger.error(f"Could not find directory for branch {self.target_branch} in release-management")
            raise RuntimeError(f"Could not find directory for branch {self.target_branch} in release-management")
        
        logger.info(f"Checking branch directory: {branch_dir}")
        
        # Check if it's master branch
        if self.target_branch == "master":
            logger.info("Handling master branch logic")
            return self._check_master_branch(branch_dir)
        else:
            logger.info("Handling non-master branch logic")
            return self._check_non_master_branch(branch_dir)

    def _check_non_master_branch(self, branch_dir):
        """
        Check non-master branch directories: baseos, everything-exclude-baseos, epol
        
        Returns:
            str: "everything" or "epol"
        """
        # Define the subdirectories to check (check everything first, then epol)
        everything_subdirs = ["baseos", "everything-exclude-baseos"]
        found_in_everything = False
        
        # Check everything subdirectories first
        for subdir in everything_subdirs:
            subdir_path = branch_dir / subdir
            if not subdir_path.exists() or not subdir_path.is_dir():
                logger.debug(f"Subdirectory {subdir} not found, skipping")
                continue
            
            # Check pckg-mgmt.yaml file in this subdirectory
            yaml_file = subdir_path / "pckg-mgmt.yaml"
            if not yaml_file.exists():
                logger.debug(f"pckg-mgmt.yaml not found in {subdir}, skipping")
                continue
            
            try:
                logger.info(f"Checking {yaml_file} for {self.origin_package}")
                with open(yaml_file, "r", encoding="utf-8", errors="ignore") as f:
                    yaml_content = yaml.safe_load(f)
                    packages = yaml_content.get("packages", [])
                    for pkg in packages:
                        pkg_name = pkg.get("name", "")
                        if pkg_name == self.origin_package:  # 精确匹配
                            logger.info(f"Found {self.origin_package} in {subdir}/pckg-mgmt.yaml")
                            found_in_everything = True
                            break  # Found in everything, no need to check others
                    if found_in_everything:
                        break  # Found in everything, no need to check other subdirs
            except Exception as e:
                logger.warning(f"Error reading {yaml_file}: {e}")
                continue
        
        if found_in_everything:
            return "everything"
        
        # Check epol directory
        epol_subdir = "epol"
        epol_path = branch_dir / epol_subdir
        epol_yaml = epol_path / "pckg-mgmt.yaml"
        
        if epol_path.exists() and epol_path.is_dir() and epol_yaml.exists():
            try:
                logger.info(f"Checking {epol_yaml} for {self.origin_package}")
                with open(epol_yaml, "r", encoding="utf-8", errors="ignore") as f:
                    yaml_content = yaml.safe_load(f)
                    packages = yaml_content.get("packages", [])
                    for pkg in packages:
                        pkg_name = pkg.get("name", "")
                        if pkg_name == self.origin_package:  # 精确匹配
                            logger.info(f"Found {self.origin_package} in epol/pckg-mgmt.yaml")
                            return "epol"
            except Exception as e:
                logger.warning(f"Error reading {epol_yaml}: {e}")
        
        # Not found in any directory, default to epol
        logger.warning(f"{self.origin_package} not found in any directories, defaulting to 'epol'")
        return "epol"

    def _check_master_branch(self, branch_dir):
        """
        Check master branch directories
        
        Returns:
            str: "everything", "epol", or "factory"
        """
        # Define everything directories for master branch
        everything_dirs_master = [
            "openEuler-BaseTools",
            "openEuler-C",
            "openEuler-Common_Languages_Dependent_Tools",
            "openEuler-Erlang",
            "openEuler-Golang",
            "openEuler-Java",
            "openEuler-KernelSpace",
            "openEuler-Lua",
            "openEuler-Mainline",
            "openEuler-Meson",
            "openEuler-MultiLanguage",
            "openEuler-Nodejs",
            "openEuler-Ocaml",
            "openEuler-Perl",
            "openEuler-Python",
            "openEuler-Qt",
            "openEuler-Ruby"
        ]
        
        # Check everything directories first
        for subdir in everything_dirs_master:
            subdir_path = branch_dir / subdir
            if not subdir_path.exists() or not subdir_path.is_dir():
                logger.debug(f"Subdirectory {subdir} not found, skipping")
                continue
            
            # Check pckg-mgmt.yaml file in this subdirectory
            yaml_file = subdir_path / "pckg-mgmt.yaml"
            if not yaml_file.exists():
                logger.debug(f"pckg-mgmt.yaml not found in {subdir}, skipping")
                continue
            
            try:
                logger.info(f"Checking {yaml_file} for {self.origin_package}")
                with open(yaml_file, "r", encoding="utf-8", errors="ignore") as f:
                    yaml_content = yaml.safe_load(f)
                    packages = yaml_content.get("packages", [])
                    for pkg in packages:
                        pkg_name = pkg.get("name", "")
                        if pkg_name == self.origin_package:  # 精确匹配
                            logger.info(f"Found {self.origin_package} in {subdir}/pckg-mgmt.yaml")
                            return "everything"
            except Exception as e:
                logger.warning(f"Error reading {yaml_file}: {e}")
                continue
        
        # Check epol directory
        epol_subdir = "openEuler-Epol"
        epol_path = branch_dir / epol_subdir
        epol_yaml = epol_path / "pckg-mgmt.yaml"
        
        if epol_path.exists() and epol_path.is_dir() and epol_yaml.exists():
            try:
                logger.info(f"Checking {epol_yaml} for {self.origin_package}")
                with open(epol_yaml, "r", encoding="utf-8", errors="ignore") as f:
                    yaml_content = yaml.safe_load(f)
                    packages = yaml_content.get("packages", [])
                    for pkg in packages:
                        pkg_name = pkg.get("name", "")
                        if pkg_name == self.origin_package:  # 精确匹配
                            logger.info(f"Found {self.origin_package} in epol/pckg-mgmt.yaml")
                            return "epol"
            except Exception as e:
                logger.warning(f"Error reading {epol_yaml}: {e}")
        
        # Check factory directory
        factory_subdir = "openEuler-Factory"
        factory_path = branch_dir / factory_subdir
        factory_yaml = factory_path / "pckg-mgmt.yaml"
        
        if factory_path.exists() and factory_path.is_dir() and factory_yaml.exists():
            try:
                logger.info(f"Checking {factory_yaml} for {self.origin_package}")
                with open(factory_yaml, "r", encoding="utf-8", errors="ignore") as f:
                    yaml_content = yaml.safe_load(f)
                    packages = yaml_content.get("packages", [])
                    for pkg in packages:
                        pkg_name = pkg.get("name", "")
                        if pkg_name == self.origin_package:  # 精确匹配
                            logger.info(f"Found {self.origin_package} in factory/pckg-mgmt.yaml")
                            return "factory"
            except Exception as e:
                logger.warning(f"Error reading {factory_yaml}: {e}")
        
        # Not found in any directory, default to factory
        logger.warning(f"{self.origin_package} not found in any directories, defaulting to 'factory'")
        return "factory"

    def _inject_variant_macros(self, build_env_macros_str):
        """
        将 variant 对应的宏行注入到 build_env_macros YAML 字符串的 macros: 段尾
        Args:
            build_env_macros_str: 原始 build_env_macros YAML 字符串
        Returns:
            str: 注入 variant 宏后的 build_env_macros 字符串
        """
        if not self.variant:
            return build_env_macros_str

        variant_macros = config.variant_macros or {}
        macro_lines = variant_macros.get(self.variant, [])
        if not macro_lines:
            return build_env_macros_str

        # 在 macros: 段的最后一个宏行之后追加新宏行
        lines = build_env_macros_str.split("\n")
        result = []
        in_macros = False
        last_macro_idx = -1

        for line in lines:
            result.append(line)
            if line.strip() == "macros:":
                in_macros = True
            elif in_macros:
                if line.strip().startswith("- "):
                    last_macro_idx = len(result) - 1
                elif line.strip() and not line.startswith(" "):
                    # 遇到下一个顶层 key，macros 段结束
                    in_macros = False

        # 在最后一个宏行之后插入 variant 宏
        if last_macro_idx < 0:
            return build_env_macros_str
        for macro_line in macro_lines:
            last_macro_idx += 1
            result.insert(last_macro_idx, f'- {macro_line}')

        return "\n".join(result)

    def _update_ground_project_config(self, repo_type):
        """
        Get ground project configuration and update PR project
        
        Args:
            repo_type: "everything", "epol", "factory", or "multi-version"
        """
        # Construct ground project name
        if repo_type == "multi-version":
            parts = self.target_branch.split("_")
            if len(parts) < 3:
                logger.error(f"Invalid Multi-Version branch name: {self.target_branch}")
                raise RuntimeError(f"Invalid Multi-Version branch name: {self.target_branch}")
            
            version_part = parts[-1]  
            product_parts = parts[:-1]  
            processed_product_parts = []
            for i, part in enumerate(product_parts):
                if i == 0 and part == "Multi-Version":
                    processed_product_parts.append(part)
                else:
                    processed_product_parts.append(part.replace("-", "_"))
            
            product_part_underscore = "_".join(processed_product_parts)
            version_part_underscore = version_part.replace("-", "_")
            ground_project_name = f"{version_part_underscore}_Epol_{product_part_underscore}"
        elif self.target_branch == "master":
            ground_project_name = f"openEuler-master:{repo_type}"
        else:
            ground_project_name = f"{self.target_branch}:{repo_type}"
        logger.info(f"Getting ground project config from: {ground_project_name}")
        
        # Execute ccb command to get ground project info
        ccb_cmd = [
            "ccb", "select", "projects", ground_project_name,
            "-f", "build_env_macros,build_targets,bootstrap_rpm_repo"
        ]
        
        result = self._command_result(ccb_cmd)
        
        if not result or not result.get("data"):
            logger.error(f"Failed to get ground project config for {ground_project_name}")
            raise RuntimeError(f"Ground project not found on EulerMaker for branch {self.target_branch}: {ground_project_name}")
        
        # Parse the result
        project_data = result["data"][0]["_source"]
        build_env_macros = project_data.get("build_env_macros", "")
        build_targets = project_data.get("build_targets", [])
        bootstrap_rpm_repo = project_data.get("bootstrap_rpm_repo", [])
        
        logger.info(f"Successfully got ground project config")
        
        # Find matching architecture in build_targets
        matched_ground_projects = []
        for target in build_targets:
            if target.get("architecture") == self.arch:
                matched_ground_projects = target.get("ground_projects", [])
                break
        
        # Add current ground project to the list
        if ground_project_name not in matched_ground_projects:
            matched_ground_projects.append(ground_project_name)
        
        logger.info(f"Using ground_projects: {matched_ground_projects}")
        
        # Prepare update content
        update_content = {}
        
        # Add build_env_macros (it's already a YAML string)
        if build_env_macros:
            build_env_macros = self._inject_variant_macros(build_env_macros)
            update_content["build_env_macros"] = build_env_macros
        
        # Add bootstrap_rpm_repo 
        if bootstrap_rpm_repo:
            update_content["bootstrap_rpm_repo"] = bootstrap_rpm_repo
        
        # Update build_targets with ground_projects
        update_content["build_targets"] = [
            {
                "os_variant": self.os_variant,
                "architecture": self.arch,
                "ground_projects": matched_ground_projects
            }
        ]
        
        logger.info(f"Updating PR project with ground project config")
        logger.debug(f"Update content: {update_content}")
        
        # Update the PR project
        self.operate_package_project(update_content)
        
        logger.info(f"Successfully updated ground project config")

    # 快速验证流程预置build_id（不实际触发新的编译），键为架构或架构-variant，比如
    # QUICK_VERIFY_BUILD_IDS = {
    #     "x86_64": "8c66251e-a68a-11f1-b034-fa163e4741d2",
    #     "aarch64": "92d127f0-a68a-11f1-b48c-fa163e4741d2",
    #     "aarch64-64k": "917ff2d2-a68a-11f1-b48c-fa163e4741d2",
    # }
    # QUICK_VERIFY_BUILD_IDS为空时会实际触发新的编译
    QUICK_VERIFY_BUILD_IDS = {}
    def _quick_verify_build_id(self):
        arch_key = f"{self.arch}-{self.variant}" if self.variant else self.arch
        build_id = self.QUICK_VERIFY_BUILD_IDS.get(arch_key)
        if not build_id:
            return None
        logger.info(
            f"Quick verify mode enabled, skip triggering build, "
            f"use preset build_id: {build_id}"
        )
        return [build_id]

    def build_prep_single(self):
        """
        Single-package build process
        Raises:
            RuntimeError: The package triggered compilation failure

        Returns:
            packages_build_results: packages build results
        """
        # Determine if a repository exists
        if config.platform == "gitee" and not self._check_warehouse_exists(self.origin_package):
            raise RuntimeError(f"This {self.origin_package} repository does not exist")
        
        # Check if warehouse exists in release-management repository
        logger.info("================= Check warehouse in release-management =================")
        repo_type = self._check_warehouse_in_release_management()
        
        logger.info("================= Create project =================")
        self.create_project()
        # 2. Empty the project
        logger.info("================= Clear ebs project exist file =================")
        self.create_project()
        self.clear_project()
        # 3. Upload the pr package
        logger.info("================= Upload code =================")
        self.operate_package_project(
            content=self.dict_data_constitute(self.origin_package, pr_id=self.pr_num)
        )

        # 4. Upload pr link package
        relation_prs = self.get_relation_link(self.pr_num, self.origin_package)
        
        # 5. Get and update ground project configuration
        logger.info("================= Get and update ground project config =================")
        self._update_ground_project_config(repo_type)
        
        logger.info("================= start build =================")
        # 6. Triggers build
        build_id = self._quick_verify_build_id()
        if not build_id:
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
        logger.info("================= build finished =================")

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
        # Check if warehouse exists in release-management repository
        logger.info("================= Check warehouse in release-management =================")
        repo_type = self._check_warehouse_in_release_management()
        
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
        
        # Get and update ground project configuration
        logger.info("================= Get and update ground project config =================")
        self._update_ground_project_config(repo_type)
        
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

    def _correct_excluded_by_support_arch(self, package_build_results):
        """
        对构建失败的包，读取 per-spec support_arch 文件：
        当前 arch 不在该 spec 的支持列表 → 结果为因架构不支持而失败，修正为 excluded。
        """
        support_arch_map = self._load_support_arch_map()
        if not support_arch_map:
            return package_build_results

        base_arch = self.arch.split("_64k")[0] if "_64k" in self.arch else self.arch

        def _correct_one(package, result):
            spec_name = package
            support_content = support_arch_map.get(spec_name)
            if support_content is None:
                return result
            # 按空白拆分后做精确成员检查，避免子串误匹配（如 aarch64 命中 aarch64_64k）
            supported_arches = support_content.split()
            if result in ["failed", "unresolvable"] and base_arch not in supported_arches:
                logger.info(
                    "package %s failed on %s but ExclusiveArch not support, "
                    "correct to excluded", package, base_arch
                )
                return "excluded"
            return result

        if isinstance(package_build_results, dict):
            corrected = {}
            for pkg, res in package_build_results.items():
                corrected[pkg] = dict(res)
                corrected[pkg]["build_result"] = _correct_one(pkg, res.get("build_result"))
            return corrected
        if isinstance(package_build_results, list):
            corrected = []
            for item in package_build_results:
                item = dict(item)
                item["result"] = _correct_one(
                    item.get("package"), item.get("result")
                )
                corrected.append(item)
            return corrected
        return package_build_results

    def _get_excluded_packages(self, package_build_results):
        """
        从构建结果中提取被判定为 excluded（ExclusiveArch 不支持当前架构）的包名。
        这些包没有构建产物，不应参与后续 install/oecp 阶段。
        """
        excluded_packages = set()
        if isinstance(package_build_results, dict):
            for pkg, res in package_build_results.items():
                if res.get("build_result") == "excluded":
                    excluded_packages.add(pkg)
        elif isinstance(package_build_results, list):
            for item in package_build_results:
                if item.get("result") == "excluded":
                    excluded_packages.add(item.get("package"))
        return excluded_packages

    def _load_support_arch_map(self):
        """
        读取当前工作目录下所有 support_arch_* 文件。
        兼容两种文件名：ci-guard.sh 下载的带 {repo}_{prid}_ 前缀文件，
        以及 comment.sh/验证环境中的不带前缀文件。
        Returns:
            dict: {spec_base_name: "x86_64 aarch64 ..."}，无文件时返回空 dict
        """
        support_arch_map = {}
        for f in glob.glob("*support_arch_*"):
            spec_name = os.path.basename(f).split("support_arch_")[-1]
            if not spec_name:
                continue
            try:
                with open(f, "r") as sf:
                    support_arch_map[spec_name] = sf.readline().strip()
            except IOError:
                logger.warning("failed to read support_arch file: %s", f)
        return support_arch_map

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
        # 按 PR 实际变更的 spec 文件过滤编译结果
        package_build_results = self.filter_by_changed_specs(package_build_results)
        # 关键修正：因 ExclusiveArch 不支持当前架构而失败的包 → 修正为 excluded
        package_build_results = self._correct_excluded_by_support_arch(
            package_build_results
        )
        result_field, package_build_resultes = (
            ("build_result", list(package_build_results.values()))
            if isinstance(package_build_results, dict)
            else ("result", package_build_results)
        )
        if not package_build_resultes:
            # 构建未真正执行（查询无数据）时结果为空，不能误判为成功
            current_result = "failed"
            logger.error(
                "No package build results returned, build may not have actually executed"
            )
        else:
            current_result_judge = any(
                package_build_result.get(result_field) not in ["success", "excluded"]
                for package_build_result in package_build_resultes
            )
            current_result = "failed" if current_result_judge else "success"
        if current_result == "failed":
            logger.error(f"Package build failed:{package_build_results}")
        check_result = dict(
            build_detail=package_build_results, current_result=current_result
        )
        process_record.update_check_options(steps=steps, check_result=check_result)
        target_packages = self._get_target_packages()
        if target_packages:
            # 因 ExclusiveArch 不支持当前架构而 excluded 的包没有构建产物，
            # 不应参与后续 install/oecp 阶段，从 target_packages 中剔除
            excluded_packages = self._get_excluded_packages(package_build_results)
            if excluded_packages:
                target_packages = [
                    p for p in target_packages
                    if self._map_variant_package(p) not in excluded_packages
                ]
                logger.info(
                    "Excluded packages (ExclusiveArch not supported) removed from "
                    "target_packages: %s", sorted(excluded_packages)
                )
            if target_packages:
                process_record.update_check_options(
                    steps="target_packages",
                    check_result=dict(packages=target_packages),
                )
        return check_result


class BuildVerify:
    """
    Package compilation factory functions
    """

    def __init__(
        self, pull_request, target_branch, arch, multiple, ignore=False, variant=None
    ) -> None:
        self.pull_request = pull_request
        self.target_branch = target_branch
        self.arch = arch
        self.multiple = multiple
        self.ignore = ignore
        self.variant = variant

    def build(self):
        """
        Factory function general entry
        Raises:
            RuntimeError: The build platform selection error

        Returns:
            check_result: The result of the entire process of package compilation
        """
        buildverify = EbsBuildVerify(
            self.pull_request, self.target_branch, self.arch, self.multiple, self.ignore, variant=self.variant
        )
        check_result = buildverify.build()
        build_details = check_result.get("build_detail")
        for build_detail in build_details:
            package_name = build_detail.get("package")
            log_url = build_detail.get("log_url").replace(f"{config.ebs_server}/", "https://eulermaker.openeuler.openatom.cn/")
            logger.info(f"The package '{package_name}' build log==>'{log_url}'")
        return check_result
