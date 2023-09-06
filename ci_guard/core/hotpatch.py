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


import time
import uuid
import json
from constant import STOP_MAX_ATTEMPT_NUMBER
from logger import logger
from pathlib import Path
from command import command
from json import JSONDecodeError
from retrying import retry
from contextlib import contextmanager

from conf import config
from api.gitee import Gitee


class MakeHotPatchProject:
    """
    EBS environment builds rpm packages
    """
    def __init__(
        self, x86_debuginfo, aarch64_debuginfo, issue_title, issue_date, repo
    ) -> None:
        super(MakeHotPatchProject).__init__()
        self.pull_request = config.pr
        self.target_branch = config.branch
        self.x86_job_id = ""
        self.aarch_job_id = ""
        self.x86_debuginfo = x86_debuginfo
        self.aarch64_debuginfo = aarch64_debuginfo
        self.issue_title = issue_title
        self.issue_date = issue_date
        self.hotpatch_repo = repo
        self.gitee = Gitee(config.repo, owner=config.warehouse_owner)

    @property
    def test_project_name(self):
        """
        Name of test project
        Returns:
            test_project_name: name of test project
        """
        return f"HotPatch:{self.pull_request}"

    def get_job_id(self, debuginfo_path):
        """
        via debuginfo get job_id
        """
        query_jobid_cmds = ["ccb", "query", "-f", "job_id", "-r", debuginfo_path, ]
        logger.info(f"query_jobid_cmds:{query_jobid_cmds}")
        code, output, error = command(query_jobid_cmds)
        logger.info(f"query_jobid_cmds output:{output}")
        response = json.loads(output)
        if response.get("result") == "success":
            logger.info("get job_id success")
            job_id = response.get("details").get("job_id")
        else:
            reason = response.get("details").get("reason")
            logger.error("get job_id failed, reason: %s", reason)
            raise RuntimeError(f"get job_id failed, reason: {reason}")

        return job_id

    def create_project(self):
        """
        Create a test project
        """
        base_dict = self.dict_data_constitute(pr_id=self.pull_request)
        logger.info(f"BASE DICT:{base_dict}")
        _json_path = self._combine_data_json_path()
        create_project_cmds = ["ccb", "create", "projects", self.test_project_name, "--json", _json_path, ]

        try:
            with self.update_package_operation(
                base_dict, create_project_cmds, _json_path)\
                    as response:
                logger.debug(f"{response.get('data') or response.get('msg')}")
        except (TypeError, OSError, IOError, PermissionError) as error:
            raise RuntimeError(f"Failed to update project, because {error}")

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

    def trigger_build(self):
        """
        Trigger the compilation of single or all software under the project
        Args:
            package_name: The package that needs to trigger the compilation is required Defaults to None.

        Returns:
            build_id: Triggers the compiled build_id
        """
        build_id_dict = {}
        base_trigger_build_cmds = ["ccb", "build", f"os_project={self.test_project_name}", "build_type=makehotpatch"]
        output = self._command_result(base_trigger_build_cmds)

        data = output.get("data")
        if data and isinstance(data, dict):
            for build_id, build_detail in data.items():
                os_variant = build_detail.get("os_variant")
                arch = build_detail.get("architecture")
                build_id_dict[arch] = {"build_id": build_id, "os_variant": os_variant}

        return build_id_dict

    def dict_data_constitute(self, pr_id=None):
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
            'project_type': 'ci-hotpatch',
            "spec_branch": self.target_branch,
            "package_repos": [
                {
                "spec_name": config.repo,
                "spec_url": f"https://gitee.com/{config.warehouse_owner}/{config.repo}.git",
                "spec_branch": "master",
                }
            ],
            "package_overrides": {
                "hotpatch_meta": {
                    "pr_id": f"{pr_id}"
                }
            },
            "hotpatch_config": {
                "package_repo": self.hotpatch_repo,
                "extra_build_dep": ["syscare", "syscare-build", "syscare-build-ebpf", "aops-apollo-tool"],
                "history_jobs": {
                    "aarch64": self.aarch_job_id,
                    "x86_64": self.x86_job_id
                },
                'issue_title': self.issue_title,
                'issue_date': self.issue_date
            },
        }
        return base_dict

    @staticmethod
    def _get_publish_status(build_result):
        publish_status_stop = [0, 2, 4, 5, 6]
        data = build_result["data"][0]
        published_status = data["_source"].get("published_status")
        publish_status = published_status if published_status in publish_status_stop else 1

        return publish_status

    @staticmethod
    def _get_publish_detail(build_project_result):
        data = build_project_result["data"]
        publish = data[0].get("_source", {}).get("published_status")
        logger.info(f"published_status: {publish}")
        if publish == 4:
            result = "success"
        else:
            result = "failed"
        return result

    def query_build_project_result(self, build_ids):
        """
        Query the compilation results of the package
        publish code interpretation:
                PUBLISH_NO = 0
                PUBLISH_WAITING = 1
                PUBLISH_ABORTED = 2
                PUBLISH_PUBLISHING = 3
                PUBLISH_SUCCESS = 4
                PUBLISH_FAILED = 5
                PUBLUSH_MISSING_INFO = 6
        Args:
            build_id: triger build id
        Returns:
            build_detail: package build detail
        """
        build_detail_dict = {}
        query_x86_build_project_cmds = ["ccb", "select", "builds",
                                        f"build_id={build_ids.get('x86_64').get('build_id')}",
                                        "-f", "published_status", ]
        query_aarch64_build_project_cmds = ["ccb", "select", "builds",
                                            f"build_id={build_ids.get('aarch64').get('build_id')}",
                                            "-f", "published_status", ]
        x86_publish_status = 1
        arm_publish_status = 1

        logger.info("The packages under the project are building, please wait...")
        while x86_publish_status == 1 or arm_publish_status == 1:
            time.sleep(10)
            x86_build_project_result = self._command_result(query_x86_build_project_cmds)
            x86_publish_status = self._get_publish_status(x86_build_project_result)

            aarch64_build_project_result = self._command_result(query_aarch64_build_project_cmds)
            arm_publish_status = self._get_publish_status(aarch64_build_project_result)

        x86_build_result = self._get_publish_detail(x86_build_project_result)
        arm_build_result = self._get_publish_detail(aarch64_build_project_result)

        build_detail_dict["x86_64"] = x86_build_result
        build_detail_dict["aarch64"] = arm_build_result

        logger.info("make hotpatch completed")
        logger.info(build_detail_dict)
        return build_detail_dict

    def get_repos(self):
        repos_dict = {}
        cmds = f"ccb select projects os_project={self.test_project_name}"

        code, out, error = command(cmds=cmds.split(), console=False)
        if code and not out:
            logger.error(f"Failed to get projects,command: {cmds} error: {error}.")
            raise ValueError()
        projects = json.loads(out)
        try:
            emsx = projects[0]["_source"]["emsx"]
            for build_target in projects[0]["_source"]["build_targets"]:
                architecture = build_target.get("architecture")
                os_variant = build_target.get("os_variant")
                repo_url = f"{config.ebs_server}api/{emsx}/repositories/{self.test_project_name}/{os_variant}/{architecture}/"
                repos_dict[architecture] = repo_url
        except (KeyError, IndexError):
            raise ValueError()
        logger.info(repos_dict)
        return repos_dict

    def comment_tag(self, build_details):
        result_list = [0 if result == "success" else 1 for arch, result in build_details.items()]
        if sum(result_list) == 0:
            self.gitee.remove_tag(self.pull_request, "ci_failed")
            self.gitee.create_tag(self.pull_request, "ci_successful")
        else:
            self.gitee.remove_tag(self.pull_request, "ci_successful")
            self.gitee.create_tag(self.pull_request, "ci_failed")

    @retry(retry_on_result=lambda result: result is False,
           stop_max_attempt_number=STOP_MAX_ATTEMPT_NUMBER,
           )
    def comment_to_pr(self, comment):
        response = self.gitee.create_pr_comment(self.pull_request, "\n".join(comment))
        if not response:
            logger.error(f"Failed to comment content to {self.pull_request}")
            return False
        return True

    def comment_hotpatch_result(self, build_detail_dict, repo_urls):
        comments = ["<table><tr><th>Arch name</th> <th>Result</th><th>Download link</th> </tr>"]
        for arch, result in build_detail_dict.items():
            build_url = repo_urls.get(arch)
            if result == "success":
                comments.append(f"<tr><td>{arch}</td> <td>:white_check_mark:{result.upper()}</td> "
                                f"<td><a href={build_url}>{build_url}</a></td></tr>")
            else:
                comments.append(f"<tr><td>{arch}</td> <td>:x:{result.upper()}</td> <td></td></tr>")

        comments.append("</table>")
        self.comment_to_pr(comments)
        self.comment_tag(build_detail_dict)

    def build_patch(self):
        """
        Single-package build process
        Raises:
            RuntimeError: The package triggered compilation failure

        Returns:
            packages_build_results: packages build results
        """
        # 1. get debuginfo job_id
        logger.info("*************** Query job id ***************")
        self.x86_job_id = self.get_job_id(self.x86_debuginfo)
        self.aarch_job_id = self.get_job_id(self.aarch64_debuginfo)
        logger.info("*************** Create project ***************")
        # 2. create project
        self.create_project()
        # 3. create make hotpatch task
        logger.info("*************** Create hotpatch task ***************")
        build_id_dict = self.trigger_build()
        if not build_id_dict:
            raise RuntimeError("build error")
        # 4. Wait for the build result, wait for the build
        logger.info("*************** check hotpatch task status ***************")
        build_detail_dict = self.query_build_project_result(build_id_dict)
        logger.info("build_detail = %s", build_detail_dict)

        # 5. get build result rpm
        logger.info("*************** get hotpatch task repo url ***************")
        repo_urls = self.get_repos()

        # 6. comment result to pr
        logger.info("*************** comment result to hotpatch_meta pr ***************")
        self.comment_hotpatch_result(build_detail_dict, repo_urls)


    def build(self):
        """
        Factory function general entry
        Raises:
            RuntimeError: The build platform selection error

        Returns:
            check_result: The result of the entire process of package compilation
        """
        self.build_patch()

