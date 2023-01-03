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
from collections import Counter
import yaml
import constant
from conf import config
from logger import logger


PR_NUMBER = -1
REPO = -3


def extract_repo_pull(pr: str):
    """
    Extract the repo and number from the pull link
    :param pr: pull link
    """
    repo, number = None, None
    if not pr:
        return repo, number
    pr = pr.split("/")
    try:
        repo, number = pr[REPO], pr[PR_NUMBER]
    except IndexError:
        return repo, number
    return repo, number


def get_test_project_name(repo, pr_number):
    """
    Get test project name
    """
    return f"home:{config.build_env_account}:branches:{config.arch}:{repo}-{pr_number}"


class ProcessRecords:
    """Record check item results"""

    file_pointer = None
    steps = [
        "single_build_check",
        "single_install_check",
        "diff_analysis",
        "multi_build_check",
        "multi_install_check",
    ]

    def __init__(self, package="", pr="") -> None:
        self._file = os.path.join(
            constant.RECORDS_COURSE,
            package + "_" + config.arch + "_" + pr + "_buildinfo",
        )
        os.makedirs(constant.RECORDS_COURSE, exist_ok=True)
        self._init_progress = dict(
            current_progress=self.steps[0],
            next_progress=self.steps[0:],
        )
        self._progress = self._execute_progress()

    def _execute_progress(self):
        if os.path.exists(self._file):
            return self.content.get("execution_progress", self._init_progress)
        return self._init_progress

    @property
    def progress(self):
        """
        Check on progress
        """
        return self._init_progress if not self.content else self._progress

    @progress.setter
    def progress(self, progress):
        """
        Set check on progress
        """
        progress_index = self._progress["next_progress"].index(progress)
        self._progress["next_progress"] = self._progress["next_progress"][
            progress_index + 1 :
        ]
        self._progress["current_progress"] = progress

    def _set_pointer(self):
        try:
            self.file_pointer = open(self._file, "a+", encoding="utf-8")
        except IOError as error:
            logger.error(f"Error opening file {self._file},error info: {error}")
            raise

    @property
    def content(self):
        """Check item contents"""
        if not self.file_pointer:
            self._set_pointer()
        try:
            self.file_pointer.seek(0)
            records_result = self.file_pointer.read()
            if not records_result:
                return dict()
            return json.loads(records_result)
        except json.JSONDecodeError as error:
            logger.warning(f"Json decode error: {error}")
            return dict()

    def update_check_options(self, steps, check_result: dict):
        """
        Update check options
        :param steps: check on steps
        :param check_result: check result
        """
        if steps != "pr_link_reult" and steps not in self.steps:
            raise ValueError(f"The {steps} step does not exist in ci check.")
        content = self.content
        content[steps] = check_result
        if steps != "pr_link_reult":
            self.save(progress=steps, content=content)
        else:
            self._write_content(content=content)

    def _write_content(self, content):
        try:
            if self.file_pointer is None:
                self._set_pointer()
            self.file_pointer.seek(0)
            self.file_pointer.truncate()
            self.file_pointer.write(
                json.dumps(
                    content,
                    indent=4,
                )
            )
        except IOError as error:
            logger.error(f"Failed to save the progress information: {error}")
        finally:
            self.file_pointer.close()

    def save(self, progress, content):
        """
        Save check options
        :param progress: check on progress
        :param content: check on contents
        """
        if progress not in self.steps:
            raise ValueError(f"The {progress} step does not exist in ci check.")
        self.progress = progress
        if content is None and not isinstance(content, dict):
            raise ValueError("The content saved is not a dict typical data.")

        content["execution_progress"] = self._progress
        if content.get("diff_analysis") and not content["diff_analysis"].get(
            "need_verify"
        ):
            content["execution_progress"]["next_progress"] = []
        self._write_content(content=content)

    def depend(self):
        build_dependeds, install_dependeds = list(), list()
        if not self.content.get("diff_analysis"):
            return build_dependeds, install_dependeds
        try:
            for _dependeds in self.content["diff_analysis"]["effect_detail"].values():
                if isinstance(_dependeds, dict):
                    build_dependeds.extend(_dependeds.get("be_build_depended", []))
                    install_dependeds.extend(_dependeds.get("be_install_depended", []))
        except KeyError as error:
            logger.error(f"an error occurred in parsing the dependent data: {error}")
        return list(set(build_dependeds)), list(set(install_dependeds))

    def multi_check(self, process):

        content = self.content.get(f"multi_{process}_check", dict()).get(
            f"{process}_detail", dict()
        )
        if not content:
            return 0, 0
        try:
            package_result = {
                package: _result.get(f"{process}_result")
                for package, _result in content.items()
            }
            counter = Counter(package_result.values())
            return counter.get("success", 0), counter.get("failed", 0)
        except (AttributeError, TypeError) as error:
            return 0, 0


class ProjectMapping:
    """
    Mapping of branches and projects
    """

    map_config = os.path.join(os.path.dirname(__file__), "branch_project_mapping.yaml")

    def __init__(self) -> None:
        self._map = dict()

    def _load_config(self):
        try:
            with open(self.map_config, "r") as map_file:
                self._map = yaml.safe_load(map_file)
        except yaml.YAMLError as error:
            logger.error(f"Parsing file branch_project_mapping.yaml failed: {error}")

    def node_host(self, project):
        """
        Gets the host address of a specific project map
        :param project: obs project name
        """
        if not self._map:
            self._load_config()

        for node_map in self._map.get("node_mapping", []):
            if project in node_map.get("projects", []):
                return node_map.get("host")

        logger.warning(f"The project is not in the mapped node: {project}.")

    def branch_project(self, branch):
        """
        Warehouse branch corresponding obs project
        """
        if not self._map:
            self._load_config()
        for _branch, projects in self._map.get("branch_mapping", dict()).items():
            if branch == _branch:
                return projects

        logger.warning(f"The branch has no corresponding project: {branch}.")

    def project_repository(self, project, arch):
        """
        A repository for engineering architecture
        :param project: obs project name
        :param arch: architecture (x86/aarch64)
        """
        if not self._map:
            self._load_config()
        try:
            return self._map["repository_mapping"][project][arch]
        except KeyError:
            logger.error(f"The branch has no corresponding project: {project}.")
            return dict()
