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
import shutil
import datetime
from pathlib import Path
import retrying
from retrying import retry, RetryError
from core import extract_repo_pull
from core.analysis import Analysis
from pyrpm.spec import Spec, replace_macros
from constant import STOP_MAX_ATTEMPT_NUMBER, WAIT_FIXED, GIT_FETCH
from api.gitee import Gitee
from sql import Mysql
from logger import logger
from command import command
from conf import config


class Pull:
    """
    Pr Relationship verification
    create,verify and delete pr links
    """

    tip_message = {"openeuler-cla/yes": "", "lgtm": "", "approved": ""}
    merge_tags = "lgtm,approved,openeuler-cla/yes"

    @staticmethod
    def _pull_comment(pr, repo, body):
        gitee_api = Gitee(repo=repo)
        gitee_api.create_pr_comment(number=pr, body=body)

    @retry(
        retry_on_result=lambda result: result is False,
        stop_max_attempt_number=STOP_MAX_ATTEMPT_NUMBER,
    )
    def _insert_link(self, pr_number, source_repo, target_pr, target_repo):
        with Mysql() as database:
            sql = """INSERT INTO link_pull(source_pr,link_pr,source_repo,link_repo,link_date)
                     VALUES(%s,%s,%s,%s,%s);"""
            if not database.execute(
                sql=sql,
                param=[
                    pr_number,
                    target_pr,
                    source_repo,
                    target_repo,
                    datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ],
                commit=True,
            ):
                return False

    def _pre_check_link(self, target_repo, target_pr, pr_number, source_repo):
        pr_info = Gitee(repo=target_repo).get_single_pr_info(number=target_pr)
        if not pr_info:
            logger.warning(f"Target pr info not found: {target_pr}.")
            self._pull_comment(
                pr_number,
                source_repo,
                f"> 目标PR不存在:https://gitee.com/src-openeuler/{target_repo}/pulls/{target_pr}",
            )
            return dict(link_result="failed", detail="目标PR不存在")
        if pr_info.get("state") == "merged":
            logger.error(f"Target pr has been merged: {target_pr}")
            self._pull_comment(
                pr_number,
                source_repo,
                f"> 目标PR已合入:https://gitee.com/src-openeuler/{target_repo}/pulls/{target_pr}",
            )
            return dict(link_result="failed", detail="目标PR已合入")
        if pr_info.get("state") == "close":
            logger.error(f"Target pr has been close: {target_pr}")
            self._pull_comment(
                pr_number,
                source_repo,
                f"> 目标PR关闭:https://gitee.com/src-openeuler/{target_repo}/pulls/{target_pr}",
            )
            return dict(link_result="failed", detail="目标PR关闭")
        url = f"https://gitee.com/src-openeuler/{source_repo}/"
        package_name = self.parse_spec_name(url, pr_number, source_repo).replace(
            "python-", "python3-"
        )
        build_depend, install_depend = Analysis().depended_analysis_package(
            package_name
        )
        build_depend.extend(install_depend)
        relation_packages = [
            package.lower().replace("python3-", "python-") for package in build_depend
        ]

        if not build_depend or target_repo.lower() not in relation_packages:
            logger.warning(f"Target pr has no depend relationship: {target_pr}.")
            self._pull_comment(
                pr_number,
                source_repo,
                f"> 待关联的PR不存在依赖:https://gitee.com/src-openeuler/{target_repo}/pulls/{target_pr}",
            )
            return dict(link_result="failed", detail="待关联的PR之间不存在依赖关系")

    @staticmethod
    def _breadth_tree_find(target_pr, target_repo, source_repo=None, merged=False):
        tree_nodes = set([target_repo])
        link_merge_status = dict()
        exists_link = None
        with Mysql() as database:
            tree_node_sql = """SELECT
                                source_repo,
                                source_pr,
                                link_repo,
                                link_pr,
                                source_pr_tag,
                                link_pr_tag 
                            FROM
                                link_pull 
                            WHERE
                                (link_pr =%s AND link_repo =%s) 
                                OR (source_pr =%s AND source_repo =%s);"""
            _link = database.all(
                sql=tree_node_sql,
                params=[target_pr, target_repo, target_pr, target_repo],
            )
            target = [target_repo]
            while _link:
                new_target = dict()
                for repo in target:
                    for link in filter(
                        lambda x: x["source_repo"] == repo or x["link_repo"] == repo,
                        _link,
                    ):
                        if not merged and (
                            link["source_repo"] == source_repo
                            or link["link_repo"] == source_repo
                        ):
                            tree_nodes.add(source_repo)
                            exists_link = link
                            break

                        if (
                            link["source_repo"] == repo
                            and link["link_repo"] not in tree_nodes
                        ):
                            new_target[link["link_repo"]] = link["link_pr"]
                            tree_nodes.add(link["link_repo"])
                        if (
                            link["link_repo"] == repo
                            and link["source_repo"] not in tree_nodes
                        ):
                            tree_nodes.add(link["source_repo"])
                            new_target[link["source_repo"]] = link["source_pr"]
                        # This data is recorded when a merge is checked
                        if merged:
                            link_merge_status[link["link_repo"]] = dict(
                                tag=link["link_pr_tag"], pr=link["link_pr"]
                            )
                            link_merge_status[link["source_repo"]] = dict(
                                tag=link["source_pr_tag"], pr=link["source_pr"]
                            )

                _link = []
                target = [key for key, _ in new_target.items()]
                for repo, _pr in new_target.items():
                    _link.extend(
                        database.all(
                            sql=tree_node_sql,
                            params=[_pr, repo, _pr, repo],
                        )
                    )
        return dict(
            tree_nodes=tree_nodes,
            exists_link=exists_link,
            link_merged=link_merge_status,
        )

    def pull_link(self, pr_number, source_repo, target_pr, target_repo):
        """
        relation of PR, establish the relation between each other
        :param pr_number: PR number submitted
        :param target_pr: Pr number of the target to be associated
        :return:
                {
                    "link_result":"success/failed",
                    "detail":None
                }
                1. Target is merged
                2. Target is closed
                3. The target has no depends
                4. PR relation already exists
        """
        pre_check_result = self._pre_check_link(
            target_repo, target_pr, pr_number, source_repo
        )
        if pre_check_result and pre_check_result["link_result"] == "failed":
            return pre_check_result

        # breadth first tree traversal finds all nodes where the current association relationship exists
        breadth_tree_nodes = self._breadth_tree_find(
            target_pr, target_repo, source_repo
        )
        exists_link = breadth_tree_nodes["exists_link"]
        if source_repo in list(breadth_tree_nodes["tree_nodes"]):
            if source_repo == exists_link["source_repo"]:
                _pr, _repo = exists_link["link_pr"], exists_link["link_repo"]
            else:
                _pr, _repo = exists_link["source_pr"], exists_link["source_repo"]
            msg = f"源PR已存在关联关系:https://gitee.com/src-openeuler/{_repo}/pulls/{_pr} 请联系对应仓maintainer确认"
            logger.warning(msg)
            self._pull_comment(pr_number, source_repo, msg)
            return dict(link_result="failed", detail=msg)

        try:
            self._insert_link(pr_number, source_repo, target_pr, target_repo)
            self._pull_comment(
                pr_number,
                source_repo,
                f"> 目标Pr:https://gitee.com/src-openeuler/{target_repo}/pulls/{target_pr} 已关联",
            )
        except retrying.RetryError:
            logger.error(
                "An error occurred while inserting data into the associated target PR."
            )
            self._pull_comment(
                pr_number,
                source_repo,
                f"> 目标PR关联错误:https://gitee.com/src-openeuler/{target_repo}/pulls/{target_pr}",
            )
            return dict(link_result="failed", detail="目标PR关联错误")

        for repo, pull in {source_repo: pr_number, target_repo: target_pr}.items():
            Gitee(repo=repo).create_tag(pr_number=pull, body=["linkpull"])

        return dict(
            link_result="success",
            detail=f"目标Pr:https://gitee.com/src-openeuler/{target_repo}/pulls/{target_pr} 已关联",
        )

    def relation_verify(self, pr_number, repo):
        """
        Pr association verification, queries whether there is
        associated PR and the status of associated pr
        :param pr_number: Pr to be queried
        :param repo: Repo to be queried
        :return:
            link_pr:[
                {
                    "status":"merge",
                    "package:"rpmA",
                    "pull":"1"
                }
            ],
            be_link_pr:[
                {
                    "status":"merge",
                    "package:"rpmA",
                    "pull":"1"
                }
            ]
            /None
        """
        relations = dict(link_pr=[], be_link_pr=[])
        with Mysql() as db:
            sql = """SELECT * FROM link_pull WHERE source_pr=%s and source_repo=%s
                     UNION
                    SELECT * FROM link_pull WHERE link_pr=%s and link_repo=%s;"""
            link_prs = db.all(sql, [pr_number, repo, pr_number, repo])
        if not link_prs:
            logger.info(f"There PR is no correlation relationship: {pr_number}")
            return relations

        for pr_link_info in link_prs:
            if (
                pr_link_info["source_pr"] == pr_number
                and pr_link_info["source_repo"] == repo
            ):
                number = pr_link_info["link_pr"]
                repo = pr_link_info["link_repo"]
                link = "link_pr"
            else:
                number = pr_link_info["source_pr"]
                repo = pr_link_info["source_repo"]
                link = "be_link_pr"
            pr_info = Gitee(repo=repo).get_single_pr_info(number=number)
            relations[link].append(
                {
                    "status": pr_info.get("state") if pr_info else "unknow",
                    "package": repo,
                    "pull": number,
                }
            )
        return relations

    @staticmethod
    def del_pull_link(pr_number, repo):
        """
        Delete the PR relation
        :param pr_number: link pr number
        :param repo: link repo
        :return:
            True: delete succes
            False: delete failed
        """

        with Mysql() as database:
            sql = """DELETE FROM link_pull WHERE (link_pr=%s and link_repo=%s) or (source_pr=%s and 
                    source_repo=%s);"""
            success = database.execute(
                sql=sql, param=[pr_number, repo, pr_number, repo], commit=True
            )
        del_result = "success" if success else "failed"
        detail = "PR关联已清除" if success else "关联关系删除失败"
        return dict(del_result=del_result, detail=detail)

    @retry(
        retry_on_result=lambda result: result is False,
        stop_max_attempt_number=STOP_MAX_ATTEMPT_NUMBER,
        wait_fixed=WAIT_FIXED,
    )
    def fetch_pull(self, url, pr_number, repo, depth=1):
        """
        Get the PR and merge it into the code bin for package validation
        :param url: warehouse address
        :param pr_number:commit pr number
        :param depth: To obtain depth
        :return: true or false
        """

        try:
            os.makedirs(GIT_FETCH, exist_ok=True)
        except PermissionError:
            logger.warning(f"Makedirs permission error: {GIT_FETCH}")
            return None
        if not os.path.exists(os.path.join(GIT_FETCH, repo)):
            command(cmds=["git", "clone", url], cwd=GIT_FETCH)
        fetch = f"+refs/pull/{pr_number}/MERGE:refs/pull/{pr_number}/MERGE"
        code, _, error = command(
            ["git", "fetch", "--depth", str(depth), url, fetch],
            cwd=os.path.join(GIT_FETCH, repo),
        )
        if code or error:
            logger.error(f"The fetch PR error occurred: {pr_number}")
            return False
        logger.info(f"PR has been successfully merged: {pr_number}")
        command(
            cmds=["git", "checkout", "-f", f"pull/{pr_number}/MERGE"],
            cwd=os.path.join(GIT_FETCH, repo),
        )
        return True

    def _can_merge(self, repo, pr_number):
        meet_merge, inconformity_merge = set(), set()
        breadth_tree_nodes = self._breadth_tree_find(
            target_pr=pr_number, target_repo=repo, merged=True
        )
        for repo, link_status in breadth_tree_nodes["link_merged"].items():
            pull_link = (
                f"https://gitee.com/src-openeuler/{repo}/pulls/{link_status['pr']}"
            )
            if link_status["tag"] == self.merge_tags:
                meet_merge.add(pull_link)
            else:
                inconformity_merge.add(pull_link)

        return dict(meet_merge=meet_merge, inconformity_merge=inconformity_merge)

    @retry(
        retry_on_result=lambda result: result is None,
        stop_max_attempt_number=STOP_MAX_ATTEMPT_NUMBER,
    )
    def _update_merge_flag(self, repo, pr_number, state):
        with Mysql() as database:
            update_link_success = database.execute(
                "update link_pull set link_pr_tag=%s where link_pr=%s and link_repo=%s",
                [state, pr_number, repo],
            )
            update_source_success = database.execute(
                "update link_pull set source_pr_tag=%s where source_pr=%s and source_repo=%s",
                [state, pr_number, repo],
            )
            if all([update_link_success, update_source_success]):
                logger.info("可合入状态更新成功")
                return True

    def _merge_pull(self, pull):
        repo, _pr = extract_repo_pull(pull)
        self.del_pull_link(_pr, repo)
        if not Gitee(repo=repo).remove_tag(_pr, "linkpull"):
            self._pull_comment(
                _pr,
                repo,
                """> 当前PR已满足合入条件(关联的PR都存在lgtm approved openeuler-cla/yes标签),
                        由于网络原因,linkpull标签未去除,可执行强制合入""",
            )

    def synchronous_merge(self, pr_number, repo):
        """
        Link pull merged
        """
        tags = Gitee(repo=repo).get_all_tag(
            pr_number=pr_number, body=dict(page=1, per_page=100)
        )
        if not tags:
            return
        exist_tags = [tag.get("name") for tag in tags]
        if "linkpull" not in exist_tags:
            return
        exist_tags.remove("linkpull")
        miss_tags = set(self.merge_tags.split(",")).difference(
            set(filter(lambda tag: tag in self.merge_tags, exist_tags))
        )
        state = None if miss_tags else self.merge_tags
        try:
            update_state = self._update_merge_flag(repo, pr_number, state)
        except retrying.RetryError:
            update_state = False
        if not update_state or miss_tags:
            message = (
                """> 不满足合入条件,缺失必要的标签：{}""".format("、".join(miss_tags))
                if not update_state
                else """ > 合入异常,请重新尝试执行 /lgtm /approve"""
            )
            self._pull_comment(pr_number, repo, message)
            logger.warning(message)
            return

        is_merged = self._can_merge(repo, pr_number)
        if is_merged["inconformity_merge"]:
            message = (
                "> 以下关联的PR不满足合入要求(缺少lgtm、approved、openeuler-cla/yes标签),请您联系相关maintainer确认:"
                + os.linesep.join(is_merged["inconformity_merge"])
            )
            self._pull_comment(pr_number, repo, message)
            logger.info(message)
            return
        for pull in is_merged["meet_merge"]:
            logger.info(f"执行合入PR: {pull}")
            self._merge_pull(pull)

    def forced_merge(self, pr_number, repo):
        """
        Forced merged pull
        """
        merged_pulls = self._can_merge(repo, pr_number)
        merged_pulls["meet_merge"].add(
            f"https://gitee.com/src-openeuler/{repo}/pulls/{pr_number}"
        )
        # delete link tag
        merged_pulls["meet_merge"].update(merged_pulls["inconformity_merge"])
        for pull in merged_pulls["meet_merge"]:
            logger.info(f"start remove tag {pull}")
            self._merge_pull(pull)

    def download_kernel_repo_of_tag(self, pr_number, src_openeuler_ulr, repo):
        """
        Download kernel
        :param pr_number: pr number to submit
        :param src_openeuler_ulr: src openeuler address
        :parma repo: warehouse name
        """
        if not self.fetch_pull(src_openeuler_ulr, pr_number, repo, depth=4):
            raise RuntimeError("kernel pr not obtained")
        _, kernel_tag, _ = command(
            ["cat", os.path.join(GIT_FETCH, repo, "SOURCE")],
            cwd=os.path.join(GIT_FETCH, repo),
        )
        if not kernel_tag:
            raise RuntimeError("kernel_tag not obtained")
        logger.info(f"now clone kernel source of tag {kernel_tag} to code/kernel")
        command(
            cmds=[
                "git",
                "clone",
                "-b",
                kernel_tag,
                "--depth",
                "1",
                f"https://{config.giteeuser}:{config.gitpassword}@gitee.com/openeuler/kernel",
                os.path.join(GIT_FETCH, "code", repo),
            ],
            cwd=os.path.join(GIT_FETCH),
        )
        _ = [
            os.path.isdir(os.path.join(GIT_FETCH, "code", "kernel", ".git"))
            and shutil.rmtree(os.path.join(GIT_FETCH, "code", "kernel", ".git"))
        ]

    def parse_spec_name(self, url, pr_number, repo):
        """
        Parse the spec to get the source package name
        :param url: Full warehouse address
        :param pr_number: pr number to submit
        :param repo: warehouse name
        """
        try:
            if not self.fetch_pull(url, pr_number, repo):
                return repo
            repo_paths = Path(GIT_FETCH).joinpath(repo)

            for file in repo_paths.glob("**/*.spec"):
                if not file.is_file():
                    continue
                if repo == "kernel":
                    repo = "kernel"
                else:
                    spec = Spec.from_file(file)
                    repo = replace_macros(spec.name, spec) if spec else repo
                return repo
        except (AttributeError, RetryError) as error:
            logger.info(
                f"Parse the spec to get the source package name, an error occurs {error}"
            )
            return repo
        finally:
            _ = Path(GIT_FETCH).joinpath(repo).is_dir() and shutil.rmtree(
                Path(GIT_FETCH).joinpath(repo)
            )
