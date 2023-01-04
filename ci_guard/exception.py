#!/usr/bin/python3
# ******************************************************************************
# Copyright (c) Huawei Technologies Co., Ltd. 2020-2020. All rights reserved.
# licensed under the Mulan PSL v2.
# You can use this software according to the terms and conditions of the Mulan PSL v2.
# You may obtain a copy of Mulan PSL v2 at:
#     http://license.coscl.org.cn/MulanPSL2
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FIT FOR A PARTICULAR
# PURPOSE.
# See the Mulan PSL v2 for more details.
# ******************************************************************************/


class CiError(Exception):
    """
    CI access control exception base class
    """

    def __init__(self, msg):
        super(CiError, self).__init__(f"{msg}")


class RequestError(CiError):
    """
    Error calling URL
    """

    def __init__(self, msg):
        super(RequestError, self).__init__(f"Error calling URL: {msg}")


class ConfigError(CiError):
    """
    Configuration file content parsing error
    """

    def __init__(self, msg):
        super(ConfigError, self).__init__(
            f"Configuration file content parsing error: {msg}\n Please check the configuration file"
        )


class FileError(CiError):
    """
    file operation error
    """

    def __init__(self, msg):
        super(FileError, self).__init__(f"File operation error: {msg}")


class LinkError(CiError):
    """
    Pull link error
    """

    def __init__(self, msg):
        super(LinkError, self).__init__(f"Link pull error: {msg}")


class ParameterError(CiError):
    """
    Incoming parameter error
    """

    def __init__(self, **kwargs):
        super(ParameterError, self).__init__(
            f"Incoming parameter error: {kwargs}, please check and try again"
        )


class OscError(CiError):
    """
    OSC command execution error
    """

    def __init__(self, msg):
        super(OscError, self).__init__(f"osc command execution error: {msg}")


class ProjectNameError(CiError):
    """
    Project name is error
    """

    def __init__(self, msg):
        super(ProjectNameError, self).__init__(f"Project name is error: {msg}")


class CreateProjectError(CiError):
    """
    create project error
    """

    def __init__(self, msg):
        super(CreateProjectError, self).__init__(f"failed create Project: {msg}")


class DeletePackageError(CiError):
    """
    Software package deletion Exception
    """

    def __init__(self, msg):
        super(DeletePackageError, self).__init__(f"delete Package Error: {msg}")


class BranchPackageError(CiError):
    """
    OBS failed to package branches
    """

    def __init__(self, msg):
        super(BranchPackageError, self).__init__(f"branch Package Error: {msg}")


class ModifyProjectError(CiError):
    """
    Change the obs project configuration error
    """

    def __init__(self, msg):
        super(ModifyProjectError, self).__init__(
            f"failed to modify the meta value of the project: {msg}"
        )
