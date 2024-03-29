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
from abc import ABCMeta, abstractmethod
from datetime import datetime

import xmltodict
from conf import config
from logger import logger
from requests.auth import HTTPBasicAuth

from . import Api


class BuildABC(Api):
    __meta_class__ = ABCMeta

    @abstractmethod
    def copy_project(self, original_project, target_project, package: str = None):
        """Copy the target project, or only specific rpm packages if package is specified"""
        pass

    @abstractmethod
    def project_meta(self, project):
        """Get the project's meta to check if the project exists"""
        pass

    @abstractmethod
    def modify_project_meta(self, project, meta: dict):
        """
        Create a project if it does not exist
        If the project doesn't exist, create the project.
        The project modifies the _meta file of a project to add mainly Repositories
        :param meta:is a dict
                {
                    "project": "openEuler:Test",
                    "title": None,
                    "description": None,
                    "person": {"userid": "obs-main", "role": "maintainer"},
                    "publish": "disable/enable",
                    "repository": [
                        {
                            "name": "standard_x86_64",
                            "arch": "x86_64",
                            "path": ["openEuler:Epol", "openEuler:Mainline"],
                        }
                    ],
                }
        """
        pass

    @abstractmethod
    def build_log(self, project, package, arch):
        """build log link address"""
        pass

    @abstractmethod
    def del_project(self, project, package: str = None):
        """Delete a project or a package under a project"""
        pass

    @abstractmethod
    def set_package_flag(self, project, package, flag, status):
        """Set the flag status of a particular package"""
        pass

    @abstractmethod
    def build_rpms(self, project, package, repository="standard_x86_64", arch="x86_64"):
        """Gets the rpm packages generated by a particular repo"""
        pass

    @abstractmethod
    def published_binarys(self, project, repository="standard_x86_64", arch="x86_64"):
        """all archived binary packages under the published project"""
        pass

    @abstractmethod
    def modify_package_meta(self, project, package):
        """modify package meta"""
        pass

    @abstractmethod
    def get_project_info(self, project):
        """get project info"""

    @abstractmethod
    def build_package_lastlog(self, project, package, arch):
        """Gets the compile status of the last package"""
        pass

    @abstractmethod
    def get_package_meta(self, level, project, package):
        """get package meta"""
        pass

    @abstractmethod
    def branch_package(self, project, package, target_project):
        """branch package to test project"""
        pass

    @abstractmethod
    def get_project_build_state(self, project):
        """get project build state"""
        pass

    @abstractmethod
    def package_build_time(self, project, arch, package, state, number=1):
        """get package build time"""
        pass

    @abstractmethod
    def get_project_config(self, project):
        """get project config"""
        pass

    @abstractmethod
    def put_project_config(self, project, config):
        """put project config"""
        pass


