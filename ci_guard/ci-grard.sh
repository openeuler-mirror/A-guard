#!/bin/bash
JENKINS_HOME=/home/jenkins
SCRIPT_CMD=${shell_path}/ci_guard/ci.py
pr=https://gitee.com/${repo_owner}/${repo}/pulls/${prid}
repo_comment="${repo}_${prid}_${arch}_comment"
SCRIPT_PATCH=${shell_pathoe}/src/build
fileserver_user_path="/repo/openeuler/src-openeuler/${tbranch}/${committer}/${repo}/${arch}/${prid}/${repo_comment}/$commentid"

function repo_owner_judge(){
    if [[ "${repo_owner}" == "" ]]; then
        repo_owner="src-openeuler"
        repo_server_test_tail=""
    elif [[ "${repo_owner}" != "src-openeuler" && "${repo_owner}" != "openeuler" ]]; then
        repo_server_test_tail="-test"
    fi
fileserver_tmpfile_path="/repo/soe${repo_server_test_tail}/check_item"
}

function remote_dir_make(){
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
EOF
    )
    ssh -i ${SaveBuildRPM2Repo} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR root@${repo_server} "$remote_dir_reset_cmd"
}

function update_config(){
    echo "============ Start synchronizing jenkin environment variables ============"
    sed -i "/^gitee_token: */cgitee_token: ${GiteeToken}" ${shell_path}/ci_guard/conf/config.yaml
    sed -i "/^requires_repo: */crequires_repo: ${buddy}" ${shell_path}/ci_guard/conf/config.yaml
    sed -i "/^build_env_account: */cbuild_env_account: ${OBSUserName}" ${shell_path}/ci_guard/conf/config.yaml
    sed -i "/^build_env_passwd: */cbuild_env_passwd: ${OBSPassword}" ${shell_path}/ci_guard/conf/config.yaml
    sed -i "/^warehouse_owner: */cwarehouse_owner: ${repo_owner}" ${shell_path}/ci_guard/conf/config.yaml
    sed -i "/^build_host: */cbuild_host: ${obs_webui_host}" ${shell_path}/ci_guard/conf/config.yaml
    sed -i "/^files_server: */cfiles_server: ${repo_server}" ${shell_path}/ci_guard/conf/config.yaml
    sed -i "/^workspace: */cworkspace: ${WORKSPACE}" ${shell_path}/ci_guard/conf/config.yaml
    sed -i "/^arch: */carch: ${arch}" ${shell_path}/ci_guard/conf/config.yaml
    sed -i "/^pr: */cpr: ${prid}" ${shell_path}/ci_guard/conf/config.yaml
    sed -i "/^repo: */crepo: ${repo}" ${shell_path}/ci_guard/conf/config.yaml
    sed -i "/^committer: */ccommitter: ${committer}" ${shell_path}/ci_guard/conf/config.yaml
    sed -i "/^db_host: */cdb_host: ${MysqldbHost}" ${shell_path}/ci_guard/conf/config.yaml
    sed -i "/^port: */cport: ${MysqldbPort}" ${shell_path}/ci_guard/conf/config.yaml
    sed -i "/^user_passwd: */cuser_passwd: ${MysqlUserPasswd}" ${shell_path}/ci_guard/conf/config.yaml
    sed -i "/^commentid: */ccommentid: ${commentid}" ${shell_path}/ci_guard/conf/config.yaml
    sed -i "/^branch: */cbranch: ${tbranch}" ${shell_path}/ci_guard/conf/config.yaml
    sed -i "/^build_env: */cbuild_env: ${build_env}" ${shell_path}/ci_guard/conf/config.yaml
    sed -i "/^ebs_server: */cebs_server: ${ebs_server}" ${shell_path}/ci_guard/conf/config.yaml
    echo "End of synchronous config"
}

