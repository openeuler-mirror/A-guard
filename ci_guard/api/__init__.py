#!/usr/bin/python3
# ******************************************************************************
# Copyright (c) Huawei Technologies Co., Ltd. 2021-2021. All rights reserved.
# licensed under the Mulan PSL v2.
# You can use this software according to the terms and conditions of the Mulan PSL v2.
# You may obtain a copy of Mulan PSL v2 at:
#     http://license.coscl.org.cn/MulanPSL2
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FIT FOR A PARTICULAR
# PURPOSE.
# See the Mulan PSL v2 for more details.
# ******************************************************************************/
import requests
from requests.exceptions import RequestException
from retrying import retry, RetryError
import constant
from logger import logger


class Api:
    @staticmethod
    def _post(url, data, text=False, **kwargs):
        """
        POST into gitee API
        """
        try:
            return Api._request(url=url, method="post", data=data, text=text, **kwargs)
        except RetryError:
            logger.warning(f"Request post error: {url}.")
            return None

    @staticmethod
    def _patch(url, data, text=False, **kwargs):
        """
        Patch into gitee API
        """
        try:
            return Api._request(url=url, method="patch", data=data, text=text, **kwargs)
        except RetryError:
            logger.warning(f"Request patch error: {url}.")
            return None

    @staticmethod
    def _put(url, data=None, text=False, **kwargs):
        """
        Put into gitee API
        """
        try:
            return Api._request(url=url, method="put", data=data, text=text, **kwargs)
        except RetryError:
            logger.warning(f"Request put error: {url}.")
            return None

    @staticmethod
    def _get(url, params=None, text=False, **kwargs):
        """
        HTTP GET request
        """
        try:
            return Api._request(url=url, method="get", data=params, text=text, **kwargs)
        except RetryError:
            logger.warning(f"Request get error: {url}")
            return None

    @staticmethod
    def _delete(url, text=False, **kwargs):
        """
        Delete into gitee API
        """
        try:
            return Api._request(url=url, method="delete", text=text, **kwargs)
        except RetryError:
            logger.warning(f"Request delete error: {url}")
            return None

    @staticmethod
    @retry(
        retry_on_result=lambda result: result is None,
        stop_max_attempt_number=constant.STOP_MAX_ATTEMPT_NUMBER,
        wait_fixed=constant.WAIT_FIXED,
    )
    def _request(url, method="get", data=None, text=False, **kwargs):
        """
        POST into gitee API
        """
        if data:
            if method == "get":
                kwargs["params"] = data
            else:
                kwargs["data"] = data
        try:
            if "timeout" not in kwargs:
                kwargs["timeout"] = 30
            response = requests.request(method=method, url=url, verify=False, **kwargs)
        except RequestException as error:
            logger.error(f"Call url {url} failed, message: {error}")
            return None
        success_code = (
            requests.codes.ok,
            requests.codes.created,
            requests.codes.no_content,
        )
        if response.status_code not in success_code:
            logger.warning(f"reuqest url: {url} status code: {response.status_code}")
            return None if response.status_code != requests.codes.not_found else False
        if response.status_code == requests.codes.no_content:
            return dict(delete="success")
        return response.text if text else response.json()
