#!/bin/bash
# ******************************************************************************
# GitCode Action 编译门禁入口脚本
# 对应 Jenkins 时代的 ". ${shell_path}/ci_guard/ci-guard.sh" + 调用 main()
# 由 workflow (.gitcode/workflows/ci.yml build job) 注入 ACTION_* 环境变量，
# 本脚本将其映射为 ci-guard.sh main() 所需的 Jenkins 变量，source 后调用 main()。
#
# 本脚本不修改原始 ci-guard.sh，OBS 相关逻辑（config_osc/update_repo）保留不动，
# 编译后端固定走 EBS（build_env=ebs）。
#
# 环境变量约定（由 workflow 注入）：
#   ACTION_SHELL_PATH:        A-guard 仓库路径
#   ACTION_SHELL_PATHEOE:     openeuler-jenkins 仓库路径
#   ACTION_REPO:              仓库名
#   ACTION_PR_NUMBER:         PR 编号
#   ACTION_TARGET_BRANCH:     PR 目标分支
#   ACTION_COMMITTER:         PR 提交者
#   ACTION_ARCH:              编译架构 (x86_64/aarch64)
#   ACTION_VARIANT:           构建变体（可选，如 64k）
#   ACTION_PLATFORM:          代码平台 (gitcode)
#   ACTION_COMMUNITY:         仓库归属 (src-openeuler)
#   ACTION_COMMENT_ID:        PR 评论 ID（可选）
#   ACTION_GITCODE_TOKEN:     GitCode API token (atomgit.token)
#   ACTION_GITEE_TOKEN:       Gitee API token（可选）
#   ACTION_MYSQL_HOST/PORT/USER_PASSWD: MySQL 连接
#   ACTION_OAUTH_ACCOUNT/PASSWORD:      EBS OAuth 凭据
#   ACTION_SSH_KEY_CONTENT:   文件服务器 SSH 私钥内容（优先，本脚本落盘+规范化）
#   ACTION_SSH_KEY:           文件服务器 SSH key 文件路径（回退，content 为空时使用）
#   ACTION_REPO_SERVER:       文件服务器地址
#   ACTION_WORKSPACE:         工作目录
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
export repo_owner=${ACTION_COMMUNITY:-src-openeuler}
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
    # （与 gate 侧 gate_entry.py 的 _upload_support_arch 处理保持一致）
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

# OBS 相关变量（保留不删，build_env=ebs 不进入 config_osc/update_repo 分支）
export OBSSecondaryUserName=${ACTION_OBS_USER:-}
export OBSSecondaryPassword=${ACTION_OBS_PASSWORD:-}
export obs_webui_host=${ACTION_OBS_HOST:-}
export buddy=${ACTION_REQUIRES_REPO:-}

# 工作目录 / 环境
export WORKSPACE=${ACTION_WORKSPACE}
export JENKINS_HOME=${ACTION_JENKINS_HOME:-$HOME}
export JOB_NAME=${ACTION_JOB_NAME:-A-Guard}
export BUILD_ID=${ACTION_RUN_ID:-0}

# EBS 服务器（config.yaml 有默认值，这里保证非空以覆盖 sed 注入）
export ebs_server=${ACTION_EBS_SERVER:-https://eulermaker.openeuler.openatom.cn}

# 固定使用 EBS 构建后端
export build_env=ebs

# source 原始入口脚本，保持其一切逻辑不变
source ${shell_path}/ci_guard/ci-guard.sh

# 调用主流程
main
BUILD_RC=$?
echo "==== build_entry: BUILD_RC=${BUILD_RC} ===="

# 评论 build 门禁结果（失败也会评论）。评论异常不改变 job 退出码。
export ACTION_BUILD_RESULT=${BUILD_RC}
(cd ${shell_pathoe} && python3 -m src.build.comment_entry) ||
    echo "build 评论执行失败，忽略（不影响 build 结果）"

# 以 build job 的聚合退出码返回，runner 据此判定 job 成败，ci-final 再据此打 ci_successful/ci_failed
exit ${BUILD_RC}
