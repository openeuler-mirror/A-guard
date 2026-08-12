#!/bin/bash
# ******************************************************************************
# Copyright (c) Huawei Technologies Co., Ltd. 2020-2026. All rights reserved.
# licensed under the Mulan PSL v2.
# You can use this software according to the terms and conditions of the Mulan PSL v2.
# You may obtain a copy of Mulan PSL v2 at:
#     http://license.coscl.org.cn/MulanPSL2
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FIT FOR A PARTICULAR
# PURPOSE.
# See the Mulan PSL v2 for more details. 
#
# GitCode Action 编译门禁入口脚本
# 对应 Jenkins 时代的 ". ${shell_path}/ci_guard/ci-guard.sh" + 调用 main()
# 由 workflow (.gitcode/workflows/ci.yml build job) 注入 ACTION_* 环境变量，
# 本脚本将其映射为 ci-guard.sh main() 所需的 Jenkins 变量，source 后调用 main()。
#
# 环境变量约定（由 workflow 注入）：
#   ACTION_SHELL_PATH:        A-guard 仓库路径
#   ACTION_SHELL_PATHEOE:     openeuler-jenkins 仓库路径
#   ACTION_REPO:              仓库名
#   ACTION_PR_NUMBER:         PR 编号
#   ACTION_TARGET_BRANCH:     PR 目标分支
#   ACTION_COMMITTER:         PR 提交者
#   ACTION_ARCH:              编译架构 (x86_64/aarch64)
#   ACTION_VARIANT:           构建变体（可选，如 64k；仅特定分支支持，见 support_64k_branch）
#   ACTION_PLATFORM:          代码平台 (gitcode)
#   ACTION_OWNER:             PR 目标仓实际 owner（ACTION_COMMUNITY 为改名前旧名，过渡兼容）
#   ACTION_COMMENT_ID:        PR 评论 ID（可选）
#   ACTION_GITCODE_TOKEN:     GitCode API token (atomgit.token)
#   ACTION_GITEE_TOKEN:       Gitee API token（可选）
#   ACTION_MYSQL_HOST/PORT/USER_PASSWD: MySQL 连接
#   ACTION_OAUTH_ACCOUNT/PASSWORD:      EBS OAuth 凭据
#   ACTION_SSH_KEY_CONTENT:   文件服务器 SSH 私钥内容（优先，本脚本落盘+规范化）
#   ACTION_SSH_KEY:           文件服务器 SSH key 文件路径（回退，content 为空时使用）
#   ACTION_REPO_SERVER:       文件服务器地址
#   ACTION_WORKSPACE:         工作目录
#   ACTION_ARTIFACT_DIR:      AC 制品下载根目录（用于还原 spec_list/support_arch，可选）
#   ACTION_JENKINS_HOME:      jenkins 用户 home（默认 $HOME）
#   ACTION_JOB_NAME / ACTION_RUN_ID: 用于 print_job 评论
#   ACTION_EBS_SERVER:        EBS 服务器（可选，默认 https://eulermaker.openeuler.openatom.cn 公网域名）
#   ACTION_REQUIRES_REPO:     依赖仓库（可选）
# ******************************************************************************

# shell 路径
export shell_path=${ACTION_SHELL_PATH}
export shell_pathoe=${ACTION_SHELL_PATHEOE}

# PR 上下文
export repo=${ACTION_REPO}
export prid=${ACTION_PR_NUMBER}
export tbranch=${ACTION_TARGET_BRANCH}
export committer=${ACTION_COMMITTER}
export arch=${ACTION_ARCH}
export variant=${ACTION_VARIANT:-}
export platform=${ACTION_PLATFORM:-gitcode}
export repo_owner=${ACTION_OWNER:-${ACTION_COMMUNITY:-src-openeuler}}
export commentid=${ACTION_COMMENT_ID:-}

# 代码平台 Token
export gitcodeToken=${ACTION_GITCODE_TOKEN}
export GiteeToken=${ACTION_GITEE_TOKEN:-}

# MySQL
export MysqldbHost=${ACTION_MYSQL_HOST}
export MysqldbPort=${ACTION_MYSQL_PORT:-3306}
export MysqlUserPasswd=${ACTION_MYSQL_USER_PASSWD}

# EBS OAuth
export OauthAccount=${ACTION_OAUTH_ACCOUNT}
export OauthPassword=${ACTION_OAUTH_PASSWORD}

