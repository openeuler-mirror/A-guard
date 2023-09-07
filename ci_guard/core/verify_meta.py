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


import re
import sys
import os
import xmltodict

from compare_version import CompareVersion
from logger import logger

from conf import config
from api.gitee import Gitee
from command import command


date_pattern = r"\d{4}[-/]\d{2}[-/]\d{2}"
type_dict = {
    "cve": "security",
    "bugfix": "bugfix",
    "feature": "enhancement"
}


class VerifyHotPatchMeta:
    """
    EBS environment builds rpm packages
    """
    def __init__(
        self, input, output, patch_list, mode
    ) -> None:
        super(VerifyHotPatchMeta).__init__()
        self.pull_request = config.pr
        self.target_branch = config.branch
        self.input = input
        self.output = output
        self.patch_list = patch_list
        self.mode = mode
        self.gitee = Gitee(config.repo, owner=config.warehouse_owner)

    def parse_from_meta_file(self, meta_file):
        meta_info = []
        hotpatchs = []
        with open(meta_file, "r", encoding="utf-8", ) as f:
            d = xmltodict.parse(f.read(), process_namespaces="ns0")
            hotpatchdoc_url = "https://gitee.com/openeuler/hotpatch_meta:hotpatchdoc"
            hotpatch_result = d.get(hotpatchdoc_url, {}).get("HotPatchList", {}).get("Package", {}).get("hotpatch", [])
            logger.info(hotpatch_result)
            if hotpatch_result and isinstance(hotpatch_result, dict):
                hotpatchs.append(hotpatch_result)
            else:
                hotpatchs = hotpatch_result
            for hotpatch in hotpatchs:
                if not hotpatch:
                    break
                try:
                    tmp = dict()
                    if self.mode == "SGL":
                        tmp["name"] = hotpatch["@name"]
                    tmp["version"] = hotpatch["@version"]
                    tmp["release"] = hotpatch["@release"]
                    tmp["type"] = hotpatch["@type"]
                    tmp["inherit"] = hotpatch["@inherit"]
                    tmp["status"] = hotpatch["@status"]
                    tmp["SRC_RPM"] = hotpatch["SRC_RPM"]
                    tmp["Debug_RPM_X86_64"] = hotpatch["Debug_RPM_X86_64"]
                    tmp["Debug_RPM_Aarch64"] = hotpatch["Debug_RPM_Aarch64"]
                    tmp["hotpatch_issue"] = hotpatch["hotpatch_issue_link"]
                    tmp["patch"] = hotpatch["patch"]
                    tmp["issue"] = hotpatch["issue"]
                    meta_info.append(tmp)
                except KeyError as error:
                    logger.error(f"校验元数据字段错误，keyerror: {error}")
                    return []

        return meta_info

    def get_version_release(self, meta_info):
        name = meta_info.get("name")
        version = meta_info.get("version")
        release = meta_info.get("release")
        if self.mode == "SGL":
            ver = "%s-%s-%s" % (name.replace("-", "_"), version, release)
        else:
            ver = "%s-%s-%s" % ("ACC", version, release)
        logger.info(f"version-release：{ver}")
        return ver

    def check_version(self, old_meta_info, new_meta_info):
        if self.mode == "ACC":
            last_version_release = self.get_version_release(old_meta_info)
            curr_version_release = self.get_version_release(new_meta_info)
            if CompareVersion.vr_compare(curr_version_release, "LE", last_version_release):
                error_info = "新热补丁版本号%s小于已有热补丁%s，请重新指定热补丁版本和release" % (
                    curr_version_release, last_version_release)
                return self.comment_metadata_pr(error_info)
        elif self.mode == "SGL":
            last_version_release = self.get_version_release(old_meta_info)
            curr_version_release = self.get_version_release(new_meta_info)
            if CompareVersion.vr_compare(curr_version_release, "LE", last_version_release):
                error_info = "新热补丁版本号%s小于已有热补丁%s，请重新指定热补丁版本和release" % (
                    curr_version_release, last_version_release)
                return self.comment_metadata_pr(error_info)
        else:
            return self.comment_metadata_pr("不支持的补丁演进方式，目前支持的演进方式为ACC/SGL")
        logger.info("pre_version_release:%s", last_version_release)
        with open(self.output, "a") as file:
            file.write("pre_version_release:%s\n" % last_version_release)
        return 0

    def check_modify_field(self, version, old_meta_info, new_meta_info):
        # -1 异常场景 0 没有变更 1 其它字段有变更 2 只有status
        modify_flag = 0
        patch_file = []
        if self.patch_list != "null":
            patch_file = list(map(lambda x: x.split("/")[-1], self.patch_list.split()))
        logger.info("patch_file_list:%s", patch_file)

        # 检查字段是否有变更
        old_status = old_meta_info.get("status")
        new_status = new_meta_info.get("status")

        for key, value in old_meta_info.items():
            if new_meta_info.get(key) != value:
                modify_flag = 1
                if old_status == "confirmed":
                    error_info = "热补丁版本号%s已经confirmed, 如果需要更改的话请联系sig maintianer" % version
                    return self.comment_metadata_pr(error_info)

        # 检查本次pr变更的patch文件是否合法，如果已经confirmed，patch文件不允许更改
        patch_name = old_meta_info.get("patch")
        for patch in patch_file:
            if patch in patch_name:
                modify_flag = 1
                if old_status == "confirmed":
                    error_info = "热补丁版本号%s已经confirmed, 如果需要更改的话请联系sig maintianer" % version
                    return self.comment_metadata_pr(error_info)

        # 如果只有status的变更，不用制作热补丁，直接成功
        if old_status == "unconfirmed" and new_status == "confirmed":
            logger.warning("%s only status is modify, don't need make hotpatch" % version)
            modify_flag = 2

        return modify_flag

    def verify_sgl_name(self, curr_meta_info):
        issue_id_list = []
        issue_list = curr_meta_info.get('issue')
        try:
            if isinstance(issue_list, dict):
                issue_id_list.append(issue_list.get("@id"))
            elif isinstance(issue_list, list):
                for issue in issue_list:
                    issue_id_list.append(issue.get("@id"))
            curr_name = curr_meta_info.get("name")
            need_name = "SGL-%s" % ("-".join(issue_id_list))
            if curr_name != need_name:
                error_info = f"热补丁name字段与issue id字段不匹配，当前为：{curr_name}， 应该为：{need_name}"
                return self.comment_metadata_pr(error_info)
        except KeyError as error:
            logger.error(f"get matedata keyerror: {error}")
            return -1
        return 0

    def verify_meta_field(self, meta_info):
        curr_meta_info = meta_info[-1]
        # 检查cve类型合法性
        cve_type = curr_meta_info.get("type")
        if cve_type not in type_dict.keys():
            error_info = f"修复的问题类型{cve_type}不是支持的类型，可选类型[cve/bugfix/feature]，请重新指定"
            return self.comment_metadata_pr(error_info)

        # 热补丁issue检查, 获取issue标题和创建时间
        hotpatch_issue = curr_meta_info.get("hotpatch_issue")
        result = self.check_hotpatch_issue(hotpatch_issue)
        if result < 0:
            return -1

        # 检查SGL模式name字段合法性
        if self.mode == "SGL":
            return self.verify_sgl_name(curr_meta_info)
        return 0

    def check_hotpatch_issue(self, hotpatch_issue):
        hotpatch_issue_resp = self.gitee.get_issue(hotpatch_issue.split("/")[-1])
        logger.warning(hotpatch_issue_resp)
        if not hotpatch_issue_resp:
            return self.comment_metadata_pr("获取热补丁issue失败")

        state = hotpatch_issue_resp.get("state")
        if state in ["closed", "rejected"]:
            return self.comment_metadata_pr("请确认热补丁issue未处于已完成/已关闭状态")
        issue_title = hotpatch_issue_resp.get("title")
        reference_date = hotpatch_issue_resp.get("created_at")
        dates = re.findall(date_pattern, reference_date)
        issue_date = dates[0]
        with open(self.output, "w") as file:
            file.write("issue_title: %s\n" % issue_title)
            file.write("issued-date: %s\n" % issue_date)
        return 0

    def compare_modify_version(self, meta_info):
        # 比较xml中两个相同版本
        changed_version_list = []
        only_status_changed = []
        old_meta_info = []
        work_dir = os.getcwd()

        # 获取本次提交之前的元数据信息
        os.chdir(os.path.join(work_dir, "hotpatch_meta"))
        checkout_cmd = ["git", "checkout", "master"]
        ret, out, _ = command(checkout_cmd)
        if ret:
            raise RuntimeError(f"git checkout master failed, {ret}")
        if os.path.exists(self.input):
            old_meta_info = self.parse_from_meta_file(self.input)
            if not old_meta_info:
                return self.comment_metadata_pr("解析变更前的元数据字段失败，没有获取到有效信息")
        # 比较新旧元数据文件的变更
        new_meta_info = meta_info
        if old_meta_info and new_meta_info:
            # 检查版本号合法性，判断新增热补丁的版本是否大于上个版本
            if len(old_meta_info) != len(new_meta_info):
                result = self.check_version(old_meta_info[-1], new_meta_info[-1])
                if result < 0:
                    return -1
            # 判断其它patch字段是否有变更
            for i in range(len(old_meta_info)):
                version_release = self.get_version_release(old_meta_info[i])
                result = self.check_modify_field(version_release, old_meta_info[i], new_meta_info[i])
                # -1 异常场景 0 没有变更 1 其它字段有变更 2 只有status
                if result == 0:
                    continue
                elif result == 1:
                    logger.warning("version %s is modify", version_release)
                    changed_version_list.append(version_release)
                elif result == 2:
                    only_status_changed.append(version_release)
                else:
                    return -1

        if changed_version_list:
            logger.info("modify_list = %s", changed_version_list)
            with open(self.output, "a") as file:
                file.write("modify_version:%s\n" % " ".join(changed_version_list))
        else:
            if only_status_changed:
                self.gitee.remove_tag(self.pull_request, "ci_processing")
                self.gitee.create_tag(self.pull_request, "ci_successful")
                logger.warning("only status is modify, don't need make hotpatch")

        checkout_cmd = ["git", "checkout", f"pr_{self.pull_request}"]
        ret, out, _ = command(checkout_cmd)
        if ret:
            logger.error(f"git checkout pr_{self.pull_request} failed, {ret}")
            return -1
        os.chdir(work_dir)
        return 0

    def get_update_info(self):
        # 读取xml中的hotpatch字段
        meta_info = self.parse_from_meta_file(self.input)
        if not meta_info:
            return self.comment_metadata_pr("校验元数据字段失败，没有获取到有效信息")
        # 检查cve type和name字段是否合法
        result = self.verify_meta_field(meta_info)
        if result < 0:
            return -1

        # 元数据文件变更对比
        result = self.compare_modify_version(meta_info)
        return result

    def comment_metadata_pr(self, err_info):
        body_str = "热补丁制作流程已中止，错误信息：%s" % err_info
        logger.error(err_info)
        self.gitee.create_pr_comment(self.pull_request, body_str)
        self.gitee.remove_tag(self.pull_request, "ci_processing")
        self.gitee.create_tag(self.pull_request, "ci_failed")
        return -1

    def verify(self):
        self.gitee.remove_tag(self.pull_request, "ci_successful")
        self.gitee.remove_tag(self.pull_request, "ci_failed")
        self.gitee.create_tag(self.pull_request, "ci_processing")
        result = self.get_update_info()
        if result == 0:
            sys.exit(0)
        else:
            sys.exit(1)
