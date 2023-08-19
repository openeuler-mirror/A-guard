#!/bin/bash
COMMAND=$1
JENKINS_HOME=/home/jenkins
SCRIPT_CMD=${shell_path}/ci_guard/ci.py


function update_config(){
    echo "============ Start synchronizing jenkin environment variables ============"
    sed -i "/^gitee_token: */cgitee_token: ${GiteeToken}" ${shell_path}/ci_guard/conf/config.yaml
    sed -i "/^workspace: */cworkspace: ${WORKSPACE}" ${shell_path}/ci_guard/conf/config.yaml
    sed -i "/^branch: */cbranch: ${tbranch}" ${shell_path}/ci_guard/conf/config.yaml
    sed -i "/^pr: */cpr: ${giteePullRequestIid}" ${shell_path}/ci_guard/conf/config.yaml
    sed -i "/^repo: */crepo: ${giteeRepoName}" ${shell_path}/ci_guard/conf/config.yaml
    sed -i "/^ebs_server: */cebs_server: ${ebs_server}" ${shell_path}/ci_guard/conf/config.yaml
    sed -i "/^warehouse_owner: */cwarehouse_owner: ${giteeTargetNamespace}" ${shell_path}/ci_guard/conf/config.yaml
    echo "End of synchronous config"
}

function clean_env(){
    echo "========== Start clean env =========="
    if [[ -d "$WORKSPACE/hotpatch_meta" ]]; then
        echo "rm -rf $WORKSPACE/hotpatch_meta"
        rm -rf $WORKSPACE/hotpatch_meta
    fi
    echo "========== Env clean up =========="
}

function make_hotpatch(){
    echo "============ Start make hotpatch  ============"
    python3 $SCRIPT_CMD hotpatch -xd $WORKSPACE/$x86_debug_name -ad $WORKSPACE/$aarch64_debug_name -t "$issue_title" -d $issue_date -r $repo
    if  [ $? -ne 0 ]; then
        echo "Single package build failed"
        exit 1
    fi
    echo "Single package build successfully"
}

function get_pr_commit(){
    log_info "***********get pr commit**********"
    git clone https://gitee.com/openeuler/hotpatch_meta ${metadata_path}/
    cd ${metadata_path}

    if [[ ${giteePullRequestIid} ]]; then
        git fetch origin pull/$giteePullRequestIid/head:pr_$giteePullRequestIid
        git checkout pr_$giteePullRequestIid
    fi

    hotmetadata_path=`git diff --name-status HEAD~1 HEAD~0 | grep "hotmetadata_" | awk -F ' ' '{print $2}'`

    echo ${hotmetadata_path}

    if [[ !${hotmetadata_path} ]]; then
        echo "this pr not exist patch hotmetadata.xml."
    fi

    hotmetadata_xml=${metadata_path}/${hotmetadata_path}
    echo ${hotmetadata_xml}
    tbranch=`echo $hotmetadata_path | awk -F '/' '{print $1}'`
    cd $WORKSPACE
}

function get_rpm_package(){
    echo "**********get rpm package from relase********"
    echo "get x86_64 debuginfo rpm"
    x86_debug_url=`cat ${hotmetadata_xml} | grep Debug_RPM_X86_64 | sed 's/^.*<Debug_RPM_X86_64>//g' | sed 's/<\/Debug_RPM_X86_64>.*$//g'|awk -F " " 'END {print}'`
    wget -q ${x86_debug_url} || echo "get source rpm failed"
    x86_debug_name=${x86_debug_url##*/}
    echo "get aarch64 debuginfo rpm"
    aarch64_debug_url=`cat ${hotmetadata_xml} | grep Debug_RPM_Aarch64 | sed 's/^.*<Debug_RPM_Aarch64>//g' | sed 's/<\/Debug_RPM_Aarch64>.*$//g'|awk -F " " 'END {print}'`
    wget -q ${aarch64_debug_url} || echo "get aarch64 debuginfo failed"
    aarch64_debug_name=${aarch64_debug_url##*/}
}

function get_hotpatch_issue(){
    echo "**********get hotpatch_issue********"
    echo "get hotpatch_issue_url"
    hotpatch_issue_link=`cat ${hotmetadata_xml} | grep hotpatch_issue_link | sed 's/^.*<hotpatch_issue_link>//g' | sed 's/<\/hotpatch_issue_link>.*$//g'|awk -F " " 'END {print}'`
    echo $hotpatch_issue_link
    issue_number=`echo ${hotpatch_issue_link}|awk -F '/' '{print $7}'`
    log_info "get hotpatch issue body"
    get_body=`curl -X GET --header 'Content-Type: application/json;charset=UTF-8' 'https://gitee.com/api/v5/enterprises/open_euler/issues/'${issue_number}'?access_token='${token}`
    issue_title=`echo ${get_body} |jq -r '.title'`
    issue_date=`echo ${get_body} |jq -r '.created_at'`
}

function make_patch(){
    metadata_path=$WORKSPACE/hotpatch_meta
    # 清理环境
    clean_env
    # 更新配置文件
    update_config
    # 获取pr最新提交内容
    get_pr_commit
    # 获取debuginfo包
    get_rpm_package
    # 获取hotpatch issue_title、issue_date
    get_hotpatch_issue
    # 构建
    make_hotpatch
}

main