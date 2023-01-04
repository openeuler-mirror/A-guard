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
import click
from core.comment import Comment
from exception import ParameterError


@click.command("comment", help="Add comments from pr")
@click.option(
    "-pr", "--pull-request", help="The pr that returns the comment information"
)
@click.option(
    "-m",
    "--message",
    help="""The content of the comment can not be filled
    If it is not filled in, the result file can be read for content concatenation""",
)
@click.option(
    "-p",
    "--process",
    help="""If you do not fill in the step that needs to be
    commented, read the current step in the result file for content concatenation""",
)
@click.option("-u", "--users", multiple=True, help="A list of people to remind")
def notify(pull_request, message, process, users):
    """
    Comment information to the specified pr
    :param pull_request: specified pr
    :param message: The content that needs to be commented
                    if not specified, it will be obtained from the result file
    :param process: Read the information of the specified
                    progress from process_message.yaml, and then comment to pr
    :param users: Users who need to be notified
    :return: None
    """
    click.echo("[INFO] Start to comment information")
    if not pull_request:
        raise ParameterError(pr=pull_request)

    comment_instance = Comment(
        pr_url=pull_request, message=message, process=process, users=users
    )
    comment_instance.comment_message()


__all__ = ("notify",)