function config_osc() {
    echo "============ Start config osc ============"
    cat >${JENKINS_HOME}/.oscrc <<EOF
[general]
apiurl = http://117.78.1.88
no_verify = 1
build-root = ${BUILD_ROOT}

[http://117.78.1.88]
user = ${OBSUserName}
pass = ${OBSPassword}
trusted_prj = openEuler:22.03:LTS:LoongArch:selfbuild:BaseOS openEuler:22.03:LTS:selfbuild:BaseOS openEuler:22.03:LTS:Next:selfbuild:BaseOS openEuler:20.03:LTS:SP3:selfbuild:BaseOS openEuler:selfbuild:BaseOS openEuler:20.03:LTS:selfbuild:BaseOS openEuler:selfbuild:function openEuler:20.09:selfbuild:BaseOS openEuler:20.03:LTS:SP1:selfbuild:BaseOS openEuler:21.03:selfbuild:BaseOS openEuler:20.03:LTS:SP2:selfbuild:BaseOS openEuler:21.09:selfbuild:BaseOS openEuler:20.03:LTS:Next:selfbuild:BaseOS # 不用输0,1,2了
EOF
    echo "Successful installed osc"
}

function update_repo(){
    echo "Start updating the repo source files"
    python3 $SCRIPT_CMD initrepo
    if  [ $? -ne 0 ]; then
        echo "Failed to update repo source"
        exit 1
    fi
    cat ${WORKSPACE}/ci-tools.repo
    echo "Update repo source successful"
}

function scp_remote_service(){
    if [ ${build_env} == "obs" ]
    then
        echo "Start obs copy the check result file to the remote file server"
        chmod 755 $WORKSPACE/records-course/${repo}_${arch}_${prid}_buildinfo
        cat $WORKSPACE/records-course/${repo}_${arch}_${prid}_buildinfo
        echo $fileserver_tmpfile_path
        scp -i ${SaveBuildRPM2Repo} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR $WORKSPACE/records-course/${repo}_${arch}_${prid}_buildinfo root@${repo_server}:$fileserver_tmpfile_path
    else
        cat $WORKSPACE/records-course/${repo}_${arch}_${prid}_buildinfo
        echo $fileserver_tmpfile_path
        echo "ebs does not need to copy files to remote"
    fi
}

function check_single_install(){
    echo "============ Start check single install ============"
    python3 $SCRIPT_CMD install -a $arch -pr $pr -tb $tbranch -p $repo
    if  [ $? -ne 0 ]; then
        echo "Single install check failed"
        scp_remote_service
        exit 1
    fi
    # python3 $SCRIPT_CMD comment -pr $pr 
    echo "End check single install"
}

function check_multiple_install(){
    echo "============ Start check multiple install ============"
    python3 $SCRIPT_CMD install -a $arch -pr $pr -tb $tbranch --multiple
    if  [ $? -ne 0 ]; then
        echo "Multiple install check failed"
        scp_remote_service
        exit 1
    fi
    # python3 $SCRIPT_CMD comment -pr $pr 
    echo "End check multiple install"
}

function check_multiple_build(){
    echo "============ Start check multiple build ============"
    python3  $SCRIPT_CMD build -pr $pr -tb $tbranch -a $arch --multiple
    if  [ $? -ne 0 ]; then
        echo "Multi package build failed"
        scp_remote_service
        exit 1
    fi
    # python3 $SCRIPT_CMD comment -pr $pr 
    echo "Multi package build succeeded"
    
}

function compare_difference(){
    echo "============ Start comparing package differences ============"
    # oecp文件调用比对
    oecp_compare
    abi_compare

    python3 $SCRIPT_CMD analysis -df $result_dir/report-$old_dir-$new_dir/osv.json
    if  [ $? -ne 0 ]; then
        echo "No need to verify change impact."
        scp_remote_service
        exit 0
    fi
    # python3 $SCRIPT_CMD comment -pr $pr 
    echo "Change impact needs to be verified."
}

function abi_compare(){
    pr_link='https://gitee.com/${repo_owner}/'${repo}'/pulls/'${prid}
    pr_commit_json_file="${WORKSPACE}/pr_commit_json_file"
    # comment_file="${repo}_${prid}_${arch}_comment"
    curl https://gitee.com/api/v5/repos/${repo_owner}/${repo}/pulls/${prid}/files?access_token=$GiteeToken >$pr_commit_json_file
    compare_result="${repo}_${prid}_${arch}_compare_result"
    export PYTHONPATH=${shell_pathoe}
    if [[ ! "$(ls -A $old_dir | grep '.rpm')" || ! "$(ls -A $new_dir | grep '.rpm')" ]]; then
        echo "this is first commit PR"
        python3 ${SCRIPT_PATCH}/extra_work.py comparepackage --ignore -p ${repo} -j $result_dir/report-$old_dir-$new_dir/osv.json -pr $pr_link -pr_commit $pr_commit_json_file -f $WORKSPACE/${compare_result} || echo "continue although run compare package failed"
    else
        python3 ${SCRIPT_PATCH}/extra_work.py comparepackage -p ${repo} -j $result_dir/report-$old_dir-$new_dir/osv.json -pr $pr_link -pr_commit $pr_commit_json_file -f $WORKSPACE/${compare_result} || echo "continue although run compare package failed"
    fi
    # run before save rpm, reset remote dir
    fileserver_user_path="/repo/openeuler/src-openeuler${repo_server_test_tail}/${tbranch}/${committer}/${repo}/${arch}/${prid}"
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

    echo "save result"
    if [[ -e $result_dir/report-$old_dir-$new_dir/osv.json && "$(ls -A $old_dir | grep '.rpm')" && "$(ls -A $new_dir | grep '.rpm')" ]] && [[ ${build_env} == "obs" ]]; then
        old_any_rpm=$(ls $old_dir | head -n 1)
        old_version=$(rpm -q $old_dir/$old_any_rpm --queryformat '%{version}\n')
        old_release=$(rpm -q $old_dir/$old_any_rpm --queryformat '%{release}\n')
        old_release=${old_release%%\.oe1}
        new_any_rpm=$(ls $new_dir | head -n 1)
        new_version=$(rpm -q $new_dir/$new_any_rpm --queryformat '%{version}\n')
        new_release=$(rpm -q $new_dir/$new_any_rpm --queryformat '%{release}\n')
        new_release=${new_release%%\.oe1}

        new_json_name=${repo}_${old_version}-${old_release}_${new_version}-${new_release}.json
        scp -r -i ${SaveBuildRPM2Repo} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR $result_dir/report-$old_dir-$new_dir/osv.json root@${repo_server}:/repo/openeuler/src-openeuler${repo_server_test_tail}/${tbranch}/${committer}/${repo}/${arch}/${prid}/$new_json_name
    fi
    if [[ -d $new_dir && "$(ls -A $new_dir | grep '.rpm')" ]] && [[ ${build_env} == "obs" ]]; then
        scp -r -i ${SaveBuildRPM2Repo} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR $new_dir/* root@${repo_server}:/repo/openeuler/src-openeuler${repo_server_test_tail}/${tbranch}/${committer}/${repo}/${arch}/${prid}/
    fi
    if [[ -e $compare_result ]] && [[ ${build_env} == "obs" ]]; then
        pwd
        cat $compare_result
        echo $compare_result
        scp -r -i ${SaveBuildRPM2Repo} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR ${compare_result} root@${repo_server}:$fileserver_tmpfile_path/${compare_result}
    fi
    # if [[ -e $comment_file ]]; then
    #     scp -r -i ${SaveBuildRPM2Repo} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR ${comment_file} root@${repo_server}:$fileserver_tmpfile_path/${comment_file}
    # fi

    python3 ${shell_pathoe}/src/utils/oemaker_analyse.py --branch ${tbranch} --arch ${arch} \
	--oecp_json_path "$result_dir/report-$old_dir-$new_dir/osv.json" --owner "src-openeuler" \
	--repo ${repo} --gitee_token $GiteeToken --prid ${prid}
}

function check_single_build(){
    echo "============ Start check single build ============"
    
    python3 $SCRIPT_CMD build -pr $pr -tb $tbranch -a $arch
    if  [ $? -ne 0 ]; then
        echo "Single package build failed"
        scp_remote_service
        exit 1
    fi
    # python3 $SCRIPT_CMD comment -pr $pr 
    echo "Single package build successfully"
}

function clean_env(){
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
    cat >${WORKSPACE}/ci-tools.repo <<EOF
EOF
    echo "========== Env clean up =========="
}

function oecp_compare(){
    echo "========== Start to compare package diff =========="
    old_dir="${WORKSPACE}/old_rpms/"
    new_dir="${WORKSPACE}/new_rpms/"
    result_dir="${WORKSPACE}/oecp_result"
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

    if [[ ! "$(ls -A $old_dir | grep '.rpm')" && "$(ls -A $new_dir | grep '.rpm')" ]]; then
        python3 $SCRIPT_CMD download -p $repo -b $tbranch -a $arch
        if [[ -d $old_dir/binaries && "$(ls -A $old_dir/binaries | grep '\.rpm$')" ]]; then
            cp $old_dir/binaries/*.rpm $old_dir
            sudo rm -rf $old_dir/binaries
        fi
    fi

    if [[ "$(ls -A $new_dir | grep '.rpm')" ]]; then
        sed -i "s/dbhost=127.0.0.1/dbhost=${MysqldbHost}/g" ${JENKINS_HOME}/oecp/oecp/conf/oecp.conf
        sed -i "s/dbport=3306/dbport=${MysqldbPort}/g" ${JENKINS_HOME}/oecp/oecp/conf/oecp.conf
        python3 ${JENKINS_HOME}/oecp/cli.py $old_dir $new_dir -o $result_dir -w $result_dir -n 2 -f json -s $tbranch-${arch} -p ${JENKINS_HOME}/oecp/oecp/conf/plan/symbol.json --db-password ${MysqlUserPasswd:5} --pull-request-id ${repo}-${prid} || echo "continue although run oecp failed"
    fi

}

function config_ebs(){
    echo "Start config ebs env"
    if [ ! -d ~/.config/cli/defaults ]; then
        mkdir -p ~/.config/cli/defaults
    fi
    cat >> ~/.config/cli/defaults/config.yaml <<EOF
SRV_HTTP_REPOSITORIES_HOST: 172.16.1.108
SRV_HTTP_REPOSITORIES_PORT: 30012
SRV_HTTP_REPOSITORIES_PROTOCOL: http://
SRV_HTTP_RESULT_HOST: 172.16.1.108
SRV_HTTP_RESULT_PORT: 30012
SRV_HTTP_RESULT_PROTOCOL: http://
GATEWAY_IP: 172.16.1.108
GATEWAY_PORT: 30012
GITEE_ID:
GITEE_PASSWORD: 
EOF

    echo "The ebs configuration is complete."
}

function make_ebs_env(){
    echo "Start clone lkp-tests"
    sudo dnf install rubygems ruby hostname ruby-devel gcc-c++ -y
    gem sources --add https://repo.huaweicloud.com/repository/rubygems/ --remove https://rubygems.org/
    
    gem install -f git activesupport rest-client faye-websocket md5sum base64
    git clone https://$GiteeUserName:$GiteePassword@gitee.com/openeuler-customization/lkp-tests.git $WORKSPACE/lkp
    cd $WORKSPACE/lkp
    make install || echo "make install failed."
    source /etc/profile
    source $HOME/.${SHELL##*/}rc
    echo "Lkp-test tools are ready."
    config_ebs
    cd $WORKSPACE
    ccb create projects test-ci-boot
}

function main(){
    repo_owner_judge
    remote_dir_make
    clean_env
    update_config
    if [ $build_env == 'ebs' ] ; then
        make_ebs_env
    else
        config_osc
        update_repo
    fi
    check_single_build
    check_single_install
    compare_difference
    check_multiple_build
    check_multiple_install
    scp_remote_service
}

function link_pull(){
    echo "Start link pr"
    update_config
    update_repo
    tpr=${comment///pull-link/""}
    python3 $SCRIPT_CMD link --behavior link -pr $pr -tpr $tpr
}

function merge(){
    echo "Start merge PR: $pr"
    update_config
    update_repo
    python3 $SCRIPT_CMD link --behavior sync -pr $pr
}

function forced_merge(){
    echo "Start forced merge PR: $pr"
    update_config
    update_repo
    python3 $SCRIPT_CMD link --behavior forced -pr $pr
}
