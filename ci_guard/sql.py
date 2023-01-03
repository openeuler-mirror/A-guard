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
import pymysql
from pymysql.cursors import DictCursor
from conf import config
from logger import logger


class Mysql:
    """
    Mysql database link and execute
    """

    db = None

    def __init__(self) -> None:
        self._cursor = None
        self.db = self._conn()

    def _conn(self):
        return pymysql.connect(
            host=config.db_host,
            user="root",
            password=config.user_passwd[5:],
            port=config.port,
            database="citools",
            cursorclass=DictCursor,
        )

    @property
    def cursor(self):
        """database cursor"""
        if not self.db.connect():
            self.db = self._conn()

        if self._cursor is None:
            self._cursor = self.db.cursor()
        return self._cursor

    def close(self):
        """close cursor"""
        if self._cursor:
            self._cursor.close()
        self.db.close()

    def __enter__(self):
        self._cursor = self.db.cursor()
        return self

    def first(self, sql, param: list = None):
        """
        Get first result
        :param sql: Sql script
        :param param: Sql condition parameters
        """
        if not self.execute(sql=sql, param=param, commit=False):
            return None
        return self._cursor.fetchone()

    def execute(self, sql, param: list = None, commit=True):
        """
        Execute sql script
        :param sql: Sql script
        :param param: Sql condition parameters
        :param commit: Performing database commit
        """
        if not sql:
            return False
        try:
            self._cursor.execute(sql, param)
        except pymysql.MySQLError as error:
            self.db.rollback()
            logger.error(error)
            return False
        if commit:
            self.db.commit()
        return True

    def all(self, sql, params: list = None):
        """
        Get all data that matches the filter
        :param sql: Sql script
        :param param: Sql condition parameters
        """
        if not self.execute(sql=sql, param=params, commit=False):
            return None
        return self._cursor.fetchall()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._cursor.close()