# 文件服务器
# 优先使用 ACTION_SSH_KEY_CONTENT（私钥内容，本脚本负责落盘+规范化，与 gate 侧
# gate_entry.py 的模式一致：ci.yml 只注入 Secret 内容，不写 key 文件）；
# 为空时回退 ACTION_SSH_KEY（已存在的 key 文件路径）
if [[ -n "${ACTION_SSH_KEY_CONTENT}" ]]; then
    ssh_key_file="${ACTION_WORKSPACE}/.ci_ssh_key"
    # 规范化 Secret 保存时的常见残留：字面 \n 转义、CRLF 行尾、行首尾多余空白
    key_content="${ACTION_SSH_KEY_CONTENT//\\n/$'\n'}"
    printf '%s\n' "${key_content}" | tr -d '\r' |
        sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' >"${ssh_key_file}"
    chmod 600 "${ssh_key_file}"
    # 用完即删：脚本任何退出路径（含异常中断）都清理落盘的私钥，
    # 避免私钥在复用型 runner 上残留（与 gate 侧 gate_entry.py 的 finally 删除一致）
    trap 'rm -f "${ssh_key_file}"' EXIT
    export SaveBuildRPM2Repo="${ssh_key_file}"
elif [[ -n "${ACTION_SSH_KEY}" ]]; then
    export SaveBuildRPM2Repo=${ACTION_SSH_KEY}
fi
export repo_server=${ACTION_REPO_SERVER}

# 工作目录 / 环境
export WORKSPACE=${ACTION_WORKSPACE}
export JENKINS_HOME=${ACTION_JENKINS_HOME:-$HOME}
export JOB_NAME=${ACTION_JOB_NAME:-A-Guard}
export BUILD_ID=${ACTION_RUN_ID:-0}

# EBS 服务器（config.yaml 有默认值，这里保证非空以覆盖 sed 注入）
export ebs_server=${ACTION_EBS_SERVER:-https://eulermaker.openeuler.openatom.cn}

# 固定使用 EBS 构建后端
export build_env=ebs

# 64k 变体仅特定分支支持：目标分支不在 support_64k_branch 清单内时直接跳过
if [[ -n "${variant}" ]]; then
    support_64k_branch_file="${shell_path}/ci_guard/conf/support_64k_branch"
    if [[ ! -f "${support_64k_branch_file}" ]] || ! grep -qx "${tbranch}" "${support_64k_branch_file}"; then
        echo "当前分支 ${tbranch} 不支持64k编译，跳过"
        # 留存跳过原因供 artifact 收集（upload-artifact 的 *.log 通配），避免空目录上传失败
        echo "$(date '+%F %T') branch ${tbranch} not in support_64k_branch, skip variant=${variant} build" \
            >>"${ACTION_WORKSPACE}/skip_variant.log"
        exit 0
    fi
fi

# ******************************************************************************
# spec_list/support_arch 还原（从 AC artifact 到构建 workspace）
# 若制品文件不可读导致还原失败，fail-soft 走保守全架构构建，不阻断门禁。
# ******************************************************************************
_restore_ac_spec_files() {
    local search_root="${ACTION_ARTIFACT_DIR:-}"
    local ws="${ACTION_WORKSPACE}"
    # 先清残留
    rm -f "${ws}/spec_list" "${ws}"/support_arch_* 2>/dev/null
    # 按文件名 find 定位还原，不依赖具体目录结构
    if [[ -z "${search_root}" || ! -d "${search_root}" ]]; then
        echo "ACTION_ARTIFACT_DIR 无效（${search_root:-未注入}），回退 cwd 搜索"
        search_root=.
    fi
    find "${search_root}" -maxdepth 5 -type f \( -name spec_list -o -name 'support_arch_*' \) \
        -exec cp -f {} "${ws}/" \; \
        || echo "warn: spec_list/support_arch 还原失败，走保守全架构构建"
    # glob 无匹配时字面量传给 ls 会非零退出，须用 nullglob 判断有无文件
    shopt -s nullglob
    local restored=()
    [[ -f "${ws}/spec_list" ]] && restored+=("${ws}/spec_list")
    restored+=("${ws}"/support_arch_*)
    shopt -u nullglob
    if [[ ${#restored[@]} -gt 0 ]]; then
        ls -l "${restored[@]}"
    else
        echo "无 spec_list/support_arch 制品（AC 未生成或下载失败，走保守全架构构建）"
    fi
}

# source 原始入口脚本，保持其一切逻辑不变
source ${shell_path}/ci_guard/ci-guard.sh

# 还原 AC 传递的 spec_list/support_arch
_restore_ac_spec_files

# 调用主流程
main
BUILD_RC=$?
echo "==== build_entry: BUILD_RC=${BUILD_RC} ===="

# 导出本架构 build 成败到 records-course（随 artifact 上传），供 build-comment 汇总
mkdir -p "${ACTION_WORKSPACE}/records-course"
echo "${BUILD_RC}" >"${ACTION_WORKSPACE}/records-course/${repo}_${prid}_${arch}${variant_suffix}_build_rc" ||
    echo "build_rc 文件写入失败，忽略（不影响 build 结果）"

echo "$(date '+%F %T') build_entry arch=${arch}${variant_suffix} rc=${BUILD_RC}" \
    >"${ACTION_WORKSPACE}/build_entry.log"

# 以 build job 的聚合退出码返回，runner 据此判定 job 成败，ci-final 再据此打 ci_successful/ci_failed
exit ${BUILD_RC}
