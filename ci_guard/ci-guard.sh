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
# ******************************************************************************/
JENKINS_HOME=/home/jenkins
SCRIPT_CMD=${shell_path}/ci_guard/ci.py

# 构建变体标识（可选），如 64k
variant=${variant:-""}
if [[ -n "$variant" ]]; then
    variant_suffix="_${variant}"
else
    variant_suffix=""
fi

repo_comment="${repo}_${prid}_${arch}${variant_suffix}_comment"
SCRIPT_PATCH=${shell_pathoe}/src/build

# 公共 shell 函数库（config_oecp_db 等，来自 openeuler-jenkins 仓库部署目录）
. ${shell_pathoe}/src/lib/lib.sh

# 代码平台读写 token：Jenkins 由 job 绑定 gitcodeTokenRead / gitcodeTokenWrite；
# Action 由 build_entry.sh 从 ACTION_* 映射后导出 GITCODE_TOKEN_READ / WRITE。
# 旧 job 兼容（ADR-028）：新变量逐项优先，缺失时回退旧 gitcodeToken 并告警。
_legacy_code_token="${gitcodeToken:-}"
if [[ -n "${_legacy_code_token}" ]] && { [[ -z "${GITCODE_TOKEN_READ:-}${gitcodeTokenRead:-}" ]] || [[ -z "${GITCODE_TOKEN_WRITE:-}${gitcodeTokenWrite:-}" ]]; }; then
    echo "[WARN] gitcodeTokenRead/gitcodeTokenWrite 未配置，回退旧 gitcodeToken" >&2
fi
export GITCODE_TOKEN_READ="${GITCODE_TOKEN_READ:-${gitcodeTokenRead:-${_legacy_code_token}}}"
export GITCODE_TOKEN_WRITE="${GITCODE_TOKEN_WRITE:-${gitcodeTokenWrite:-${_legacy_code_token}}}"
export gitcodeTokenRead="${gitcodeTokenRead:-${GITCODE_TOKEN_READ}}"
export gitcodeTokenWrite="${gitcodeTokenWrite:-${GITCODE_TOKEN_WRITE}}"

# build 阶段需要代码平台 token；M3 的 install phase 不经过此检查
function require_code_tokens() {
    if [[ "${platform}" == "github" ]]; then
        return 0
    fi
    : "${GITCODE_TOKEN_READ:?GITCODE_TOKEN_READ is required (gitcodeTokenRead or gitcodeToken)}"
    : "${GITCODE_TOKEN_WRITE:?GITCODE_TOKEN_WRITE is required (gitcodeTokenWrite or gitcodeToken)}"
}

if [[ ${platform} == "github" ]]; then
    repo_server_test_tail="-github"
    pr=https://github.com/${repo_owner}/${repo}/pull/${prid}
elif [[ ${platform} == "gitee" ]]; then
    repo_server_test_tail=""
    pr=https://gitee.com/${repo_owner}/${repo}/pulls/${prid}
else
    repo_server_test_tail=""
    pr=https://atomgit.com/${repo_owner}/${repo}/pull/${prid}
fi

fileserver_user_path="/repo/openeuler/src-openeuler${repo_server_test_tail}/${tbranch}/${committer}/${repo}/${arch}${variant_suffix}/${prid}/${repo_comment}/$commentid"

function repo_owner_judge() {
    if [[ "${repo_owner}" == "" ]]; then
        repo_owner="src-openeuler"
    fi
    fileserver_tmpfile_path="/repo/soe${repo_server_test_tail}/check_item"
}

