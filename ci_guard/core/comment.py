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
import os
import os.path
import yaml
from pathlib import Path
from conf import config
from api.gitee import Gitee
from core import extract_repo_pull, ProcessRecords, get_test_project_name
from logger import logger


class Comment:
    """
    Add a comment to the specified pr
    """

    def __init__(self, pr_url, message, process, users):
        self.pr = pr_url
        self.users = users
        self.process = process
        self.message = message
        self.repo_name, self.pr_num = extract_repo_pull(self.pr)
        self.gitee_api = Gitee(repo=self.repo_name)
        self.comment = (
            f"{config.repo}_{config.pr}_{config.arch}_comment/{config.commentid}"
        )

    def comment_message(self):
        """
        Add a comment to the specified pr
        """
        notify_users = self._add_notify_users(self.users)
        # When "message" specified, comment the "message"
        if self.message:
            notify_message = self.message + notify_users
        else:
            process_message = self._get_process_message()
            if self.process:
                notify_message = process_message.get(self.process)
            else:
                result_file_instance = self._get_current_process_from_file()
                current_result = result_file_instance.progress
                current_process = current_result.get("current_progress")
                notify_message = (
                    process_message.get(current_process) if current_process else ""
                )
                build_host = f"{config.build_host}/project/show/{get_test_project_name(config.repo, config.pr)}"
                install_host = f"http://{config.files_server}/src-openeuler/{config.branch}/{config.committer}/{config.repo}/{config.arch}/{config.pr}/{self.comment}/"
                if current_process == "single_build_check":
                    notify_message["message"] = notify_message["message"] % (
                        config.arch,
                        build_host,
                    )
                elif current_process == "single_install_check":
                    notify_message["message"] = notify_message["message"] % (
                        config.arch,
                        install_host,
                    )
                elif current_process == "diff_analysis":
                    _build, _install = result_file_instance.depend()
                    notify_message["message"] = notify_message["message"] % (
                        config.arch,
                        len(_build),
                        len(_install),
                        build_host,
                    )
                elif current_process in ["multi_build_check", "multi_install_check"]:
                    process = (
                        "build" if current_process == "multi_build_check" else "install"
                    )
                    log_url = build_host if current_process == "multi_build_check" else install_host
                    success_num, fail_num = result_file_instance.multi_check(process)
                    notify_message["message"] = notify_message["message"] % (
                        config.arch,
                        success_num,
                        fail_num,
                        log_url,
                    )
            notify_message = (
                notify_message["message"] + notify_users if notify_message else ""
            )

        if notify_message:
            if not config.process_comment_id:
                self._add_comment_to_pr(notify_message, choice=True)
            else:
                self._modify_comment_to_pr(notify_message, config.process_comment_id)
        else:
            logger.warning("Add comment content is empty")

    @staticmethod
    def _add_notify_users(users):
        """
        Add users who need to be notified
        :param users: users who need to be notified
        :return: string  e.g. @userA,@userB,@userC
        """
        if not users:
            return ""
        return "@" + ",@".join(users)

    def _add_comment_to_pr(self, message, choice=False):
        """
        add comment to pr
        :param message: the content of the comment
        :return: None
        """

        response = self.gitee_api.create_pr_comment(number=self.pr_num, body=message)
        if not response:
            logger.error(f"Failed to comment content {message} to {self.pr}")
        if choice:
            try:
                yaml_path = Path(__file__).parents[1].joinpath("conf", "config.yaml")
                with open(yaml_path, encoding="utf-8") as file:
                    content = yaml.load(file.read(), Loader=yaml.FullLoader)
                    content["process_comment_id"] = response.get("id")
                with open(yaml_path, "w", encoding="utf-8") as f:
                    yaml.dump(data=content, stream=f, allow_unicode=True)
            except (FileNotFoundError, yaml.YAMLError) as error:
                logger.error(f"data write yaml error {error}")

    def _modify_comment_to_pr(self, message, process_comment_id):
        """
        Modify pr's comment
        Args:
            message: message info
            process_comment_id: comment id 
        """
        response = self.gitee_api.modify_pr_comment(
            number=process_comment_id, body=message
        )
        if not response:
            logger.error(f"Failed to comment content {message} to {self.pr}")

    def _get_process_message(self):
        """
        Parse the echo information configuration file of the execution process
        :return: information of the execution process(dict)
        """
        current_path = os.path.dirname(os.path.relpath(__file__))
        message_file = os.path.join(
            os.path.dirname(current_path), "conf/process_message.yaml"
        )
        try:
            with open(message_file, "r", encoding="utf-8") as msg_file:
                process_message = yaml.safe_load(msg_file)
                return process_message
        except yaml.YAMLError as error:
            logger.error(f"Parsing file process_message.yaml failed: {error}")
            return dict()

    def _get_current_process_from_file(self):
        """
        Get the current execution step from the result log file
        :return: dict e.g.
        {
        "current_progress": "single_build_check",
        "next_progress": [
            "single_install_check",
            "diff_analysis",
            "multi_build_check",
            "multi_install_check"
            ]
        }
        """
        repo_name, pr_num = extract_repo_pull(self.pr)
        result_file_instance = ProcessRecords(package=repo_name, pr=pr_num)
        return result_file_instance
