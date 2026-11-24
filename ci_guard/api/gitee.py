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
    pkg_info_url = "https://www.openeuler.org/api-omapi/query/sig/info"

    def __init__(self, repo, owner="src-openeuler", token=None, *, read_token=None, write_token=None):
        super(Gitee, self).__init__()
        self._owner = owner
        self._repo = repo
        if not all([self._owner, self._repo]):
            raise ValueError("Calling the api must pass the owner repo parameters.")
        # 灰度兼容：仅传旧 token 时读写双通；任一拆分 token 已传则忽略旧 token
        if token and not (read_token or write_token):
            read_token = write_token = token
        # gitee 无独立写 token 配置，读写均回退 gitee_token
        self._read_token = read_token or config.gitee_token
        self._write_token = write_token or config.gitee_token

    def _require(self, kind):
        """
        取指定类型的 token，缺失时 fail-fast

        :param kind: read / write
        :return: token 字符串
        """
        token = self._read_token if kind == "read" else self._write_token
        if not token:
            raise RuntimeError(f"{kind} token not provided")
        return token

    def _headers(self, kind):
        """
        构造 Bearer 鉴权头

        :param kind: read / write
        :return: header dict
        """
        return {"Authorization": f"Bearer {self._require(kind)}"}

    def _params(self, **kwargs):
        return kwargs

    def create_pr_comment(self, number, body):
        """
        Post comment to the given specific PR
        """
        url = f"{self.host}/{self._owner}/{self._repo}/pulls/{number}/comments"
        return self._post(url, self._params(body=body), headers=self._headers("write"))

    def modify_pr_comment(self, number, body):
        """
        Post comment to the given specific PR
        """
        url = f"{self.host}/{self._owner}/{self._repo}/pulls/comments/{number}"
        return self._patch(url, self._params(body=body), headers=self._headers("write"))

    def get_single_pr_info(self, number):
        """
        Get pr details by pull number
        :param number: Pr number
        """
        url = f"{self.host}/{self._owner}/{self._repo}/pulls/{number}"
        return self._get(url, params=self._params(), headers=self._headers("read"))

    def package_committer(self, package_names, community="openeuler", search="fuzzy"):
        """
        Get maintainer information for a package
        Args:
            package_names : package repository name
        Returns:

        """

        def parse_maintainer(content, pkg_name):
            """
            parse maintainer information for a package
            Args:
                content : maintainer information
                pkg_name : package repository name
             Returns:
            """
            pkg_info = content["data"]
            for con in pkg_info:
                for repo in con["repos"]:
                    if pkg_name in repo:
                        maintainer = con["maintainer_info"][0]
                        commiters[pkg_name] = dict(
                            name=maintainer.get("gitee_id"),
                            email=maintainer.get("email"),
                            sig=con.get("sig_name"),
                        )
            return commiters

        values = dict(community=community, search=search)
        commiters = dict()
        response = self._get(self.pkg_info_url, params=values)
        for package_name in package_names:
            try:
                commiters.update(parse_maintainer(response, package_name))
            except IndexError:
                continue
        return commiters

    def create_tag(self, pr_number, body):
        """
        Create a repository tag
        """
        url = f"{self.host}/{self._owner}/{self._repo}/pulls/{pr_number}/labels"
        return self._post(url, self._params(body=json.dumps(body)), headers=self._headers("write"))

    def remove_tag(self, pr_number, label):
        """
        Remove repository tag
        """
        url = f"{self.host}/{self._owner}/{self._repo}/pulls/{pr_number}/labels/{label}"
        return self._delete(url, params=self._params(), headers=self._headers("write"))

    def get_all_tag(self, pr_number, body):
        """
        Get pull all tags
        """
        url = f"{self.host}/{self._owner}/{self._repo}/pulls/{pr_number}/labels"
        return self._get(url, self._params(body=body), headers=self._headers("read"))
    def get_issue(self, cve_issue, enterprises="open_euler"):
        issue_url = f"https://gitee.com/api/v5/enterprises/{enterprises}/issues/{cve_issue}"
        return self._get(issue_url, params=self._params(), headers=self._headers("read"))