function remote_dir_make() {
    # run before save rpm, reset remote dir
    remote_dir_reset_cmd=$(
        cat <<EOF
if [[ ! -d "$fileserver_user_path" ]]; then
    mkdir -p $fileserver_user_path
fi
if [[ \$(ls -A "$fileserver_user_path" | grep ".log") ]]; then
    rm $fileserver_user_path/*.log
fi
if [[ ! -d "$fileserver_tmpfile_path" ]]; then
    mkdir -p $fileserver_tmpfile_path
fi
if [[ -e "$fileserver_tmpfile_path/${repo}-${arch}-${prid}" ]]; then
    rm $fileserver_tmpfile_path/${repo}-${arch}-${prid}
fi
# 清理上一轮残留的 comment 结果文件
if [[ -e "$fileserver_tmpfile_path/${repo_comment}" ]]; then
    rm $fileserver_tmpfile_path/${repo_comment}
fi
EOF
    )
    ssh -i ${SaveBuildRPM2Repo} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR root@${repo_server} "$remote_dir_reset_cmd"
}

function update_config() {
    { set +x; } 2>/dev/null
    echo "============ Start synchronizing jenkins environment variables ============"
    local config_file="${shell_path}/ci_guard/conf/config.yaml"
    # 敏感值通过环境变量进入子进程，不出现在 sed/awk 等命令的 argv 中；
    # 按行替换目标 key，保留注释、空行、缩进与 variant_macros 等嵌套结构
    export MysqlUserPasswd buddy repo_owner repo_server WORKSPACE arch \
        prid repo committer MysqldbHost MysqldbPort commentid tbranch ebs_server platform variant \
        GITCODE_TOKEN_READ GITCODE_TOKEN_WRITE
    python3 - "${config_file}" <<'PY'
import os
import sys

path = sys.argv[1]
values = {
    "atomgit_token": os.environ.get("GITCODE_TOKEN_READ", ""),
    "atomgit_write_token": os.environ.get("GITCODE_TOKEN_WRITE", ""),
    "requires_repo": os.environ.get("buddy", ""),
    "warehouse_owner": os.environ.get("repo_owner", ""),
    "files_server": os.environ.get("repo_server", ""),
    "workspace": os.environ.get("WORKSPACE", ""),
    "arch": os.environ.get("arch", ""),
    "pr": os.environ.get("prid", ""),
    "repo": os.environ.get("repo", ""),
    "committer": os.environ.get("committer", ""),
    "db_host": os.environ.get("MysqldbHost", ""),
    "port": os.environ.get("MysqldbPort", ""),
    "user_passwd": os.environ.get("MysqlUserPasswd", ""),
    "commentid": os.environ.get("commentid", ""),
    "branch": os.environ.get("tbranch", ""),
    "ebs_server": os.environ.get("ebs_server", ""),
    "platform": os.environ.get("platform", ""),
    "variant": os.environ.get("variant", ""),
}

lines = []
with open(path, encoding="utf-8") as config_file:
    for line in config_file:
        key = None
        if not line.startswith((" ", "\t")) and ":" in line:
            key = line.split(":", 1)[0]
        if key in values:
            lines.append("{}: {}\n".format(key, values[key]))
        else:
            lines.append(line)

with open(path, "w", encoding="utf-8") as config_file:
    config_file.writelines(lines)
PY
    chmod 600 "${config_file}"
    echo "End of synchronous config"
    if [ "${CI_DEBUG:-false}" == "true" ]; then
        set -x
    fi
}

function clean_secrets() {
    { set +x; } 2>/dev/null
    local config_file="${shell_path}/ci_guard/conf/config.yaml"
    if [ -f "${config_file}" ]; then
        python3 - "${config_file}" <<'PY'
import sys

path = sys.argv[1]
secret_keys = {"atomgit_token", "atomgit_write_token", "user_passwd"}
lines = []
with open(path, encoding="utf-8") as config_file:
    for line in config_file:
        key = None
        if not line.startswith((" ", "\t")) and ":" in line:
            key = line.split(":", 1)[0]
        if key in secret_keys:
            lines.append("{}:\n".format(key))
        else:
            lines.append(line)
with open(path, "w", encoding="utf-8") as config_file:
    config_file.writelines(lines)
PY
        chmod 600 "${config_file}"
    fi
    # EBS 配置含 OAuth 凭据，用后删除
    if [ -f "$HOME/.config/cli/defaults/config.yaml" ]; then
        shred -u "$HOME/.config/cli/defaults/config.yaml" 2>/dev/null \
            || rm -f "$HOME/.config/cli/defaults/config.yaml"
    fi
    # Action 链路落盘的 SSH 私钥：main() 的 EXIT trap 会覆盖 build_entry.sh 的同名 trap，
    # 在此兜底删除（Jenkins 链路不存在该文件）
    if [ -n "${ACTION_WORKSPACE:-}" ] && [ -f "${ACTION_WORKSPACE}/.ci_ssh_key" ]; then
        shred -u "${ACTION_WORKSPACE}/.ci_ssh_key" 2>/dev/null \
            || rm -f "${ACTION_WORKSPACE}/.ci_ssh_key"
    fi
}

function scp_remote_service() {
    echo "Start copy the check result file to the remote file server"
    local comment_file_path="$WORKSPACE/records-course/${repo_comment}"
    local masked_file="${comment_file_path}.masked"
    chmod 755 "${comment_file_path}"
    # comment 文件是 JSON：按 JSON 模式脱敏，只替换敏感 key 的 value，保持 key/引号/结构合法
    if ! mask_sensitive --json < "${comment_file_path}" > "${masked_file}"; then
        echo "ERROR: mask_sensitive failed for ${comment_file_path}, abort upload"
        rm -f "${masked_file}"
        return 1
    fi
    if ! python3 -m json.tool "${masked_file}" >/dev/null 2>&1; then
        echo "ERROR: masked comment file is not valid JSON, abort upload"
        rm -f "${masked_file}"
        return 1
    fi
    mv "${masked_file}" "${comment_file_path}"
    chmod 755 "${comment_file_path}"
    cat "${comment_file_path}"
    echo "${fileserver_tmpfile_path}"
    retry_command "scp -i ${SaveBuildRPM2Repo} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR ${comment_file_path} root@${repo_server}:$fileserver_tmpfile_path"
}

function check_single_install() {
    echo "============ Start check single install ============"
    if [[ -n "$variant" ]]; then
        python3 $SCRIPT_CMD install -a $arch -pr $pr -tb $tbranch -p $repo --variant $variant
    else
        python3 $SCRIPT_CMD install -a $arch -pr $pr -tb $tbranch -p $repo
    fi
    if [ $? -ne 0 ]; then
        echo "Single install check failed"
        scp_remote_service
        return 1
    fi
    scp_remote_service
    echo "End check single install"
}

function check_multiple_install() {
    echo "============ Start check multiple install ============"
    python3 $SCRIPT_CMD install -a $arch -pr $pr -tb $tbranch --multiple
    if [ $? -ne 0 ]; then
        echo "Multiple install check failed"
        scp_remote_service
    fi
    echo "End check multiple install"
}

function check_multiple_build() {
    echo "============ Start check multiple build ============"
    python3 $SCRIPT_CMD build -pr $pr -tb $tbranch -a $arch --multiple
    if [ $? -ne 0 ]; then
        echo "Multi package build failed"
        scp_remote_service
        exit 1
    fi
    echo "Multi package build succeeded"
}

function check_license() {
    echo "============ Start check license ============"
    if [[ -n "$variant" ]]; then
        python3 $SCRIPT_CMD license -pr $pr -a $arch --variant $variant
    else
        python3 $SCRIPT_CMD license -pr $pr -a $arch
    fi
    if [ $? -ne 0 ]; then
        echo "Check package license failed"
        scp_remote_service
        return 1
    fi
    scp_remote_service
    echo "End check license"
}

function compare_difference() {
    echo "============ Start comparing package differences ============"
    # oecp文件调用比对
    oecp_compare
    abi_compare
    echo "Change impact needs to be verified."
}

function abi_compare() {
    { set +x; } 2>/dev/null
    pr_link='https://atomgit.com/'${repo_owner}/${repo}'/pull/'${prid}
    pr_commit_json_file="${WORKSPACE}/pr_commit_json_file"
    # comment_file="${repo}_${prid}_${arch}_comment"
    if [[ ${platform} != "github" ]]; then
        curl -H "Authorization: Bearer ${gitcodeTokenRead}" https://api.atomgit.com/api/v5/repos/${repo_owner}/${repo}/pulls/${prid}/files >$pr_commit_json_file
    fi
    compare_result="${repo}_${prid}_${arch}${variant_suffix}_compare_result"
    export PYTHONPATH=${shell_pathoe}
    if [[ ! "$(ls -A $old_dir | grep '.rpm')" || ! "$(ls -A $new_dir | grep '.rpm')" ]]; then
        echo "this is first commit PR"
        python3 ${SCRIPT_PATCH}/extra_work.py comparepackage --ignore -p ${repo} -j $result_dir/report-$old_dir-$new_dir/osv.json -pr $pr_link -pr_commit $pr_commit_json_file -f $WORKSPACE/${compare_result} || echo "continue although run compare package failed"
    else
        python3 ${SCRIPT_PATCH}/extra_work.py comparepackage -p ${repo} -j $result_dir/report-$old_dir-$new_dir/osv.json -pr $pr_link -pr_commit $pr_commit_json_file -f $WORKSPACE/${compare_result} || echo "continue although run compare package failed"
    fi
    # run before save rpm, reset remote dir
    fileserver_user_path="/repo/openeuler/src-openeuler${repo_server_test_tail}/${tbranch}/${committer}/${repo}/${arch}${variant_suffix}/${prid}"
    fileserver_tmpfile_path="/repo/soe${repo_server_test_tail}/check_item"
    remote_dir_reset_cmd=$(
        cat <<EOF
if [[ ! -d "$fileserver_user_path" ]]; then
	mkdir -p $fileserver_user_path
fi
if [[ \$(ls -A "$fileserver_user_path" | grep ".rpm") ]]; then
	rm $fileserver_user_path/*.rpm
fi
if [[ \$(ls -A "$fileserver_user_path" | grep ".json") ]]; then
	rm $fileserver_user_path/*.json
fi
if [[ ! -d "$fileserver_tmpfile_path" ]]; then
	mkdir -p $fileserver_tmpfile_path
fi
if [[ -e "$fileserver_tmpfile_path/${compare_result}" ]]; then
	rm  $fileserver_tmpfile_path/${compare_result}
fi
# if [[ -e "$fileserver_tmpfile_path/${comment_file}" ]]; then
# 	rm  $fileserver_tmpfile_path/${comment_file}
# fi
EOF
    )
    ssh -i ${SaveBuildRPM2Repo} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR root@${repo_server} "$remote_dir_reset_cmd"

    if [[ -e $result_dir/report-$old_dir-$new_dir/osv.json && "$(ls -A $old_dir | grep '.rpm')" && "$(ls -A $new_dir | grep '.rpm')" ]]; then
        old_any_rpm=$(ls $old_dir | head -n 1)
        new_any_rpm=$(ls $new_dir | head -n 1)
        # 版本解析容错（rpm 损坏时 rpm -q 非零）：if 条件内命令不受 set -e 影响，
        # Jenkins（有 -e）与 Action（无 -e）行为一致；失败仅告警、跳过归档，不阻断门禁
        if ! old_version=$(rpm -q $old_dir/$old_any_rpm --queryformat '%{version}\n') \
            || ! old_release=$(rpm -q $old_dir/$old_any_rpm --queryformat '%{release}\n') \
            || ! new_version=$(rpm -q $new_dir/$new_any_rpm --queryformat '%{version}\n') \
            || ! new_release=$(rpm -q $new_dir/$new_any_rpm --queryformat '%{release}\n'); then
            echo "warn: parse rpm version/release failed, rpm file may be corrupted, skip osv.json archive upload"
        else
            old_release=${old_release%%\.oe1}
            new_release=${new_release%%\.oe1}

            new_json_name=${repo}_${old_version}-${old_release}_${new_version}-${new_release}.json
            retry_command "scp -r -i ${SaveBuildRPM2Repo} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR $result_dir/report-$old_dir-$new_dir/osv.json root@${repo_server}:/repo/openeuler/src-openeuler${repo_server_test_tail}/${tbranch}/${committer}/${repo}/${arch}${variant_suffix}/${prid}/$new_json_name"
            if [ -d $result_dir/details_analyse ]; then
                retry_command "scp -r -i ${SaveBuildRPM2Repo} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR $result_dir/details_analyse root@${repo_server}:/repo/openeuler/src-openeuler${repo_server_test_tail}/${tbranch}/${committer}/${repo}/${arch}${variant_suffix}/${prid}/"
            fi
        fi
    fi
    if [[ -d $new_dir && "$(ls -A $new_dir | grep '.rpm')" ]]; then
        retry_command "scp -r -i ${SaveBuildRPM2Repo} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR $new_dir/* root@${repo_server}:/repo/openeuler/src-openeuler${repo_server_test_tail}/${tbranch}/${committer}/${repo}/${arch}${variant_suffix}/${prid}/"
    fi
    if [[ -e $compare_result ]]; then
        retry_command "scp -r -i ${SaveBuildRPM2Repo} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR ${compare_result} root@${repo_server}:$fileserver_tmpfile_path/${compare_result}"
    fi
    if [[ -e $comment_file ]]; then
        retry_command "scp -r -i ${SaveBuildRPM2Repo} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR ${comment_file} root@${repo_server}:$fileserver_tmpfile_path/${comment_file}"
    fi
    echo "save result"

    python3 ${shell_pathoe}/src/utils/oemaker_analyse.py --branch ${tbranch} --arch ${arch} \
	--oecp_json_path "$result_dir/report-$old_dir-$new_dir/osv.json" --owner "${repo_owner}" \
	--repo ${repo} --prid ${prid}
    if [ "${CI_DEBUG:-false}" == "true" ]; then
        set -x
    fi
}

function check_single_build() {
    echo "============ Start check single build ============"
    if [[ -n "$variant" ]]; then
        python3 $SCRIPT_CMD build -pr $pr -tb $tbranch -a $arch --variant $variant
    else
        python3 $SCRIPT_CMD build -pr $pr -tb $tbranch -a $arch
    fi
    if [ $? -ne 0 ]; then
        echo "Single package build failed"
        scp_remote_service
        return 1
    fi
    scp_remote_service
    echo "Single package build successfully"
}

function clean_env() {
    echo "========== Start clean env =========="
    if [[ -d "$WORKSPACE/rpms" ]]; then
        echo "rm -rf $WORKSPACE/rpms"
        rm -rf $WORKSPACE/rpms
    fi
    if [[ -d "$WORKSPACE/records-course" ]]; then
        echo "rm -rf $WORKSPACE/records-course"
        rm -rf $WORKSPACE/records-course
    fi
    if [[ -d "$WORKSPACE/install-logs" ]]; then
        echo "rm -rf $WORKSPACE/install-logs"
        rm -rf $WORKSPACE/install-logs
    fi
    if [[ -d "$WORKSPACE/pull-fetch" ]]; then
        echo "rm -rf $WORKSPACE/pull-fetch"
        rm -rf $WORKSPACE/pull-fetch
    fi
    if [[ -d "$WORKSPACE/lkp" ]]; then
        echo "rm -rf $WORKSPACE/lkp"
        rm -rf $WORKSPACE/lkp
    fi
    cat >${WORKSPACE}/ci-tools.repo <<EOF
EOF
    echo "========== Env clean up =========="
}

function oecp_compare() {
    { set +x; } 2>/dev/null
    echo "========== Start oecp compare =========="
    old_dir="${WORKSPACE}/old_rpms/"
    new_dir="${WORKSPACE}/new_rpms/"
    result_dir="${WORKSPACE}/oecp_result"
    ci_server_dir="/repo/openeuler/src-openeuler${repo_server_test_tail}/${tbranch}/0X080480000XC0000000/${repo}/${arch}${variant_suffix}/"

    if [[ -d $old_dir ]]; then
        echo "rm -rf $old_dir"
        rm -rf $old_dir
    fi
    if [[ -d $new_dir ]]; then
        echo "rm -rf $new_dir"
        rm -rf $new_dir
    fi
    if [[ -d $result_dir ]]; then
        echo "rm -rf $result_dir"
        rm -rf $result_dir
    fi
    mkdir -p $old_dir
    mkdir -p $new_dir
    mkdir -p $result_dir

    if [[ -d ${WORKSPACE}/rpms && "$(ls -A ${WORKSPACE}/rpms)" ]]; then
        cp ${WORKSPACE}/rpms/*.rpm $new_dir
    fi

    echo "try download rpms from ci server"
    scp -r -i ${SaveBuildRPM2Repo} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@${repo_server}:$ci_server_dir/*.rpm $old_dir || echo log_info "file ${ci_server_dir} not exist"

    if [[ ! "$(ls -A $old_dir | grep '.rpm')" && "$(ls -A $new_dir | grep '.rpm')" ]]; then
        python3 $SCRIPT_CMD download -p $repo -a $arch
        if [[ -d $old_dir/binaries && "$(ls -A $old_dir/binaries | grep '\.rpm$')" ]]; then
            cp $old_dir/binaries/*.rpm $old_dir
            sudo rm -rf $old_dir/binaries
        fi
    fi

    if [[ "$(ls -A $new_dir | grep '.rpm')" && "$(ls -A $old_dir | grep '.rpm')" ]]; then
        config_oecp_db
        python3 ${JENKINS_HOME}/oecp/cli.py $old_dir $new_dir -o $result_dir -w $result_dir -n 2 -s $tbranch-${arch} --spec $BUILD_ROOT/home/abuild/rpmbuild/SOURCES --db-password ${MysqlUserPasswd#*:} --pull-request-id ${repo}-${prid} || echo "continue although run oecp failed"
        cat $result_dir/report-$old_dir-$new_dir/osv.json
    fi
    echo "End oecp compare"
    if [ "${CI_DEBUG:-false}" == "true" ]; then
        set -x
    fi
}

function config_ebs() {
    # OAuth 账号/密码通过环境变量进入子进程，不出现在 sed 等命令的 argv 中
    { set +x; } 2>/dev/null
    echo "Start config ebs env"
    if [ ! -d ~/.config/cli/defaults ]; then
        mkdir -p ~/.config/cli/defaults
    fi
    local ebs_config="$HOME/.config/cli/defaults/config.yaml"
    cp ${shell_path}/ci_guard/conf/ebs_config.yaml "${ebs_config}"
    export OauthAccount OauthPassword
    python3 - "${ebs_config}" <<'PY'
import os
import sys

path = sys.argv[1]
replacements = {
    "__OAUTH_ACCOUNT__": os.environ.get("OauthAccount", ""),
    "__OAUTH_PASSWORD__": os.environ.get("OauthPassword", ""),
}
with open(path, encoding="utf-8") as config_file:
    content = config_file.read()
for placeholder, value in replacements.items():
    content = content.replace(placeholder, value)
with open(path, "w", encoding="utf-8") as config_file:
    config_file.write(content)
PY
    chmod 600 "${ebs_config}"
    source /etc/profile
    source $HOME/.${SHELL##*/}rc
    echo "The ebs configuration is complete."
    # 仅回显配置生效的行数校验（不 cat 全文，防 OAuth 凭据进 CI 日志）
    echo "ebs config entries: $(grep -c '.' ${ebs_config})"
    if [ "${CI_DEBUG:-false}" == "true" ]; then
        set -x
    fi
}

