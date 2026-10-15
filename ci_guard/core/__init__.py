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


class ProcessRecords:
    """Record check item results"""

    file_pointer = None
    steps = [
        "single_build_check",
        "single_install_check",
        "package_license_check",
        "diff_analysis",
        "multi_build_check",
        "multi_install_check",
    ]

    def __init__(self, package="", pr="") -> None:
        variant_suffix = f"_{config.variant}" if config.variant else ""
        self._file = os.path.join(
            constant.RECORDS_COURSE,
            package + "_" + pr + "_" + config.arch + variant_suffix + "_comment",
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
            progress_index + 1:
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
        if not self.file_pointer or self.file_pointer.closed:
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
        # Metadata keys that bypass step validation and progress tracking
        metadata_keys = {"pr_link_reult", "target_packages"}
        if steps not in metadata_keys and steps not in self.steps:
            raise ValueError(f"The {steps} step does not exist in ci check.")
        content = self.content
        content[steps] = check_result
        if steps not in metadata_keys:
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
