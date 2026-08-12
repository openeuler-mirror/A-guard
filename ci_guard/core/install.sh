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

# 构建变体标识（可选），如 64k
variant=${variant:-""}
if [[ -n "$variant" ]]; then
    variant_suffix="_${variant}"
else
    variant_suffix=""
fi

FILESERVER_PATH="/repo/openeuler/src-openeuler${tail}/${tbranch}/${committer}/${repo}/${arch}${variant_suffix}/${prid}/${repo}_${prid}_${arch}${variant_suffix}_comment/$commentid"

function update_repo() {
    echo "=======================Start updating the repo source files====================="
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
    cat ${WORKSPACE}/ci-tools.repo
    echo "=============Update repo source successful============="
}

function install_log_dir(){
    if [ ! -d $INSTALL_LOG_DIR ]; then
        mkdir -p $INSTALL_LOG_DIR
        chmod -R 755 $INSTALL_LOG_DIR
    fi
}

# 按仓库元数据预建 installroot 顶层布局：
# tsflags=noscripts 禁用了 filesystem 的 %pretrans，而 glibc、固件等包会先把 /lib 建为真实目录，
# 导致 filesystem 解包 cpio 冲突（File from package already exists as a directory）。
# 通过 dnf repoquery 读取 filesystem 包顶层条目类型逐条复刻：
#   符号链接（mode 12xxxx）→ usrmerge 布局，预建 lib/bin/sbin/lib64 -> usr/* 链接
#   目录（mode 40xxx）→ 传统布局，预建真实目录
# openEuler 全系分支均为 usrmerge；元数据检测失败时保守按 usrmerge 处理并输出 WARN
function prepare_install_layout() {
    local root=$1
    local layout
    layout=$(mktemp)
    sudo dnf repoquery --qf '[%{FILEMODES} %{FILENAMES}\n]' filesystem \
        --setopt=reposdir=${WORKSPACE} >"$layout" 2>/dev/null || true
    local detected=0
    for link in lib bin sbin lib64; do
        local mode
        mode=$(awk -v p="/$link" '$2==p {print $1; exit}' "$layout")
        if [[ -z "$mode" ]]; then
            continue
        fi
        detected=1
        if [[ "$mode" == 12* ]]; then
            sudo mkdir -p $root/usr/$link
            sudo ln -sfn usr/$link $root/$link
        else
            sudo mkdir -p $root/$link
        fi
    done
    rm -f "$layout"
    if [[ "$detected" -ne 1 ]]; then
        echo "WARN: failed to detect filesystem layout from repo metadata, assume usrmerge."
        for link in lib bin sbin lib64; do
            sudo mkdir -p $root/usr/$link
            sudo ln -sfn usr/$link $root/$link
        done
    fi
}