function update_ccb() {
    echo "============ Start update ccb ============"
    ccb_test="/home/jenkins/ccb1"
    rm -rf ${ccb_test}
    mkdir -p ${ccb_test}
    git clone --depth=1 https://atomgit.com/openeuler-customization/lkp-tests.git ${ccb_test}
    rm -rf /home/jenkins/lkp-tests/sbin
    cp -a ${ccb_test}/sbin /home/jenkins/lkp-tests/
    echo "End update ccb"
}

# 检测 repo_server 连通性。
function check_repo_server_connect() {
    echo "Check connectivity to repo_server ${repo_server} via ssh..."
    ssh -i ${SaveBuildRPM2Repo} \
        -o ConnectTimeout=5 -o ConnectionAttempts=1 \
        -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR \
        -o BatchMode=yes root@${repo_server} "echo ok"
}
function retry_command() {
    local command=$1
    local max_time=3
    local wait_time=10
    local attempt=0
    # 对 repo_server 的 scp/ssh 操作先做连通性探测（见 check_repo_server_connect），
    # 探测失败直接返回不执行命令，避免重试空耗超时时间
    if [[ "$command" == *"root@${repo_server}"* ]] && ! check_repo_server_connect; then
        echo "repo_server ${repo_server} probe failed, skip command"
        return 1
    fi
    while [[ $attempt -lt max_time ]]; do
        if eval $command; then
            echo "command executed successful"
            break
        else
            attempt=$((attempt + 1))
            echo "command failed, retrying $attempt times"
            sleep $wait_time
        fi
    done
}

