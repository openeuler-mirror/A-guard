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

import json
import re
import random
from json import JSONDecodeError
from core import ProcessRecords
from command import command
from logger import logger
from conf import config
from constant import (
    max_abi_change_effects_number,
    max_change_effects_number,
    max_random_number,
)


class Analysis:
    """
    Package change difference point analysis and change impact scope analysis classes
    """

    def __init__(self, diff_file=None):
        self.diff_file = diff_file
        self.package = config.repo
        self.pr_num = str(config.pr)
        if not all([self.package, self.pr_num]):
            raise RuntimeError(
                "Please check whether the path, account and password of obs are fully configured"
            )

    def _match_packge_name(self, rpm_name, choice=True):
        """
        match package name
        Args:
            rpm_name: rpm package name

        Returns:
            package: package name
        """
        regex_content = r"-\d+:.*" if choice else r"-(\d|[a-zA-Z]).*"
        return re.sub(regex_content, "", rpm_name)

    def _analysis_depends(self, output):
        """
        Analyze result after the command is executed.
        The.src end indicates the build dependency and the rest indicates the installation dependency
        Args:
            output: Result after the command is executed(dnf repoquery --whatdepends package)

        Returns:
            be_build_dependeds: List of built dependencies
            be_install_depended: List of installed dependencies
        """
        be_build_dependeds, be_install_depended = list(), list()
        for out_put in output.splitlines(False):
            if out_put.endswith(".src"):
                be_build_dependeds.append(self._match_packge_name(out_put))
            else:
                be_install_depended.append(self._match_packge_name(out_put))
        return list(set(be_build_dependeds)), list(set(be_install_depended))

    def _record_log(self, code, error, package_name):
        """
        shell name execution error logging
        Args:
            code: shell command execution return status
            error: error message
            package_name: package name
        """
        if code or error:
            logger.error(
                f"analysis {package_name} of dependencies failed because {error}"
            )
            raise RuntimeError(
                f"analysis {package_name} of dependencies failed because {error}"
            )

    def _dependent_data_combination(self, *args):
        """
        If more than 20 packages of a single type are analyzed by dependency analysis,
        15 packages are randomly selected for verification.
        You can first pick 5 from the packages affected by abi (if there are more than 5),
        and then randomly pick 10 from the other dnf analysis
            args:
                be_build_depended: The build of the package affects the package
                be_install_depended: The install of the package affects the package
                abi_change_effects: Packages affected by abi changes
                rpm_name: rpm package name
                effect_detail: Data Combination dictionary
        Returns:
            effect_detail: data impacted after analysis
            demo: {'rpm package': {'be_build_depended': ['librsvg2'],
                                   'be_install_depended': ['libatasmart-devel', 'babl-vala']}}
        """
        (
            be_build_depended,
            be_install_depended,
            abi_change_effects,
            rpm_name,
            effect_detail,
        ) = args
        abi_change_effects = (
            random.sample(abi_change_effects, max_abi_change_effects_number)
            if len(abi_change_effects) >= max_abi_change_effects_number
            else abi_change_effects
        )
        target_number = max_random_number - len(abi_change_effects)
        if len(be_build_depended) + len(be_install_depended) >= target_number:
            while True:
                be_build_depended_num = (
                    random.randint(1, target_number - 1) if be_build_depended else 0
                )
                if be_build_depended_num < len(
                    be_build_depended
                ) and target_number - be_build_depended_num < len(be_install_depended):
                    be_install_depended_num = target_number - be_build_depended_num
                    _ = [
                        be_build_depended.append(abi_change_effect)
                        for abi_change_effect in abi_change_effects
                        if abi_change_effect not in be_install_depended
                    ]
                    effect_detail.update(
                        {
                            rpm_name: dict(
                                be_build_depended=random.sample(
                                    be_build_depended, be_build_depended_num
                                ),
                                be_install_depended=random.sample(
                                    be_install_depended, be_install_depended_num
                                ),
                            )
                        }
                    )
                    break
        return effect_detail

    def depended_analysis_package(self, packages):
        """
        Packages are analyzed for dependencies
        Args:
            rpm_name: rpm package name

        Returns:
           be_build_components: Compile dependency impact list
           be_install_components: Install Dependency Impact List
        """

        def _cmds(package_name):
            """
            Executing shell Commands
            Args:
                package_name: package name

            Returns:
                code: code of executing the command
                output: Result of executing the command
                error: error of executing the command
            """
            cmds = [
                "dnf",
                f"--setopt=reposdir={config.workspace}",
                "repoquery",
                "--whatdepends",
                package_name,
            ]
            code, output, error = command(cmds)
            self._record_log(code, error, package_name)
            return code, output, error

        if isinstance(packages, str):
            _, output, _ = _cmds(packages)

            return self._analysis_depends(output)
        else:
            be_build_components, be_install_components = list(), list()
            for package in packages:
                _, output, _ = _cmds(package)
                be_build_dependeds, be_install_depended = self._analysis_depends(output)
                be_build_components.extend(be_build_dependeds)
                be_install_components.extend(be_install_depended)
            return list(set(be_build_components)), list(set(be_install_components))

    def package_dependencies_analyzed(self, result):
        """
        package dependencies analyzed
        Args:
            analysis_content:

        Returns:
            effect_detail (dict):
            demo:
                {'rpma': {'be_build_depended': ['xxx'],
                         'be_install_depended': ['xxx']},
                 'rpmb': {'be_build_depended': ['xxx'],
                         'be_install_depended': ['xxx']}}
        """
        effect_detail = dict()
        analysis_content = result.get("analysis_content", {})
        for rpm_name, changed_values in analysis_content.items():
            abi_change_effects = [
                self._match_packge_name(abi_rpm_name, choice=False)
                for abi_rpm_name in changed_values.get("abi_change_effect", [])
                if self._match_packge_name(abi_rpm_name, choice=False) != rpm_name
            ]
            need_be_analysis_packages = (
                rpm_name
                if not changed_values.get("changed_provides")
                else changed_values.get("changed_provides", list())
            )
            be_build_depended, be_install_depended = self.depended_analysis_package(
                need_be_analysis_packages
            )
            if rpm_name in be_install_depended[:]:
                be_install_depended.remove(rpm_name)
            if rpm_name in be_build_depended[:]:
                be_build_depended.remove(rpm_name)
            if (
                len(be_build_depended)
                + len(be_install_depended)
                + len(abi_change_effects)
                >= max_change_effects_number
            ):
                args = (
                    be_build_depended,
                    be_install_depended,
                    abi_change_effects,
                    rpm_name,
                    effect_detail,
                )
                effect_detail = self._dependent_data_combination(*args)
            else:
                for abi_change_effect in abi_change_effects:
                    if abi_change_effect not in be_install_depended:
                        be_build_depended.append(abi_change_effect)
                effect_detail.update(
                    {
                        rpm_name: dict(
                            be_build_depended=be_build_depended,
                            be_install_depended=be_install_depended,
                        )
                    }
                )
        return effect_detail

    def depended_analysis(self):
        """
        According to the change points analyzed by the _diff_analysis method,
        the build and installation dependencies of the package are analyzed.
        """
        diff_analysis_result = self._diff_analysis()
        effect_detail = self.package_dependencies_analyzed(diff_analysis_result)
        effect_result = any(
            detail.get("be_build_depended") or detail.get("be_install_depended")
            for _, detail in effect_detail.items()
        )
        need_verify = True if effect_result else False
        diff_analysis = dict(effect_detail=effect_detail, need_verify=need_verify)
        process_record = ProcessRecords(self.package, self.pr_num)
        process_record.update_check_options(
            steps="diff_analysis",
            check_result=diff_analysis,
        )
        return diff_analysis

    def _diff_analysis(self):
        """
        Analyze the package changes and return to the change points that need to continue to be verified
        :return Analysis results, e.g.:
        {
            "need_analysis": true,
            "analysis_content": {
                "rpmA": {
                    "changed_provides": [
                        "componment1",
                        "componment2"
                    ],
                    "abi_change_effect": [
                        "rpm1",
                        "rpm2",
                        "rpm3"
                    ]
                }
            }
        }
        """
        analysis_result = dict(analysis_content={}, need_analysis=False)
        with open(self.diff_file, "r", encoding="utf-8") as df:
            try:
                compare_result = json.load(df)
                diff_content = (
                    compare_result.get("compare_details")
                    .get("diff")
                    .get("diff_details")
                )
            except (JSONDecodeError, AttributeError, FileNotFoundError) as error:
                logger.error(
                    f"Failed to parse the package change result file {self.diff_file}, message is:{error}"
                )
                return analysis_result

        if not diff_content:
            logger.info("No changes to the package")
            return analysis_result

        for rpm_name, rpm_diff in diff_content.items():
            rpm_provide_diff = rpm_diff.get("rpm provides", {}).get("less", [])
            rpm_abi_effect = rpm_diff.get("rpm symbol", {}).get(
                "total_effect_other_rpm", []
            )
            if any([rpm_provide_diff, rpm_abi_effect]):
                analysis_result["analysis_content"][rpm_name] = dict(
                    changed_provides=rpm_provide_diff, abi_change_effect=rpm_abi_effect
                )
        logger.info(f"analysis_result: {analysis_result}")
        return analysis_result
