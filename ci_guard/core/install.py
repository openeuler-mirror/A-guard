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
from api.gitee import Gitee
from logger import logger
from command import command
from core import (
    extract_repo_pull,
    get_test_project_name,
    ProjectMapping,
    ProcessRecords,
)
import constant
from conf import config
from .pull_link import Pull


class InstallBase:
    """
    EBS or OBS software package installation check
    """

    install_cmds = os.path.join(os.path.dirname(__file__), "install.sh")

    def __init__(self, arch, target_branch, ignore=False) -> None:
        comment = f"{config.repo}_{config.pr}_{arch}_comment/{config.commentid}"
        self.log = f"http://{config.files_server}/src-openeuler/{target_branch}/{config.committer}/{config.repo}/{arch}/{config.pr}/{comment}/"
        self._arch = arch or config.arch
        self._pull = None
        self._repo = None
        self._target_branch = target_branch or config.branch
        self._ignore = ignore

    @staticmethod
    def json_loads(json_str):
        """
        Json data loading
        :param json_str: json content
        """
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as error:
            logger.error(f"Json load error: {error}")
            raise ValueError(error)

    @staticmethod
    def repo_rpm_map():
        """
        Repo and rpm name mapping
        """
        repo_rpm_file = os.path.join(
            constant.PROJECT_WORK_DIR, "install-logs", "repo-rpm-map"
        )
        repo_rpm_map_dict = dict()
        if not os.path.exists(repo_rpm_file):
            logger.error(f"File not found: {repo_rpm_file}")
            return repo_rpm_map_dict
        try:
            with open(repo_rpm_file, "r", encoding="utf-8") as file:
                repo_rpms = [
                    repo_rpm.replace(os.linesep, "").split(":")
                    for repo_rpm in file.readlines()
                ]
        except IOError as error:
            logger.error(f"Failed to read the installation result file: {error}.")
            repo_rpms = []
        finally:
            os.remove(repo_rpm_file)
        for rpm_repo in repo_rpms:
            repo, rpm = rpm_repo
            if repo in repo_rpm_map_dict:
                repo_rpm_map_dict[repo].add(rpm)
            else:
                repo_rpm_map_dict[repo] = {rpm}
        return repo_rpm_map_dict

    @staticmethod
    def installed_checked():
        """
        Get the rpm installation result
        """
        successful, failed = dict(), dict()
        installed_file = os.path.join(
            constant.PROJECT_WORK_DIR, "install-logs", "installed"
        )
        if not os.path.exists(installed_file):
            return successful, failed
        try:
            with open(installed_file, "r", encoding="utf-8") as file:
                _installed_status = [
                    rpm.replace(os.linesep, "").split(":") for rpm in file.readlines()
                ]
        except IOError as error:
            logger.error(f"Failed to read the installation result file: {error}.")
            _installed_status = []
        for installed_status in _installed_status:
            rpm, start_time, end_time, state = installed_status
            if state == "success":
                successful[rpm] = int(end_time) - int(start_time)
            else:
                failed[rpm] = int(end_time) - int(start_time)
        return successful, failed

    def _record(self, install_results, steps):
        if steps == "single_install_check":
            current_result = all(
                [
                    True if installed["result"] == "success" else False
                    for installed in install_results
                ]
            )
        else:
            current_result = all(
                [
                    True if installed["install_result"] == "success" else False
                    for _, installed in install_results.items()
                ]
            )
        setp_result = "success" if current_result else "failed"
        process_record = ProcessRecords(self._repo, self._pull)
        process_record.update_check_options(
            steps=steps,
            check_result=dict(
                install_detail=install_results, current_result=setp_result
            ),
        )
        return current_result

    def _multiple_install_check(self, rpms, archive_rpms: list = None):
        installed_result = dict()
        _, failed = self.installed_checked()
        archive_rpms.extend([rpm for rpm, _ in rpms.items()])

        installed_failed_rpms = dict()
        repo_rpm_map = self.repo_rpm_map()
        for package in archive_rpms:
            gitee_api = Gitee(repo=package)
            binary_rpms = repo_rpm_map.get(package, set())
            status = "success" if not binary_rpms.intersection(failed) else "failed"
            commitor = gitee_api.package_committer(
                package_names=[package],
                gitee_branch=self._target_branch,
            )
            if status == "failed":
                installed_failed_rpms[package] = False if package in rpms else True
            logger.info(
                f"The package '{package}' is {status} installed,log: {self.log}"
            )
            installed_result[package] = dict(
                install_result=status,
                sig=None,
                log_url=self.log,
                commitor=commitor.get(package),
            )
        if self._record(installed_result, "multi_install_check"):
            logger.info("The multi package installation check succeeded.")
            return True

        return self._isolation_verify(installed_failed_rpms, installed_result)

    def _single_install_check(self, rpms: dict):
        install_results = []
        successful, failed = self.installed_checked()
        repo_rpm_map = self.repo_rpm_map()
        for package, _ in rpms.items():
            if not repo_rpm_map:
                status = "failed"
            else:
                binary_rpms = repo_rpm_map.get(package, set())
                status = "success" if not binary_rpms.intersection(failed) else "failed"

            if status == "success":
                install_time = successful.get(package)
                logger.info(f"The package {package} is successfully installed.")
            else:
                install_time = failed.get(package)
                logger.error(f"Package {package} installation failed.")
            logger.info(
                f"Single package installation checked,package: {package} status: {status} log: {self.log} "
            )
            install_results.append(
                dict(
                    arch=self._arch,
                    package=package,
                    result=status,
                    log_url=self.log,
                    install_time=install_time,
                )
            )

        return self._record(install_results, "single_install_check")

    def _link_pull(self, link=True):
        """
        Gets the pr association or is associated with
        :param link: When link is True, the pr of the association is obtained, and vice versa
        """
        pull_links = Pull().relation_verify(pr_number=self._pull, repo=self._repo)
        key = "link_pr" if link else "be_link_pr"
        return [
            dict(pr=link_pr["pull"], repo=link_pr["package"])
            for link_pr in pull_links[key]
        ]

    def _isolation_verify(self, rpms, install_results):
        """
        When a multi package installation fails, use elimination for isolation verification
        :param rpms: List of rpms installed
        :param install_results: installed results
        """
        verify_result = dict()
        for package, is_archive in rpms.items():
            if is_archive:
                code, _, _ = command(
                    ["bash", self.install_cmds, "isolation_verify", package]
                )
            else:
                cmds = f"bash {self.install_cmds} isolation_verify {constant.DOWNLOAD_RPM_DIR} {package}"
                code, _, _ = command(cmds.split())
            verify_result[package] = False if code else True

            if code:
                logger.error(f"Isolation installation verification failed: {package}.")
        # As long as one successful installation is affected by the current PR
        # all isolated installation failures are irrelevant to the current PR
        if any([state for _, state in verify_result.items()]):
            logger.error(
                f"Isolation verify that a successfully installed package exists,\
                    please check the current pr: {self._pull}."
            )
            return False
        logger.warning(
            f"Isolation verify installed packages are failed:{' '.join(rpms.keys())}."
        )
        process_record = ProcessRecords(self._repo, self._pull)
        process_record.update_check_options(
            steps="multi_install_check",
            check_result=dict(install_detail=install_results, current_result=True),
        )
        return True

    def install(self, pull_request, multiple, packages: list):
        """
        Rpm installation verification
        :param pull_request: Submitted pull links
        :param multiple: single or mutiple package install check
        :param packages: List of packages to be installed
        """
        try:
            self._repo, self._pull = extract_repo_pull(pull_request)
        except TypeError:
            logger.warning(f"Not a valid pull link: {pull_request}.")
            return

        # multiple package install
        if multiple:
            logger.info(
                f"Starts the multi package installation check,packages:{' '.join(packages)}."
            )
            be_link_pulls = self._link_pull(link=False)
            test_project_rpms = set(packages).intersection(
                set([rpm["repo"] for rpm in be_link_pulls])
            )
            if not test_project_rpms:
                logger.warning(
                    f"The currently validated '{self._repo} {self._pull}' does not have packages that are installed bedependent."
                )
            archive_rpms = set(packages).difference(set(test_project_rpms))
            download_rpms = {
                be_link_pr["repo"]: be_link_pr["pr"]
                for be_link_pr in be_link_pulls
                if be_link_pr["repo"] in test_project_rpms
            }
            # Install archived packages
            if archive_rpms:
                logger.info(
                    f"Start installing the archive rpm package: {' '.join(archive_rpms)}"
                )
                cmds = ["bash", self.install_cmds, "install_rpms"]
                cmds.extend(list(archive_rpms))
                command(cmds=cmds)
                logger.info("The archive binary package installation is complete.")
        else:
            link_pulls = self._link_pull()
            download_rpms = {self._repo: self._pull}
            # exists link
            if link_pulls:
                download_rpms.update(
                    {link_pull["repo"]: link_pull["pr"] for link_pull in link_pulls}
                )

        if download_rpms:
            self._download_rpms(download_rpms)
            # Install the rpm compiled by the test project
            command(
                cmds=[
                    "bash",
                    self.install_cmds,
                    "install_rpms",
                    constant.DOWNLOAD_RPM_DIR,
                ]
            )
        # Single package installation, then directly check the results and update
        if not multiple:
            return self._single_install_check(download_rpms)

        return self._multiple_install_check(download_rpms, list(archive_rpms))