function print_job() {
    { set +x; } 2>/dev/null
    # Action 链路（workflow 注入 ACTION_PIPELINE_URL/ACTION_RUN_NUMBER）跳过：
    # 其日志为 workflow run 链接，且由 build-comment 汇总评论统一回显，
    # 此处逐架构发评论只会产生重复内容并拼出 Jenkins 假链接
    if [[ -n "${ACTION_PIPELINE_URL:-}${ACTION_RUN_NUMBER:-}" ]]; then
        echo "Action 环境，跳过 print_job（日志链接由 build-comment 汇总评论提供）"
        if [ "${CI_DEBUG:-false}" == "true" ]; then
            set -x
        fi
        return 0
    fi
    if [[ -n "$variant" ]]; then
        arch_display="${arch}(${variant})"
    else
        arch_display="${arch}"
    fi
    job_name=`echo $JOB_NAME|sed -e 's#/job/#/#g'`
    job_path="https://log-ci.openeuler.openatom.cn/job/${job_name}/$BUILD_ID/"
    body_str="${arch_display}架构构建及构建后检查：<a href=${job_path}>${job_name}/${BUILD_ID}</a>"
    curl -X POST --header 'Content-Type: application/json;charset=UTF-8' -H "Authorization: Bearer ${gitcodeTokenWrite}" 'https://api.atomgit.com/api/v5/repos/'${repo_owner}'/'${repo}'/pulls/'${prid}'/comments' -d '{"body":"'"${body_str}"'"}' || echo "comment source pr failed"
    if [ "${CI_DEBUG:-false}" == "true" ]; then
        set -x
    fi
}