function install_rpms() {
    tail=$3
    install_log_dir
    install_root=${WORKSPACE}/install-root/${commentid}
    if [[ ! -d "$install_root" ]]; then
        mkdir -p $install_root
        chmod -R 755 $install_root
    fi
    sudo rm -rf $install_root/*
    echo "=======================Install Check====================="
    prepare_install_layout $install_root
    # 安装归档的rpm
    if [ ! -d $2 ]; then
        echo "Start installing the archive RPM package."
        for ((i = 2; i <= $#; i++)); do
            eval rpm=\$$i
            echo "Start installing the archive package $rpm."
            start=$(date "+%Y%m%d%H%M%S")
            sudo dnf install -y --setopt=tsflags=noscripts --setopt=reposdir=${WORKSPACE} --installroot=$install_root $rpm 2>&1 | tee -a $INSTALL_LOG_DIR/$rpm.log
            if [ $? -eq 0 ] && [ -n "$(grep -E 'Complete!' $INSTALL_LOG_DIR/$rpm.log)" ]; then
                echo "$rpm installed successfully."
                echo $rpm":"$start":"$(date "+%Y%m%d%H%M%S")":""success" >>$INSTALL_LOG_DIR/installed
            else
                echo "Failed installing the archive package $rpm."
                echo $rpm":"$start":"$(date "+%Y%m%d%H%M%S")":""failed" >>$INSTALL_LOG_DIR/installed
            fi
        done
    else
        cd $2
        for rpm in $(ls *.rpm); do
            echo "Start local install $rpm."
            right_rpm=$(echo ${rpm%-*-*})
            start=$(date "+%Y%m%d%H%M%S")
            sudo dnf localinstall -y --setopt=tsflags=noscripts --setopt=reposdir=${WORKSPACE} --installroot=$install_root $WORKSPACE/rpms/$rpm 2>&1 | tee -a $INSTALL_LOG_DIR/$right_rpm.log
            if [ $? -eq 0 ] && [ -n "$(grep -E 'Complete!' $INSTALL_LOG_DIR/$right_rpm.log)" ]; then
                echo "The $right_rpm is successfully installed on the local."
                echo $right_rpm":"$start":"$(date "+%Y%m%d%H%M%S")":""success" >>$INSTALL_LOG_DIR/installed
            else
                echo "Failed local installing $right_rpm."
                echo $right_rpm":"$start":"$(date "+%Y%m%d%H%M%S")":""failed" >>$INSTALL_LOG_DIR/installed
            fi
        done
    fi
    scp_install_log_to_server
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
    prepare_install_layout $install_isolation_verify
    # 安装归档的rpm
    if [ ! -d $2 ]; then
        echo "Start isolation verify installing the archive RPM package."
        rpm=$2
        sudo dnf install -y --setopt=tsflags=noscripts $rpm --setopt=reposdir=${WORKSPACE} --installroot=$install_isolation_verify
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
    sudo dnf localinstall -y --setopt=tsflags=noscripts $3"*.rpm" --installroot=$install_isolation_verify
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
    echo "============Start download binarys============"
    install_log_dir
    project=$1
    package=$2
    arch=$3
    variant=$4
    spec_name=$5

    # If spec_name is provided, use repo:spec format for precise download
    if [[ -n "${spec_name}" ]]; then
        download_package="${package}:${spec_name}"
    else
        download_package="${package}"
    fi

    # 使用重试机制执行ccb download
    MAX_RETRIES=3
    RETRY_WAIT=10
    binary_folder=$project-$arch-$download_package
    download_success=0
    for ((i = 1; i <= MAX_RETRIES; i++)); do
        echo "Attempt $i/$MAX_RETRIES: Downloading $download_package from $project (arch: $arch)"
        
        if [[ -d $binary_folder ]]; then
            echo "Cleaning up previous download folder: $binary_folder"
            sudo rm -rf ./$binary_folder
        fi
        ccb download os_project=$project packages=$download_package architecture=$arch -d -b all
        exit_code=$?
        if [[ $exit_code -eq 0 && -d $binary_folder && "$(ls -A $binary_folder 2>/dev/null | grep '\.rpm$')" ]]; then
            download_success=1
            echo "Download succeeded on attempt $i"
            break
        fi
        if [[ $i -lt $MAX_RETRIES ]]; then
            echo "Download failed on attempt $i, waiting $RETRY_WAIT seconds before retry..."
            sleep $RETRY_WAIT
        fi
    done
    if [[ $download_success -ne 1 ]]; then
        echo "Failed to download the RPM package generated by $download_package project $project arch $arch after $MAX_RETRIES attempts."
        exit 1
    fi
 
    echo "Download the RPM package generated by $download_package project $project arch $arch."
    # For repo-rpm-map, use spec_name as key if provided, otherwise use package
    map_key="${spec_name:-$package}"
    if [[ -d $binary_folder && "$(ls -A $binary_folder | grep '\.rpm$')" ]]; then
        for rpm in $(ls -A $binary_folder | grep '\.rpm$'); do
            right_rpm=$(echo ${rpm%-*-*})
            echo $map_key":"$right_rpm >>$INSTALL_LOG_DIR/repo-rpm-map
        done
        cp $binary_folder/*.rpm .
        ls $binary_folder/
        sudo rm -rf ./$binary_folder
    fi
    echo "<=========================================================>"
    ls -l
    echo "<=========================================================>"
    echo "The RPM package generated by the $project is successfully downloaded."
}

case $COMMAND in
update_repo)
    update_repo "$2" "$3" "$4"
    ;;
install_rpms)
    install_rpms "$@"
    ;;
download_binarys)
    download_binarys "$2" "$3" "$4" "$5"
    ;;
ccb_download_binarys)
    ccb_download_binarys "$2" "$3" "$4" "$5" "$6"
    ;;
isolation_verify)
    isolation_verify "$@"
    ;;
*)
    echo 'Command Error'
    ;;
esac
