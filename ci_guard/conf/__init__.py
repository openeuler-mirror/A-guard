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
import os
import yaml
from . import settings


class PreloadingSettings:
    """
    The system default configuration file and the configuration
    file changed by the user are lazily loaded.
    """

    _setting_container = None

    def _preloading(self):
        """
        Load the default configuration in the system and the related configuration
        of the user, and overwrite the default configuration items of the system
        with the user's configuration data
        """
        settings_file = os.environ.get("CI-SETTINGS") or os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "config.yaml"
        )
        if not os.path.exists(settings_file):
            raise RuntimeError(
                "No user configuration is specified or the configuration file does not exist."
                "that needs to be loaded: CI-SETTINGS"
            )

        self._setting_container = Configs(settings_file)

    def __getattr__(self, name):
        """
        Return the value of a setting and cache it in self.__dict__
        """
        if self._setting_container is None:
            self._preloading()
        value = getattr(self._setting_container, name, None)
        self.__dict__[name] = value
        return value

    def __setattr__(self, name, value):
        """
        Set the configured value and re-copy the value cached in __dict__
        """
        if name is None:
            raise KeyError("The set configuration key value cannot be empty")
        if name == "_setting_container":
            self.__dict__.clear()
            self.__dict__["_setting_container"] = value
        else:
            self.__dict__.pop(name, None)
        if self._setting_container is None:
            self._preloading()
        setattr(self._setting_container, name, value)

    def __delattr__(self, name):
        """
        Delete a setting and clear it from cache if needed
        """
        if name is None:
            raise KeyError("The set configuration key value cannot be empty")

        if self._setting_container is None:
            self._preloading()
        delattr(self._setting_container, name)
        self.__dict__.pop(name, None)

    @property
    def config_ready(self):
        """
        Return True if the settings have already been configured
        """
        return self._setting_container is not None

    def reload(self):
        """
        Add the reload mechanism
        """
        self._setting_container = None
        self._preloading()


class Configs:
    """
    The system's default configuration items and the user's
    configuration items are integrated
    """

    def __init__(self, settings_file):
        for config_item in dir(settings):
            if not config_item.startswith("_"):
                setattr(self, config_item.lower(), getattr(settings, config_item))

        for config_item, set_val in self.load_settings(settings_file).items():
            if set_val:
                setattr(self, config_item, set_val)

    @staticmethod
    def load_settings(settings_file):
        """
        Loading configuration items
        :param settings: config file
        """
        try:
            with open(settings_file, "r", encoding="utf-8") as file:
                _config = yaml.load(file, Loader=yaml.SafeLoader)

        except yaml.YAMLError:
            raise ValueError("Configuration file parsing error")
        return _config


config = PreloadingSettings()

__all__ = ("config",)