# 从文件服务器拉取 trigger 阶段上传的 per-spec support_arch 与 spec_list。
# Jenkins 链路使用；Action 链路改由 build_entry.sh 的 _restore_ac_spec_files 从 AC 制品还原。
# 文件不可达时 fail-soft，交由 main 的保守全架构构建兜底，不阻断门禁。
function fetch_support_arch_from_server() {
    local support_arch_prefix=${repo}_${prid}_support_arch_

    # 下载所有 per-spec support_arch 文件（供构建决策与 build.py 结果修正阶段读取）
    retry_command "scp -r -i ${SaveBuildRPM2Repo} -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null \
        root@${repo_server}:/repo/soe${repo_server_test_tail}/support_arch/${support_arch_prefix}* ." 2>/dev/null || true
    # 去掉 {repo}_{prid}_ 前缀，还原为 support_arch_{spec_name}（构建决策按 spec 名精确匹配）
    for f in ${support_arch_prefix}*; do
        if [[ -e "$f" ]]; then
            mv "$f" "support_arch_${f#${support_arch_prefix}}"
        fi
    done

    # 下载 spec_list 清单（trigger 阶段生成，PR 修改的全部 spec 名）
    local spec_list_remote=${repo}_${prid}_spec_list
    retry_command "scp -r -i ${SaveBuildRPM2Repo} -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null \
        root@${repo_server}:/repo/soe${repo_server_test_tail}/support_arch/${spec_list_remote} ." 2>/dev/null || true
    if [[ -e "$spec_list_remote" ]]; then
        mv "$spec_list_remote" "spec_list"
    fi
}