class OpenBuildService(BuildABC):
    """
    OBS build service
    """

    def __init__(self, account=None, password=None) -> None:
        super(OpenBuildService, self).__init__()
        if not config.build_host:
            raise ValueError("Build host is null")
        self.host = (
            config.build_host
            if config.build_host.endswith("/")
            else config.build_host + "/"
        )
        self.account = account or config.build_env_account
        self.password = password or config.build_env_passwd

    @staticmethod
    def _status(result):
        """Result determination"""
        return (
            "success" if result.get("status", dict()).get("@code") == "ok" else "failed"
        )

    @staticmethod
    def xml_to_dict(xml: str):
        """
        XML is transformed into a dictionary
        """
        try:
            return xmltodict.parse(xml)
        except xmltodict.ParsingInterrupted as error:
            logger.warning(error)
            return dict()

    @property
    def _server_error(self):
        """Server errors"""
        return dict(status="failed", detail="server error")

    @property
    def _request_error(self):
        """request error"""
        return dict(status="failed", detail="request error")

    def _auth(self):
        """User permission authentication"""
        return HTTPBasicAuth(self.account, self.password)

    def project_meta(self, project):
        """
        set project meta to create new project
        Args:
            project_name (_type_): _description_
        """
        url = f"{self.host}source/{project}/_meta"
        response = self._get(url, auth=self._auth(), text=True)
        if not response:
            logger.error(f"Failed to get the meta of the project: {url}.")
            return self._request_error
        meta_result = self.xml_to_dict(response)
        if not meta_result:
            return self._server_error
        project_info = meta_result.get("project", dict())
        meta = {
            "project": project_info.get("@name"),
            "title": project_info.get("title"),
            "description": project_info.get("description"),
            "publish": list(project_info.get("publish", {}).keys())[-1]
            if list(project_info.get("publish", {}).keys())
            else "",
            "repository": dict(),
        }
        repositorys = project_info.get("repository", dict())
        if isinstance(repositorys, dict):
            repositorys = [repositorys]
        for repository in repositorys:
            paths = repository.get("path")
            if isinstance(paths, dict):
                paths = [paths]
            meta["repository"][repository["arch"]] = [
                {path.get("@repository"): path.get("@project")} for path in paths
            ]

        return dict(status="success", detail=meta)

    def copy_project(self, original_project, target_project, package: str = None):
        """
        Copy one project to another
        If the software package exists, copy the rpm to the target project
        """
        if package:
            values = dict(cmd="branch", oproject=target_project, nodelay=True)
            url = f"{self.host}source/{original_project}/{package}"
        else:
            values = dict(cmd="copy", oproject=original_project, nodelay=True)
            url = f"{self.host}source/{target_project}"
        response = self._post(url, values, auth=self._auth(), text=True)
        if response is None:
            logger.error(f"Failed to copy a project or software package: {url}.")
            return self._request_error
        copy_result = OpenBuildService.xml_to_dict(response)
        if not copy_result:
            return self._server_error

        return dict(
            status=OpenBuildService._status(copy_result),
            detail=copy_result.get("status", dict()).get("summary"),
        )

    def modify_project_meta(self, project, meta: dict):
        """
        Changing the configuration of the meta value of a test project
        """
        url = f"{self.host}source/{project}/_meta"
        repository_xml = ""
        for repository in meta.get("repository", []):
            paths = ""
            for repository_name, project_name in repository.get("path", {}).items():
                paths += f"""<path project="{project_name}" repository="{repository_name}"/>"""
            repository_xml += f"""
                <repository name="{repository.get('name')}">
                    {paths}
                    <arch>{repository.get('arch')}</arch>
                </repository>
            """
        meta_xml = f"""
            <project name="{meta.get('project')}">
                <title>{meta.get('title')}</title>
                <description>{meta.get('description')}</description>
                <person userid="{meta.get('person', dict()).get('userid')}" role="maintainer"/>
                <publish>
                    <{meta.get('publish')}/>
                </publish>
                {repository_xml}
            </project>
        """
        response = self._put(url, meta_xml, text=True, auth=self._auth())
        if response is None:
            logger.error(f"Failed to change the project meta: {url}.")
            return self._request_error
        modify_result = OpenBuildService.xml_to_dict(response)
        if not modify_result:
            return self._server_error

        return dict(
            status=OpenBuildService._status(modify_result),
            detail=modify_result.get("status", dict()).get("summary"),
        )

    def build_log(self, project, package, arch) -> str:
        """The package build log of the"""
        return f"{self.host}/build/{project}/standard_{arch}/{arch}/{package}/_log"

    def del_project(self, project, package: str = None):
        """Delete packages under the project, or the project"""
        url = f"{self.host}/source/{project}"
        if package:
            url += f"/{package}"
        response = self._delete(url=url, text=True, auth=self._auth())
        if response is None:
            logger.error(f"Delete project or package error: {url}")
            return self._request_error
        delete_result = OpenBuildService.xml_to_dict(response)
        if not delete_result:
            return self._server_error
        return dict(
            status=OpenBuildService._status(delete_result),
            detail=delete_result.get("status", dict()).get("summary"),
        )

    def set_package_flag(self, project, package, flag, status):
        url = f"{self.host}/source/{project}/{package}"
        values = dict(cmd="set_flag", flag=flag, status=status)
        response = self._post(url=url, data=values, text=True, auth=self._auth())
        if response is None:
            logger.error(f"Delete project or package error: {url}")
            return self._request_error
        set_flag_result = OpenBuildService.xml_to_dict(response)
        if not set_flag_result:
            return self._server_error
        return dict(
            status=OpenBuildService._status(set_flag_result),
            detail=set_flag_result.get("status", dict()).get("summary"),
        )

    def published_binarys(self, project, repository="standard_x86_64", arch="x86_64"):
        """
        发布工程下的所有归档的二进制包
        """
        url = f"{self.host}/published/{project}/{repository}/{arch}"
        response = self._get(url, text=True, auth=self._auth())
        if response is None:
            logger.error(f"Get published project binarys error: {url}")
            return self._request_error
        binary_result = OpenBuildService.xml_to_dict(response)
        if not binary_result:
            return self._server_error
        return dict(
            status="success",
            detail=[
                packages["@name"]
                for packages in binary_result.get("directory", dict()).get("entry", [])
            ],
        )

    def build_rpms(self, project, package, repository="standard_x86_64", arch="x86_64"):
        """
        Gets the RPM packages generated by a particular REPO
        """
        url = f"{self.host}/build/{project}/{repository}/{arch}/{package}"
        response = self._get(url, text=True, auth=self._auth())
        if response is None:
            logger.error(f"Get build rpm error: {url}")
            return self._request_error
        rpms_result = OpenBuildService.xml_to_dict(response)
        if not rpms_result:
            return self._server_error

        return dict(
            status="success",
            detail=[
                rpm["@filename"]
                for rpm in rpms_result.get("binarylist", dict()).get("binary", [])
                if rpm["@filename"].endswith("noarch.rpm")
            ],
        )

    def modify_package_meta(self, project, package):
        url = f"{self.host}source/{project}/{package}/_meta"
        meta_xml = f"""
        <package name="{package}" project="{project}">
            <title/>
            <description/>
        </package>
        """
        response = self._put(url, meta_xml, text=True, auth=self._auth())
        if response is None:
            logger.error(f"Failed to change the project meta: {url}.")
            return self._request_error
        modify_result = OpenBuildService.xml_to_dict(response)
        if not modify_result:
            return self._server_error

        return dict(
            status=OpenBuildService._status(modify_result),
            detail=modify_result.get("status", dict()).get("summary"),
        )

    def get_project_info(self, project):
        url = f"{self.host}source/{project}/"
        response = self._get(url, text=True, auth=self._auth())
        if response is None:
            logger.error(f"get project error: {url}")
            return self._request_error
        result = OpenBuildService.xml_to_dict(response)
        if not result:
            return self._server_error
        ret = list()
        if "directory" in result and "@count" in result["directory"]:
            count = result["directory"]["@count"]
        else:
            return ret
        if count != "0":
            for pkg in result["directory"]["entry"]:
                ret.append(pkg["@name"])
        return ret

    def build_package_lastlog(self, project, package, arch):
        """
        Gets the compile status of the last package
        Args:
            project (str): project name
            package (str): package name
            arch (str): arch 

        Returns:
            package build result: package build result
        """
        package_lastlog_url = f"{self.build_log(project, package, arch)}?last"
        log_content = self._get(package_lastlog_url, text=True, auth=self._auth())
        if not log_content:
            logger.warning(
                f"Failed to get the result of the last build of the package {package}"
            )
            return False
        log_contents = log_content.splitlines()[-10:]
        for log_content in log_contents:
            if "obs-worker" and "finished" in log_content:
                logger.warning(
                    f"The result of the last build of the {package} log was successful"
                )
                return True
        logger.warning(f"The result of the last build of the {package} log failed")
        return False

    def get_package_info(self, project):
        """
        Get package information for a project
        Args:
            project: project name 

        Returns:
            ret: Packages name
        """
        url = f"{self.host}source/{project}/"
        response = self._get(url, text=True, auth=self._auth())
        if response is None:
            logger.error(f"get project error: {url}")
            return self._request_error
        result = self.xml_to_dict(response)
        if not result:
            return self._server_error
        ret = list()
        if "directory" in result and "@count" in result["directory"]:
            count = result["directory"]["@count"]
        else:
            return ret
        if count != "0":
            if isinstance(result["directory"]["entry"], list):
                for pkg in result["directory"]["entry"]:
                    ret.append(pkg.get("@name"))
            else:
                for pkg in result["directory"]["entry"].values():
                    ret.append(pkg)
        return ret

    def get_package_meta(self, level, project, package):
        """
        Get the package meta,Get the package meta and determine if the package exists
        Args:
            project: project name 
            package: package name
            level: logger level
        Returns:
            Returns true if the package exists, or false if it does not.
        """
        url = f"{self.host}source/{project}/{package}/_meta"
        response = self._get(url, level, text=True, auth=self._auth())
        if response:
            return True
        return False

    def branch_package(self, project, package, target_project):
        """
        Pull test package to test project
        Args:
            project: project name
            package: package name
        """
        url = f"{self.host}/source/{project}/{package}/?cmd=branch"
        a = dict(target_project=target_project, target_package=package)
        response = self._post(url, text=True, data=a, auth=self._auth())
        if not response:
            logger.error(f"fail to branch package {package} from {project}")
            return self._server_error
        return dict(status="succeeded", detail="branch package succeeded")

    def get_single_package_state(self, project, package, arch="x86_64"):
        """
        Gets the compile status of a single package
        Args:
            project: project name 
            package: _description_
            arch: Defaults to "x86_64".

        Returns:
            Compile results for a single package
        """
        url = f"{self.host}/build/{project}/standard_{arch}/{arch}/{package}/_status"
        response = self._get(url, text=True, auth=self._auth())
        if not response:
            logger.error(f"fail to get package {package} state")
            return
        states = self.xml_to_dict(response)
        if states:
            return states["status"]["@code"]

    def get_project_build_state(self, project):
        """
        Get the compilation status of the package under the project
        Args:
            project: project name

        Returns:
            package_results: build results for each package in the project
        """
        url = f"{self.host}/build/{project}/_result"
        response = self._get(url, text=True, auth=self._auth())
        package_results = list()
        wrong_project_state = [{"result": "building"}]
        if not response:
            return wrong_project_state
        states = self.xml_to_dict(response)
        if not states:
            return wrong_project_state
        build_results = states.get("resultlist", dict()).get("result", dict())
        if not build_results or not build_results.get("status"):
            return wrong_project_state

        if isinstance(build_results.get("status"), dict):
            package_results.append(
                dict(
                    package=build_results.get("status").get("@package"),
                    result=build_results.get("status").get("@code"),
                    arch=build_results.get("@arch"),
                    log_url="this package status is excluded"
                    if build_results.get("status").get("@code") == "excluded"
                    else self.build_log(
                        project,
                        build_results.get("status").get("@package"),
                        build_results.get("@arch"),
                    ),
                )
            )
        else:
            for build_result in build_results.get("status"):
                package_results.append(
                    dict(
                        package=build_result.get("@package"),
                        result=build_result.get("@code"),
                        arch=build_results.get("@arch"),
                        log_url="this package status is excluded"
                        if build_result.get("@code") == "excluded"
                        else self.build_log(
                            project,
                            build_result.get("@package"),
                            build_results.get("@arch"),
                        ),
                    )
                )
        return package_results

    def package_build_time(self, project, arch, package, state, number=1):
        """Package compilation time"""
        url = f"{self.host}/build/{project}/standard_{arch}/{arch}/_jobhistory?package={package}&code={state}&limit={number}"
        response = self._get(url, text=True, auth=self._auth())
        build_time = None
        if not response:
            return build_time
        try:
            response = self.xml_to_dict(response)
            if not response:
                return build_time
            starttime = datetime.fromtimestamp(
                int(response["jobhistlist"]["jobhist"]["@starttime"])
            ).strftime("%Y-%m-%d %H:%M:%S")
            endtime = datetime.fromtimestamp(
                int(response["jobhistlist"]["jobhist"]["@endtime"])
            ).strftime("%Y-%m-%d %H:%M:%S")
            time_start_struct = datetime.strptime(starttime, "%Y-%m-%d %H:%M:%S")
            time_end_struct = datetime.strptime(endtime, "%Y-%m-%d %H:%M:%S")
            build_time = (time_end_struct - time_start_struct).seconds
        except (KeyError, TypeError):
            logger.error(f"Failed to get {package} package compile time")
        return build_time

    def get_project_config(self, project):
        """Get the project's configuration"""
        url = f"{self.host}/source/{project}/_config"
        response = self._get(url, text=True, auth=self._auth())
        if response is None:
            logger.error(f"fail to get {project} _config")
            return self._server_error
        return response

    def put_project_config(self, project, config):
        """Modify the configuration of a test project"""
        url = f"{self.host}/source/{project}/_config"
        response = self._put(url, config, text=True, auth=self._auth())
        if not response:
            logger.error(f"fail to get {project} _config")
            return self._server_error
        return dict(status="succeeded", detail="modify project config succeeded")