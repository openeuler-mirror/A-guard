#!/bin/bash
COMMAND=$1
JENKINS_HOME=/home/jenkins
SCRIPT_CMD=${shell_path}/ci_guard/ci.py
EBS_SERVER="https://eulermaker.compass-ci.openeuler.openatom.cn/"


function update_config(){
    echo "============ Start synchronizing jenkin environment variables ============"
    sed -i "/^gitee_token: */cgitee_token: ${GiteeToken}" ${shell_path}/ci_guard/conf/config.yaml
    sed -i "/^workspace: */cworkspace: ${WORKSPACE}" ${shell_path}/ci_guard/conf/config.yaml
    sed -i "/^branch: */cbranch: ${tbranch}" ${shell_path}/ci_guard/conf/config.yaml
    sed -i "/^pr: */cpr: ${giteePullRequestIid}" ${shell_path}/ci_guard/conf/config.yaml
    sed -i "/^repo: */crepo: ${giteeRepoName}" ${shell_path}/ci_guard/conf/config.yaml
    sed -i "/^ebs_server: */cebs_server: ${EBS_SERVER}" ${shell_path}/ci_guard/conf/config.yaml
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

function config_ebs(){
    echo "Start config ebs env"
    if [ ! -d ~/.config/cli/defaults ]; then
        mkdir -p ~/.config/cli/defaults
    fi
    cat >> ~/.config/cli/defaults/config.yaml <<EOF
SRV_HTTP_REPOSITORIES_HOST: 172.16.1.108
SRV_HTTP_REPOSITORIES_PORT: 30108
SRV_HTTP_REPOSITORIES_PROTOCOL: http://
SRV_HTTP_RESULT_HOST: 172.16.1.108
SRV_HTTP_RESULT_PORT: 30108
SRV_HTTP_RESULT_PROTOCOL: http://
GATEWAY_IP: 172.16.1.108
GATEWAY_PORT: 30108
ACCOUNT: ${OauthAccount}
PASSWORD: ${OauthPassword}
OAUTH_TOKEN_URL: https://omapi.osinfra.cn/oneid/oidc/token
OAUTH_REDIRECT_URL: http://eulermaker.compass-ci.openeuler.openatom.cn/oauth/
PUBLIC_KEY_URL: https://omapi.osinfra.cn/oneid/public/key?community=openeuler

EOF
    source /etc/profile
    source $HOME/.${SHELL##*/}rc
    echo "The ebs configuration is complete."
    cat ~/.config/cli/defaults/config.yaml
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
    echo "***********get pr commit**********"
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
    repo=`echo $hotmetadata_path | awk -F '/' '{print $2}'`
    cd $WORKSPACE
}

function check_whether_multiple_packages(){
    echo "**********check whether multiple packages********"
    patch_list=`git diff --name-status HEAD~1 HEAD~0 | grep "\.patch" |awk -F ' ' '{print $2}'`

    echo ${hotmetadata_path}
    echo ${patch_list}

    # 如果多个hotmetadata.xml有变更，报错不支持多软件包同时制作热补丁；
    if [[ ! ${hotmetadata_path} ]]; then
        repo_path_metadata=""
        echo "this pr not exist patch hotmetadata.xml."
    else
        if [[ ${#hotmetadata_path[@]} -gt 2 ]]; then
            comment_error_src_pr "不支持多个包同时制作热补丁"
        else
            hotmetadata_path=${hotmetadata_path}
            echo "only have one hotmetadata.xml."
            repo_path_metadata=${hotmetadata_path%/*}
            echo $repo_path_metadata
        fi
    fi

    # 如果有多个patch包，需要都是同一包同一版本的patch包，否则报错不支持多软件包同时制作热补丁
    if [[ ! ${patch_list} ]]; then
        repo_path_patch=""
        patch_list="null"
        echo "this pr not exist patch file."
    else
        patch_list=(${patch_list})
        if [[ ${#patch_list[@]} -gt 2 ]]; then
            repo_path_patch=${patch_list[0]%/*}
            echo $repo_path_patch
            for patch in ${patch_list[@]:1}
            do
                repo_path_tmp=${patch%/*}
                echo $repo_path_tmp
                if [[ $repo_path_patch != $repo_path_tmp ]]; then
                    comment_error_src_pr "有多个补丁文件并且路径不同"
                fi
            done
        else
            echo "only have one patch."
            repo_path_patch=${patch_list%/*}
        fi
    fi

    # patch包需要和hotmetadata.xml包版本保持一致，否则认为是多个软件包同时制作热补丁
    if [[ $repo_path_metadata && $repo_path_patch ]]; then
        if [[ $repo_path_patch != $repo_path_metadata/patch ]]; then
            comment_error_src_pr "补丁文件和元数据文件路径不同"
        fi
    fi

    if [[ $repo_path_metadata ]]; then
        repo_path=$repo_path_metadata
    elif [[ $repo_path_patch ]]; then
        repo_path=$repo_path_patch
    else
        comment_error_src_pr "元数据文件和补丁文件没有变动，制作热补丁流程结束"
        exit 1
    fi

    comment_branch=`echo $repo_path | awk -F '/' '{print $1}'`
    repo=`echo $repo_path | awk -F '/' '{print $2}'`
    repo_version=`echo $repo_path | awk -F '/' '{print $3}'`

    echo ${comment_branch}
    echo ${repo}

    if [[ `echo ${hotmetadata_path} | grep "ACC"` ]]; then
        mode="ACC"
    elif [[  `echo ${hotmetadata_path} | grep "SGL"` ]];then
        mode="SGL"
    else
        comment_error_src_pr "元数据文件名包含不支持的补丁演进方式，目前支持的演进方式为ACC/SGL"
    fi

    hotmetadata_xml=${metadata_path}/${hotmetadata_path}
    repo_path=${metadata_path}/${repo_path}

    echo ${hotmetadata_xml}
    echo ${repo_path}
}


function get_rpm_package(){
    echo "**********get rpm package from relase********"
    echo "get x86_64 debuginfo rpm"
    x86_debug_url=`cat ${hotmetadata_xml} | grep Debug_RPM_X86_64 | sed 's/^.*<Debug_RPM_X86_64>//g' | sed 's/<\/Debug_RPM_X86_64>.*$//g'|awk -F " " 'END {print}' | sed -e 's#repo.openeuler.org#repo.openeuler.openatom.cn#'`
    wget -q ${x86_debug_url} || echo "get source rpm failed"
    x86_debug_name=${x86_debug_url##*/}
    echo "get aarch64 debuginfo rpm"
    aarch64_debug_url=`cat ${hotmetadata_xml} | grep Debug_RPM_Aarch64 | sed 's/^.*<Debug_RPM_Aarch64>//g' | sed 's/<\/Debug_RPM_Aarch64>.*$//g'|awk -F " " 'END {print}'  | sed -e 's#repo.openeuler.org#repo.openeuler.openatom.cn#'`
    wget -q ${aarch64_debug_url} || echo "get aarch64 debuginfo failed"
    aarch64_debug_name=${aarch64_debug_url##*/}
}

function get_hotpatch_issue(){
    issue_title=`cat ${update_info_file} | grep issue_title: | sed 's/^.*issue_title: //g'`
    issue_date=`cat ${update_info_file} | grep issued-date: | sed 's/^.*issued-date: //g'`
}

function download_hotpatch_rpm(){
    echo "***********download hotpatch from Eulermaker**********"
    project="HotPatch:${giteePullRequestIid}"
    package="hotpatch_meta"
    result=`ccb select projects os_project=${project}`
    emsx=`echo ${result} | jq -r .[]._source.emsx`
    archs=(`echo ${result} | jq -r '.[]._source.build_targets | .[].architecture'`)
    os_variants=(`echo ${result} | jq -r '.[]._source.build_targets | .[].os_variant'`)
    for i in ${!archs[@]}
    do
        arch=${archs[$i]}
        os_variant=${os_variants[$i]}
        url="${ebs_server}/api/${emsx}/repositories/${project}/${os_variant}/${arch}"
        echo "Download the RPM package generated by $package project $project arch $arch."

        mkdir -p ${hotpatch_path}/${ar}/Packages ${hotpatch_path}/${ar}/hotpatch_xml
        wget -r -l1 -nd -A '.xml' $url/hotpatch_xml/ -P ${hotpatch_path}/${ar}/hotpatch_xml/
        wget -r -l1 -nd -A '.rpm' $url/Packages/ -P ${hotpatch_path}/${ar}/Packages/
        if [[ $arch == "x86_64" ]]; then
            mkdir -p ${hotpatch_path}/source/Packages ${hotpatch_path}/source/hotpatch_xml
            mv ${hotpatch_path}/${ar}/Packages/*.src.rpm ${hotpatch_path}/source/Packages
            hotpatch_src_filename=`ls ${hotpatch_path}/source/Packages/*.src.rpm`
            mv ${hotpatch_path}/${ar}/hotpatch_xml/${hotpatch_src_filename%.*}.xml ${hotpatch_path}/source/hotpatch_xml
        fi
    done
}

function create_repo(){
    echo "**********begin create repo**********"
    remote_hotpatch=/repo/openeuler/hotpatch/${branch}
    dailybuild_path="http://121.36.84.172/hotpatch/${branch}"
    arch=(source x86_64 aarch64)
    for ar in ${arch[@]}
    do
        echo "${ar} create repo"
        ssh -i ${update_key} -o StrictHostKeyChecking=no root@${dailybuild_ip} "mkdir -p $remote_hotpatch/${ar}/Packages $remote_hotpatch/${ar}/hotpatch_xml"
        scp -i ${update_key} -o StrictHostKeyChecking=no -r ${hotpatch_path}/${ar}/Packages/* root@${dailybuild_ip}:${remote_hotpatch}/$ar/Packages || echo "copy hotpatch failed"
        scp -i ${update_key} -o StrictHostKeyChecking=no -r ${hotpatch_path}/${ar}/hotpatch_xml/* root@${dailybuild_ip}:${remote_hotpatch}/$ar/hotpatch_xml || echo "copy updateinfo.xml failed"
        ssh -i ${update_key} -o StrictHostKeyChecking=no root@${dailybuild_ip} "cd ${remote_hotpatch}/$ar/Packages && createrepo --update -d ${remote_hotpatch}/$ar"
    done

}

function comment_issue(){
    echo "**********comment hotpatch link to hotpatch issue**********"
    echo "get hotpatch issue body"
    hotpatch_issue_link=`cat ${hotmetadata_xml} | grep hotpatch_issue_link | sed 's/^.*<hotpatch_issue_link>//g' | sed 's/<\/hotpatch_issue_link>.*$//g'|awk -F " " 'END {print}'`
    issue_number=`echo ${hotpatch_issue_link}|awk -F '/' '{print $7}'`

    get_body=`curl -X GET --header 'Content-Type: application/json;charset=UTF-8' 'https://gitee.com/api/v5/enterprises/open_euler/issues/'${issue_number}'?access_token='${token}`
    body=`echo ${get_body} |jq -r '.body'`

    # 删除上次的热补丁路径
    issue_desc=`echo ${body}| sed 's/热补丁路径.*$//g'`
    # 获取问题类型
    ques=`echo ${issue_desc} | sed 's/热补丁元数据.*$//g'`
    # 获取元数据文件路径
    metadata=`echo ${issue_desc#${ques}}`

    hotpatch_str="热补丁路径："
    updateinfo_str="热补丁信息："
    arch=(source x86_64 aarch64)
    for ar in ${arch[@]}
    do
        arch_rpm=`ls ${hotpatch_path}/$ar/Packages/`
        if [[ ${arch_rpm} ]]; then
            patch_arch_rpm="${dailybuild_path}/$ar/Packages/${arch_rpm}"
            hotpatch_str="${hotpatch_str}${patch_arch_rpm}\n"
        fi
        arch_updateinfo=`ls ${hotpatch_path}/$ar/hotpatch_xml/`
        if [[ ${arch_updateinfo} ]]; then
            patch_arch_updateinfo="${dailybuild_path}/$ar/hotpatch_xml/${arch_updateinfo}"
            updateinfo_str="${updateinfo_str}${patch_arch_updateinfo}\n"
        fi
    done

    echo $hotpatch_str
    echo $updateinfo_str

    echo "comment hotpatch issue"
    body="${ques}\n${metadata}\n${hotpatch_str}\n${updateinfo_str}"
    curl -X PATCH --header 'Content-Type: application/json;charset=UTF-8' 'https://gitee.com/api/v5/enterprises/open_euler/issues/'${issue_number} -d '{"access_token":"'"${token}"'","repo":"'"${repo}"'","body":"'"${body}"'"}'

}

function comment_job_info(){
    job_name=`echo $JOB_NAME|sed -e 's#/#/job/#g'`
    job_path="https://openeulerjenkins.osinfra.cn/job/${job_name}/$BUILD_ID/console"
    body_str="热补丁构建入口：<a href=${job_path}>multiarch/src-openeuler/syscare-patch/hotpatch_meta_ebs</a>，当前构建号为 $BUILD_ID"
    curl -X POST --header 'Content-Type: application/json;charset=UTF-8' 'https://gitee.com/api/v5/repos/'${giteeTargetNamespace}'/'${giteeRepoName}'/pulls/'${giteePullRequestIid}'/comments' -d '{"access_token":"'"${token}"'","body":"'"${body_str}"'"}' || echo "comment source pr failed"
}

function check_version_released(){
    release_path=/repo/openeuler/${comment_branch}
    hotpatch_update_src_path=hotpatch_update/source/Packages
    # 判断最近一次版本是否已被发布
    pre_version_release=`cat ${update_info_file} | grep pre_version_release: | sed 's/^.*pre_version_release://g'`
    if [[ $pre_version_release ]]; then
        src_hotpatch_update_name=`ssh -i ${update_key} -o StrictHostKeyChecking=no -o LogLevel=ERROR root@${release_ip} "cd ${release_path}/${hotpatch_update_src_path} && ls | grep ${repo}-${repo_version} | grep ${pre_version_release}"`|| echo ""
        if [[ ! $src_hotpatch_update_name ]]; then
           src_url="https://repo.openeuler.org/${comment_branch}/${hotpatch_update_src_path}/${src_hotpatch_update_name}"
           comment_error_src_pr "上一个热补丁版本：${pre_version_release}未发布，不允许新增热补丁版本"
        fi
    fi
    # 判断本次变更的版本是否已被发布
    modify_list=`cat ${update_info_file} | grep modify_list: | sed 's/^.*modify_list://g'`
    if [[ $modify_list ]]; then
        for ver in ${modify_list[@]}
        do
            src_hotpatch_update_name=`ssh -i ${update_key} -o StrictHostKeyChecking=no -o LogLevel=ERROR root@${release_ip} "cd ${release_path}/${hotpatch_update_src_path} && ls | grep ${repo}-${repo_version} | grep ${ver}"`|| echo ""
            if [[ $src_hotpatch_update_name ]]; then
               src_url="https://repo.openeuler.org/${comment_branch}/${hotpatch_update_src_path}/${src_hotpatch_update_name}"
               comment_error_src_pr "热补丁版本：${ver}已发布，不允许修改。发布路径为：$src_url"
            fi
        done
    fi
}

function comment_error_src_pr(){
    echo "**********comment hotmetadata pr link to pr********"
    body_str="热补丁制作流程已中止，$1 "
    curl -X POST --header 'Content-Type: application/json;charset=UTF-8' 'https://gitee.com/api/v5/repos/'${giteeTargetNamespace}'/'${giteeRepoName}'/pulls/'${giteePullRequestIid}'/comments' -d '{"access_token":"'"${token}"'","body":"'"${body_str}"'"}' || echo "comment pr failed"
    echo "create tag"
    curl -X DELETE --header 'Content-Type: application/json;charset=UTF-8' 'https://gitee.com/api/v5/repos/'${giteeTargetNamespace}'/'${giteeRepoName}'/pulls/'${giteePullRequestIid}'/labels/ci_successful?access_token=0557ff54fd91c4170ecdd523ff1bba47'
    curl -X DELETE --header 'Content-Type: application/json;charset=UTF-8' 'https://gitee.com/api/v5/repos/'${giteeTargetNamespace}'/'${giteeRepoName}'/pulls/'${giteePullRequestIid}'/labels/ci_processing?access_token=0557ff54fd91c4170ecdd523ff1bba47'
    curl -X POST --header 'Content-Type: application/json;charset=UTF-8' 'https://gitee.com/api/v5/repos/'${giteeTargetNamespace}'/'${giteeRepoName}'/pulls/'${giteePullRequestIid}'/labels?access_token=0557ff54fd91c4170ecdd523ff1bba47' -d '"[\"ci_failed\"]"'
    echo $1
    exit
}

function verify_meta() {
    # 打印当前工程链接
    comment_job_info

    # 检查是否一次制作多个包的热补丁
    check_whether_multiple_packages

    # 解析metadata.xml获取信息
    export PYTHONPATH=${shell_path}/ci_guard
    python3 $SCRIPT_CMD verify_meta  -i ${hotmetadata_xml} -o ${update_info_file} -p ${patch_list} -m ${mode}
    cat ${update_info_file}

    # 判断版本是否已被发布
    check_version_released
}

function make_patch(){
    metadata_path=$WORKSPACE/hotpatch_meta/
    update_info_file=${WORKSPACE}/update_info
    # 清理环境
    clean_env
    # 配置lkp客户端
    config_ebs
    # 获取pr最新提交内容
    get_pr_commit
    # 更新配置文件
    update_config
     # 校验元数据字段
    verify_meta

    # 获取debuginfo包
    get_rpm_package
    # 获取hotpatch issue_title、issue_date
    get_hotpatch_issue
    # 构建
    make_hotpatch
}

function approve_hotpatch(){
    metadata_path=${WORKSPACE}/hotpatch_meta
    hotpatch_path=${WORKSPACE}/hotpatch_pr_${giteePullRequestIid}
    sudo yum install -y jq
    # 获取pr最新提交内容
    get_pr_commit
    # 从repo源获取热补丁产物
    download_hotpatch_rpm
    # scp到dailybuild，并创建repo
    create_repo
    # 上报路径至热补丁issue
    comment_issue
    cd ${metadata_path}
    echo "delete remote branch"
    set +e
    # 删除临时分支
    branch_name=${giteeSourceBranch}
    if [[ $giteeSourceNamespace == "openeuler" ]]; then
        if [[ $(git branch -a | grep ${branch_name}) ]]; then
            git push origin --delete ${branch_name}
        fi
    fi
    set -e

}

case $COMMAND in
make_hotpatch)
    make_patch
    ;;
approve_hotpatch)
    approve_hotpatch
    ;;
*)
    echo 'Command Error'
    ;;
esac