function main() {
    trap clean_secrets EXIT
    require_code_tokens
    # spec_list/support_arch 来源分两条链路：
    # - Jenkins：无平台制品，从文件服务器拉取 trigger 阶段上传的文件
    # - Action：AC 制品已由 build_entry.sh 的 _restore_ac_spec_files 还原到本目录
    # Action 环境（workflow 注入 ACTION_PIPELINE_URL/ACTION_RUN_NUMBER，判定同 print_job）
    # 跳过下载，避免重复拉取/覆盖制品还原的结果。
    if [[ -z "${ACTION_PIPELINE_URL:-}${ACTION_RUN_NUMBER:-}" ]]; then
        fetch_support_arch_from_server
    else
        echo "Action 环境，spec_list/support_arch 由 AC 制品还原，跳过文件服务器下载"
    fi

    # 构建决策：
    # - 无 spec_list（旧 trigger 数据）→ 保守构建，不跳过
    # - 有 spec_list：任一 spec 无 support_arch_{spec} 文件 → 该 spec 架构不受限 → 全架构构建
    # - 所有 spec 均有 support_arch 文件 → 取支持架构并集；当前架构不在并集 → 跳过构建
    need_build=true
    if [[ -f spec_list ]]; then
        all_restricted=true
        support_union=""
        for spec in $(cat spec_list); do
            if [[ ! -f "support_arch_${spec}" ]]; then
                all_restricted=false
                break
            fi
            support_union="${support_union} $(cat support_arch_${spec})"
        done
        if $all_restricted; then
            base_arch="${arch%_64k}"
            if ! echo "$support_union" | tr ' ' '\n' | grep -qx "$base_arch"; then
                echo "arch ${arch} not in supported arch union (${support_union}), skip build"
                need_build=false
            fi
        fi
    fi

    if ! $need_build; then
        echo "============ 本架构因 ExclusiveArch 限制跳过构建 ============"
        return 0
    fi

    repo_owner_judge
    remote_dir_make
    clean_env
    update_config
    config_ebs
    update_ccb

    # 构建入口评论：Jenkins 环境下链接日志服务器，便于构建期间先给出日志入口；
    # Action 环境在函数内判定跳过（见 print_job）
    print_job

    # build 失败即无 rpm 产物，跳过 install/license/oecp（保持短路）；
    # build 成功才依次跑 install/license，并各自失败累计进最终结果overall_rc；
    # oecp结果不纳入统计。
    overall_rc=0
    build_rc=0
    check_single_build || build_rc=$?
    if [ $build_rc -ne 0 ]; then
        overall_rc=1
    else
        install_rc=0
        check_single_install || install_rc=$?
        [ $install_rc -ne 0 ] && overall_rc=1

        license_rc=0
        check_license || license_rc=$?
        [ $license_rc -ne 0 ] && overall_rc=1

        compare_difference
    fi

    scp_remote_service
    return ${overall_rc}
}
