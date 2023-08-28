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
import xml.etree.ElementTree as ET
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

    @staticmethod
    def read_metadata_file(metadata_file):
        try:
            tree = ET.parse(metadata_file)
            root = tree.getroot()
            hotpatch = root.iter('hotpatch')
            return hotpatch
        except IOError:
            raise RuntimeError("read matedata file error")
        except KeyError:
            raise RuntimeError("get matedata key:hotpatch error")

    @staticmethod
    def get_patch_list(hotpatch):
        patch_list = []
        version = 0
        release = 0
        for child in hotpatch:
            patch_list.clear()
            version = child.attrib["version"]
            release = child.attrib["release"]
            patch = child.findall('patch')
            for patch_name in patch:
                patch_list.append(patch_name.text)
        logger.info("version:%s, release:%s, patch_list:%s", version, release, patch_list)
        return version, release, patch_list

    @staticmethod
    def get_version_list(metadata):
        patch_list = []
        patch = []
        try:
            with open(metadata, "r") as file:
                lines = file.readlines()
                package = lines[4].strip()
                patch_list.append(package)
                for line in lines[5:-3]:
                    line = line.strip()
                    if line.startswith("<hotpatch "):
                        patch.clear()
                        patch.append(line)
                    elif line.startswith("</hotpatch>"):
                        patch.append(line.strip())
                        patch_list.append("\n".join(patch))
                    else:
                        patch.append(line)
        except IOError:
            raise RuntimeError("read matedata file error")
        except IndexError:
            raise RuntimeError("matedata file format error")
        return patch_list

    @staticmethod
    def get_version_release(patch_list):
        patch = patch_list.split("\n")[0].strip()
        patch_line = patch.split(" ")
        if len(patch_line) != 6:
            raise RuntimeError("hotpatch line field missed")
        version = patch_line[1].split("=")[1].strip('"')
        release = patch_line[2].split("=")[1].strip('"')
        logger.info(f"version-release：{version}-{release}")
        return f"{version}-{release}"

    @staticmethod
    def get_sgl_pre_version(name, patch_list):
        last_ver = ""
        for patch_i in patch_list:
            patch = patch_i.split("\n")[0].strip()
            patch_line = patch.split(" ")
            if len(patch_line) != 7:
                raise RuntimeError("hotpatch line field missed")
            old_name = patch_line[1].split("=")[1].strip('"')
            if name == old_name:
                version = patch_line[2].split("=")[1].strip('"')
                release = patch_line[3].split("=")[1].strip('"')
                last_ver = "%s-%s-%s" % (old_name.replace("-", "_"), version, release)
        return last_ver

    @staticmethod
    def get_sgl_curr_version(patch_list):
        patch = patch_list.split("\n")[0].strip()
        name = patch.split(" ")[1].split("=")[1].strip('"')
        version = patch.split(" ")[2].split("=")[1].strip('"')
        release = patch.split(" ")[3].split("=")[1].strip('"')
        logger.warning("name:%s, version:%s, release:%s", name, version, release)
        return name, version, release

    def check_version(self, old_patch_list, new_patch_list):
        pre_version_release = ""
        if self.mode == "ACC":
            last_version_release = self.get_version_release(old_patch_list[-1])
            curr_version_release = self.get_version_release(new_patch_list[-1])
            if curr_version_release <= last_version_release:
                error_info = "新热补丁版本号%s小于已有热补丁%s，请重新指定热补丁版本和release" % (
                    curr_version_release, last_version_release)
                self.comment_metadata_pr(error_info)
            pre_version_release = "ACC-%s" % last_version_release
        if self.mode == "SGL":
            name, version, release = self.get_sgl_curr_version(new_patch_list[-1])
            curr_ver = "%s-%s-%s" % (name.replace("-", "_"), version, release)
            last_ver = self.get_sgl_pre_version(name, old_patch_list)
            if curr_ver <= last_ver:
                error_info = "新热补丁版本号%s小于已有热补丁%s，请重新指定热补丁版本和release" % (
                    curr_ver, last_ver)
                self.comment_metadata_pr(error_info)
            pre_version_release = last_ver
        logger.info("pre_version_release:%s", pre_version_release)
        with open(self.output, "a") as file:
            file.write("pre_version_release:%s\n" % pre_version_release)
        return pre_version_release

    def check_if_status_modify(self, version, old_field, new_field):
        # 检查status字段是否有变更
        old_field = old_field.strip().strip("<").strip(">").split()
        new_field = new_field.strip().strip("<").strip(">").split()

        old_status = old_field[-1].split("=")[-1].strip('"')
        new_status = new_field[-1].split("=")[-1].strip('"')

        # 检查status行字段数是否有变化
        if len(old_field) != len(new_field):
            if old_status == "confirmed":
                self.comment_metadata_pr("热补丁版本号%s已经confirmed, 如果需要更改的话请联系sig maintianer" % version)
        else:
            for i in range(len(old_field)):
                if old_field[i] != new_field[i]:
                    if old_status == "confirmed":
                        self.comment_metadata_pr("热补丁版本号%s已经confirmed, 如果需要更改的话请联系sig maintianer" % version)

        return old_status, new_status

    def check_modify_field(self, version, old_patch, new_patch):
        patch_file = []
        if self.patch_list != "null":
            patch_file = list(map(lambda x: x.split("/")[-1], self.patch_list.split()))
        logger.info("patch_file_list:%s", patch_file)

        # 检查同一个version下的字段变更
        old_patch = old_patch.split("\n")
        new_patch = new_patch.split("\n")
        old_status, new_status = self.check_if_status_modify(version, old_patch[0], new_patch[0])

        for i in range(1, len(old_patch)):
            field_name = old_patch[i].split(">")[0].split("<")[1]
            if old_status == "confirmed":
                if old_patch[i] != new_patch[i]:
                    self.comment_metadata_pr("热补丁版本号%s已经confirmed, 如果需要更改的话请联系sig maintianer" % version)
                if field_name.lower() == "patch":
                    patch_name = old_patch[i].split(">")[1].split("<")[0]
                    logger.warning("patch_name:%s", patch_name)
                    if patch_name in patch_file:
                        self.comment_metadata_pr("热补丁版本号%s已经confirmed, 如果需要更改的话请联系sig maintianer" % version)

        if old_status == "unconfirmed" and new_status == "confirmed":
            self.gitee.remove_tag(self.pull_request, "ci_processing")
            self.gitee.create_tag(self.pull_request, "ci_successful")
            logger.warning("%s only status is modify, don't need make hotpatch" % version)
            sys.exit(0)

    def verify_meta_field(self, version, release):
        hotpatch_dict = {}
        logger.info("start verifying meta field")
        hotpatchs = self.read_metadata_file(self.input)
        logger.warning(f"version: {version}, release: {release}")
        for child in hotpatchs:
            issue_id_list = []
            reference_href_list = []
            try:
                logger.info(f"version: {child.attrib['version']}, release: {child.attrib['release']}")
                if child.attrib["version"] == version and child.attrib["release"] == release:
                    cve_type = child.attrib["type"]
                    if cve_type not in type_dict.keys():
                        error_info = f"修复的问题类型{cve_type}不是支持的类型，可选类型[cve/bugfix/feature]，请重新指定"
                        self.comment_metadata_pr(error_info)

                    issue_list = child.findall('issue')
                    for issue in issue_list:
                        issue_id_list.append(issue.attrib["id"])
                        reference_href_list.append(issue.attrib["issue_href"])

                    if self.mode == "SGL":
                        name = child.attrib["name"]
                        ver_name = "SGL-%s" % ("-".join(issue_id_list))
                        if name != ver_name:
                            error_info = f"热补丁name字段与issue id字段不匹配，当前为：{name}， 应该为：{ver_name}"
                            self.comment_metadata_pr(error_info)
                        hotpatch_dict["patch_name"] = name
                    if self.mode == "ACC":
                        hotpatch_dict["patch_name"] = "ACC"
                    src_url = child.find('SRC_RPM').text
                    x86_debug = child.find('Debug_RPM_X86_64').text
                    aarch64_debug = child.find('Debug_RPM_Aarch64').text
                    hotpatch_issue = child.find('hotpatch_issue_link').text
                    logger.info(f"verify meta field success.\ntype:{cve_type}\nissue id:{' '.join(issue_id_list)}\n"
                                f"SRC_RPM:{src_url}\nDebug_RPM_X86_64:{x86_debug}\nDebug_RPM_Aarch64:{aarch64_debug}\n"
                                f"issue_href:{' '.join(reference_href_list)}\nhotpatch_issue:{hotpatch_issue} \n")
                    hotpatch_dict["cve_type"] = cve_type
                    hotpatch_dict["hotpatch_issue"] = hotpatch_issue
                    hotpatch_dict["issue_id"] = issue_id_list
                    hotpatch_dict["reference_href"] = reference_href_list
            except KeyError as error:
                raise RuntimeError(f"get matedata keyerror: {error}")
            except Exception as error:
                raise RuntimeError(f"get matedata error: {error}")
        return hotpatch_dict

    def check_hotpatch_issue(self, hotpatch_issue):
        hotpatch_issue_resp = self.gitee.get_issue(hotpatch_issue.split("/")[-1])
        logger.warning(hotpatch_issue_resp)
        if not hotpatch_issue_resp:
            self.comment_metadata_pr("获取热补丁issue失败")

        state = hotpatch_issue_resp.get("state")
        if state in ["closed", "rejected"]:
            self.comment_metadata_pr("请确认热补丁issue未处于已完成/已关闭状态")
        issue_title = hotpatch_issue_resp.get("title")
        reference_date = hotpatch_issue_resp.get("created_at")
        logger.warning("issue_title: %s" % issue_title)
        logger.warning("reference_date: %s" % reference_date)
        dates = re.findall(date_pattern, reference_date)
        issue_date = dates[0]
        with open(self.output, "w") as file:
            file.write("issue_title: %s\n" % issue_title)
            file.write("issued-date: %s\n" % issue_date)

    def compare_modify_version(self):
        # 比较xml中两个相同版本
        modify_list = []
        old_patch_list = []
        new_patch_list = []
        work_dir = os.getcwd()

        # 获取本次提交的元数据信息
        if os.path.exists(self.input):
            new_patch_list = self.get_version_list(self.input)

        # 获取本次提交之前的元数据信息
        os.chdir(os.path.join(work_dir, "hotpatch_meta"))
        checkout_cmd = ["git", "checkout", "master"]
        ret, out, _ = command(checkout_cmd)
        if ret:
            raise RuntimeError(f"git checkout master failed, {ret}")
        if os.path.exists(self.input):
            old_patch_list = self.get_version_list(self.input)

        # 比较新旧元数据文件的变更
        if old_patch_list and new_patch_list:
            # 判断Package name字段是否有变更
            if old_patch_list[0] != new_patch_list[0]:
                error_info = "元数据文件中package name字段有变更，请确认"
                self.comment_metadata_pr(error_info)
            old_patch_list = old_patch_list[1:]
            new_patch_list = new_patch_list[1:]

            # 判断新增热补丁的版本是否大于上个版本
            if len(old_patch_list) != len(new_patch_list):
                self.check_version(old_patch_list, new_patch_list)

            # 判断其它patch字段是否有变更
            for i in range(len(old_patch_list)):
                if self.mode == "ACC":
                    version_release = self.get_version_release(old_patch_list[i])
                    version_release = "ACC-" + version_release
                if self.mode == "SGL":
                    name, version, release = self.get_sgl_curr_version(new_patch_list[-1])
                    version_release = "%s-%s-%s" % (name.replace("-", "_"), version, release)

                self.check_modify_field(version_release, old_patch_list[i], new_patch_list[i])
                if old_patch_list[i] != new_patch_list[i]:
                    logger.warning("version %s is modify", version_release)
                    modify_list.append(version_release)

        # 变更的patch字段是否发布，已发布的不允许修改
        if modify_list:
            logger.info("modify_list = %s", modify_list)
            with open(self.output, "a") as file:
                file.write("modify_version:%s\n" % " ".join(modify_list))

        checkout_cmd = ["git", "checkout", f"pr_{self.pull_request}"]
        ret, out, _ = command(checkout_cmd)
        if ret:
            raise RuntimeError(f"git checkout pr_{self.pull_request} failed, {ret}")
        os.chdir(work_dir)

    def get_update_info(self):
        # 读取xml中的hotpatch字段
        hotpatchs = self.read_metadata_file(self.input)

        # 获取最新的version、release 和补丁文件
        version, release, patch_list = self.get_patch_list(hotpatchs)

        # 检查xml中字段是否都存在
        hotpatch_dict = self.verify_meta_field(version, release)

        # 热补丁issue检查, 获取issue标题和创建时间
        hotpatch_issue_url = hotpatch_dict.get("hotpatch_issue")
        self.check_hotpatch_issue(hotpatch_issue_url)

        # 元数据文件变更对比
        self.compare_modify_version()

    def comment_metadata_pr(self, err_info):
        body_str = "热补丁制作流程已中止，错误信息：%s" % err_info
        logger.error(err_info)
        self.gitee.create_pr_comment(self.pull_request, body_str)
        self.gitee.remove_tag(self.pull_request, "ci_processing")
        self.gitee.create_tag(self.pull_request, "ci_failed")
        sys.exit(1)

    def verify(self):
        self.gitee.remove_tag(self.pull_request, "ci_successful")
        self.gitee.remove_tag(self.pull_request, "ci_failed")
        self.gitee.create_tag(self.pull_request, "ci_processing")
        self.get_update_info()
        sys.exit(0)


