#!/usr/bin/bash
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

COMMAND=$1
INSTALL_LOG_DIR=${WORKSPACE}/install-logs
FILESERVER_PATH="/repo/openeuler/src-openeuler/${tbranch}/${committer}/${repo}/${arch}/${prid}/${repo}_${prid}_${arch}_comment/$commentid"

function update_repo() {
    project=$1
    host=$2
    repository=$3
    host_addr=$(echo $project | sed 's|:|:/|g')
    cat >>${WORKSPACE}/ci-tools.repo <<EOF
[$project]
name=$project
baseurl=$host/$host_addr/$repository/
enabled=1
gpgcheck=0

EOF
}

function install_log_dir(){
    if [ ! -d $INSTALL_LOG_DIR ]; then
        mkdir -p $INSTALL_LOG_DIR
        chmod -R 755 $INSTALL_LOG_DIR
    fi
}

function install_rpms() {
    install_log_dir
    install_root=${WORKSPACE}/install-root/${commentid}
    if [[ ! -d "$install_root" ]]; then
        mkdir -p $install_root
        chmod -R 755 $install_root
    fi
    sudo rm -rf $install_root/*
    echo "=======================Install Check====================="
    # 安装归档的rpm
    if [ ! -d $2 ]; then
        echo "Start installing the archive RPM package."
        for ((i = 2; i <= $#; i++)); do
            eval rpm=\$$i
            echo "Start installing the archive package $rpm."
            start=$(date "+%Y%m%d%H%M%S")
            sudo dnf install -y --setopt=reposdir=${WORKSPACE} --installroot=$install_root $rpm 2>&1 | tee -a $INSTALL_LOG_DIR/$rpm.log
            if [ $? -ne 0 ] || [ -n "$(grep -E 'Error|nothing|provides|nothing provides' $INSTALL_LOG_DIR/$rpm.log)" ]; then
                echo "Failed installing the archive package $rpm."
                echo $rpm":"$start":"$(date "+%Y%m%d%H%M%S")":""failed" >>$INSTALL_LOG_DIR/installed
            else
                echo "$rpm installed successfully."
                echo $rpm":"$start":"$(date "+%Y%m%d%H%M%S")":""success" >>$INSTALL_LOG_DIR/installed
            fi
        done
    else
        cd $2
        for rpm in $(ls *.rpm); do
            echo "Start local install $rpm."
            right_rpm=$(echo ${rpm%-*-*})
            start=$(date "+%Y%m%d%H%M%S")
            sudo dnf localinstall -y --setopt=reposdir=${WORKSPACE} --installroot=$install_root $rpm 2>&1 | tee -a $INSTALL_LOG_DIR/$right_rpm.log
            if [ $? -ne 0 ] || [ -n "$(grep -E 'Error|nothing|provides|nothing provides' $INSTALL_LOG_DIR/$right_rpm.log)" ]; then  
                echo "Failed local installing $right_rpm."
                echo $right_rpm":"$start":"$(date "+%Y%m%d%H%M%S")":""failed" >>$INSTALL_LOG_DIR/installed
            else
                echo "The $right_rpm is successfully installed on the local."
                echo $right_rpm":"$start":"$(date "+%Y%m%d%H%M%S")":""success" >>$INSTALL_LOG_DIR/installed
            fi
        done
    fi

    if [ ${build_env} == "obs" ]; then
        scp_install_log_to_server
    fi
}

function scp_install_log_to_server() {
    echo "The installation logs are copied to the remote server."
    sudo chmod -R 755 $INSTALL_LOG_DIR/*.log
    for log in $(ls $INSTALL_LOG_DIR/*.log); do
        echo "==== Scp log file: $log ===="
        scp -i ${SaveBuildRPM2Repo} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR $log root@${repo_server}:$FILESERVER_PATH || echo "scp failed"
        sudo rm -rf $log
    done
    echo "============= End scp install logs ============="

}

function isolation_verify() {
    install_isolation_verify=${WORKSPACE}/isolation-verify/install-root/${commentid}
    if [[ ! -d "$install_isolation_verify" ]]; then
        mkdir -p $install_isolation_verify
    fi
    sudo rm -rf $install_isolation_verify/*
    # 安装归档的rpm
    if [ ! -d $2 ]; then
        echo "Start isolation verify installing the archive RPM package."
        rpm=$2
        sudo dnf install -y $rpm --setopt=reposdir=${WORKSPACE} --installroot=$install_isolation_verify
        if [ $? -ne 0 ]; then
            echo "Failed installing the archive package $rpm."
            exit 1
        else
            echo "$rpm installed successfully."
            exit 0
        fi
    fi
    # 存在关联关系的包的安装
    cd $2
    sudo dnf localinstall -y $3"*.rpm" --installroot=$install_isolation_verify
    if [ $? -ne 0 ]; then
        echo "Failed local isolation verify installing $3."
        exit 1
    else
        echo "The $3 is successfully isolation verify installed on the local."
        exit 0
    fi
}

function download_binarys() {
    echo "Start download binarys ========="
    install_log_dir
    project=$1
    package=$2
    repository=$3
    arch=$4
    osc getbinaries $project $package $repository $arch
    if [ $? -ne 0 ]; then
        echo "Failed to download the RPM package generated by $package project $project repository $repository arch $arch."
        exit 1
    fi
    if [[ -d binaries && "$(ls -A binaries | grep '\.rpm$')" ]]; then
        for rpm in $(ls -A binaries | grep '\.rpm$'); do
            right_rpm=$(echo ${rpm%-*-*})
            echo $package":"$right_rpm >>$INSTALL_LOG_DIR/repo-rpm-map
        done
        cp binaries/*.rpm .
        sudo rm -rf ./binaries
    fi
    echo "The RPM package generated by the $project is successfully downloaded."
}

function ccb_download_binarys() {
    echo "Start download binarys"
    install_log_dir
    project=$1
    package=$2
    arch=$3

    download_result=`ccb download os_project=$project packages=$package architecture=$arch -b all`

    if [[ $? -ne 0 || -n $(echo $download_result | grep "Not found") ]]; then
        echo "Failed to download the RPM package generated by $package project $project arch $arch."
        exit 1
    fi
    binary_folder=$project-$arch-$package

    if [[ -d $binary_folder && "$(ls -A $binary_folder | grep '\.rpm$')" ]]; then
        for rpm in $(ls -A $binary_folder | grep '\.rpm$'); do
            right_rpm=$(echo ${rpm%-*-*})
            echo $package":"$right_rpm >>$INSTALL_LOG_DIR/repo-rpm-map
        done
        cp $binary_folder/*.rpm .
        sudo rm -rf ./$binary_folder
    fi
    echo "The RPM package generated by the $project is successfully downloaded."
}

case $COMMAND in
update_repo)
    update_repo $2 $3 $4
    ;;
install_rpms)
    install_rpms $*
    ;;
download_binarys)
    download_binarys $2 $3 $4 $5
    ;;
ccb_download_binarys)
    ccb_download_binarys $2 $3 $4
    ;;
isolation_verify)
    isolation_verify $2 $3
    ;;
*)
    echo 'Command Error'
    ;;
esac