class InstallVerify(InstallBase):
    """
    Single package or multiple package installation check
    """

    def __init__(self, arch=None, target_branch=None, ignore=False) -> None:
        super().__init__(arch, target_branch, ignore)

    @property
    def repository(self):
        """
        Repository schema mapping
        """
        repository = "standard_x86_64" if self._arch == "x86_64" else "standard_aarch64"
        return repository

    def update_repo(self, branch=config.branch):
        """
        update repo
        :param branch: Warehouse branch
        """
        logger.info(f"Start updating the repo source: {branch}")
        p_map = ProjectMapping()
        projects = p_map.branch_project(branch=branch)
        if not projects:
            raise ValueError(
                "Currently branch is not supported. Please update the configuration file"
            )
        update_repo_status = []
        for project in projects:
            host = p_map.node_host(project=project)
            if not host:
                continue
            code, _, error = command(
                cmds=[
                    "bash",
                    self.install_cmds,
                    "update_repo",
                    project,
                    host,
                    self.repository,
                ]
            )
            update_repo_status.append(code)
            if code:
                logger.error(
                    f"The repo source update failed, project: {project} detail: {error}."
                )
        return False if any(update_repo_status) else True

    def _download_rpms(self, download_rpms: list):
        """
        Download archived or compiled binaries using the OSC
        :param download_rpms: Rpm to be downloaded
        """
        rpms = {
            repo: get_test_project_name(repo, pull)
            for repo, pull in download_rpms.items()
        }

        os.makedirs(constant.DOWNLOAD_RPM_DIR, exist_ok=True)
        for package, project in rpms.items():
            cmds = f"bash {self.install_cmds} download_binarys {project} {package} {self.repository} {self._arch}"
            code, _, error = command(
                cmds=cmds.split(),
                cwd=constant.DOWNLOAD_RPM_DIR,
            )

            if code:
                logger.warning(
                    f"Failed to download the rpm package,project: {project} package: {package} error detail: {error}."
                )


