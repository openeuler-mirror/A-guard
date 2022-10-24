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
import json
from conf import config
from . import Api


class Gitee(Api):
    """
    Gitee is a helper class to abstract gitee.com api
    """

    host = "https://gitee.com/api/v5/repos"
    pkg_info_url = "https://pkgmanage.openeuler.org/"

    def __init__(self, repo, owner="src-openeuler", token=None):
        super(Gitee, self).__init__()
        self._owner = owner
        self._repo = repo
        if not all([self._owner, self._repo]):
            raise ValueError("Calling the api must pass the owner repo parameters.")
        self._token = token or config.gitee_token
        if not self._token:
            raise ValueError("Gitee private token cannot be empty.")

    def _params(self, **kwargs):
        if not kwargs:
            return dict(access_token=self._token)
        parameters = kwargs
        parameters.setdefault("access_token", self._token)
        return parameters

    def create_pr_comment(self, number, body):
        """
        Post comment to the given specific PR
        """
        url = f"{self.host}/{self._owner}/{self._repo}/pulls/{number}/comments"
        return self._post(url, self._params(body=body))

    def modify_pr_comment(self, number, body):
        """
        Post comment to the given specific PR
        """
        url = f"{self.host}/{self._owner}/{self._repo}/pulls/comments/{number}"
        return self._patch(url, self._params(body=body))

    def get_single_pr_info(self, number):
        """
        Get pr details by pull number
        :param number: Pr number
        """
        url = f"{self.host}/{self._owner}/{self._repo}/pulls/{number}"
        return self._get(url, params=self._params())

    def package_committer(
        self, package_names, gitee_branch="master", architecture="standard_aarch64"
    ):
        """
        Get maintainer information for a package
        Args:
            package_names : package repository name
        Returns:

        """
        url = f"{self.pkg_info_url}/api/infoBoard/obs"
        values = dict(gitee_branch=gitee_branch, architecture=architecture)
        commiters = dict()
        for package_name in package_names:
            values.update(dict(pkg_name=package_name))
            response = self._get(url, params=values)
            if not response or response.get("code") != "200":
                continue
            try:
                pkg_info = response["resp"]["pkg_infos"][-1]
                if not pkg_info.get("maintainer"):
                    continue
                maintainer = pkg_info["maintainer"][0]
            except IndexError:
                continue

            commiters[package_name] = dict(
                name=maintainer.get("id"),
                email=maintainer.get("email"),
                sig=pkg_info.get("sig_name"),
            )

        return commiters

    def create_tag(self, pr_number, body):
        """
        Create a repository tag
        """
        url = f"{self.host}/{self._owner}/{self._repo}/pulls/{pr_number}/labels?access_token={self._token}"
        return self._post(url, json.dumps(body))

    def remove_tag(self, pr_number, label):
        """
        Remove repository tag
        """
        url = f"{self.host}/{self._owner}/{self._repo}/pulls/{pr_number}/labels/{label}?access_token={self._token}"
        return self._delete(url)

    def get_all_tag(self, pr_number, body):
        """
        Get pull all tags
        """
        url = f"{self.host}/{self._owner}/{self._repo}/pulls/{pr_number}/labels"
        return self._get(url, self._params(body=body))