class UnifyBuildInstallVerify(InstallBase):
    """
    Unify build install verify. Use the ccb command to configure the repo source and
    download the built binary package to pass dnf installation check
    """

    def __init__(self, arch=None, target_branch=None, ignore=False) -> None:
        super().__init__(arch, target_branch, ignore)

    @property
    def project(self):
        return f"{config.branch}:{self._arch}:{self._repo}:{self._pull}"

    @staticmethod
    def _load_repos(out_repo):
        repos = UnifyBuildInstallVerify.json_loads(out_repo)
        repo_list = [repo["_source"].get("rpm_repo") for repo in repos]
        return list(set(repo_list))

    def _get_repos(self, repo_ids):
        repos = dict()
        for repo_id in repo_ids:
            cmds = f"ccb select rpm_repos repo_id={repo_id} architecture={self._arch} -f rpm_repo_path"
            code, cmd_out, error = command(cmds=cmds.split())
            if code:
                logger.error(
                    f"Failed to get the project repo source,command: {cmds} error: {error}"
                )
                raise ValueError()
            repo = UnifyBuildInstallVerify.json_loads(cmd_out)
            repos[repo_id] = repo[-1]["_source"]["rpm_repo_path"]
        return repos

    def _get_repo_id(self, build_id):
        cmds = f"ccb select builds build_id={build_id} -f repo_id,ground_projects"
        code, out, error = command(cmds=cmds.split())
        if code:
            logger.error(f"Failed to get the repo id,command: {cmds} error: {error}.")
            raise ValueError()
        build = UnifyBuildInstallVerify.json_loads(out)
        try:
            project_repo = build[0]["_source"]
            project_repo_id = project_repo["repo_id"]
            ground_project_repo_id = project_repo["ground_projects"][-1]["repo_id"]
        except (KeyError, IndexError):
            raise ValueError()
        return project_repo_id, ground_project_repo_id

    def update_repo(self, build_id):
        """
        Generate the repo source
        :param branch: Warehouse branch
        """
        try:
            project_repo_id, ground_project_repo_id = self._get_repo_id(
                build_id=build_id
            )
            repos = self._get_repos(repo_ids=(project_repo_id, ground_project_repo_id))

        except (ValueError, IndexError, KeyError):
            return False

        logger.info(f"Start updating the repo source: {config.branch}")
        repo_content = ""
        for project, repo in repos.items():
            repo_content += f"""
[{project}]
name={project}
baseurl={config.ebs_server}{repo}
enabled=1
gpgcheck=0
"""
        try:
            with open(
                os.path.join(config.workspace, "ci-tools.repo"), "w", encoding="utf-8"
            ) as file:
                file.write(repo_content)
            logger.info(repo_content)
            logger.info("The repo source update successful.")
            return True
        except IOError as error:
            logger.error(error)
            return False

    def _download_rpms(self, download_rpms: dict):
        """
        CCB downloads the generated binary package
        :param download_rpms: Rpm to be downloaded
        """
        os.makedirs(constant.DOWNLOAD_RPM_DIR, exist_ok=True)
        for package, _ in download_rpms.items():
            cmds = f"bash {self.install_cmds} ccb_download_binarys {self.project} {package} {self._arch}"
            code, _, error = command(
                cmds=cmds.split(),
                cwd=constant.DOWNLOAD_RPM_DIR,
            )
            if code:
                logger.warning(
                    f"Failed to download the rpm package,project: {self.project} package: {package} error detail: {error}."
                )
