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
from core.pull_link import Pull
from core import extract_repo_pull, ProcessRecords
from logger import logger
from exception import LinkError


def _update_pull_link(repo, pull, pr_link, message=None):
    pr_links = pr_link.relation_verify(pull, repo)

    pull_link_result = dict(
        link_pr=[], be_link_pr=[], current_result="success", operation_meseage=message
    )
    pull_link_result["link_pr"] = [link for link in pr_links["link_pr"]]
    pull_link_result["be_link_pr"] = [be_link for be_link in pr_links["be_link_pr"]]
    records_pull_link = ProcessRecords(package=repo, pr=pull)

    # update record content
    records_pull_link.update_check_options(
        steps="pr_link_reult", check_result=pull_link_result
    )


def link(pull, source_pr_repo, target_pr_repo):
    """
    To establish the link pr
    :param source_pr_repo: source pr number and repo
    :param target_pr_repo: target pr number and repo
    """
    _link = pull.pull_link(
        source_pr_repo[-1], source_pr_repo[0], target_pr_repo[-1], target_pr_repo[0]
    )
    if _link["link_result"] == "failed":
        raise LinkError(f"Pull link failed: {_link['detail']}")
    _update_pull_link(source_pr_repo[0], source_pr_repo[-1], pull, _link["detail"])


def verify(pull, source_pr_repo, *args):
    """
    View or validate pr relationships
    :param pull: pull objecct
    :param source_pr_repo: verify pr number and repo
    """
    relations = pull.relation_verify(source_pr_repo[-1], source_pr_repo[0])
    echo = {"link_pr": "Link pull:", "be_link_pr": "Be Link Pull:"}
    for _link in relations:
        click.echo(click.style(echo[_link], fg="green"))
        for link_pull in relations[_link]:
            click.echo(
                f"Repo: {link_pull['package']} PR: {link_pull['pull']} State: {link_pull['status']}"
            )


def delete(pull, source_pr_repo, *args):
    """
    Delete pull link
    :param pull: pull objecct
    :param source_pr_repo: delte pr number and repo
    """
    result = pull.del_pull_link(source_pr_repo[-1], source_pr_repo[0])

    logger.info(
        f"""delett pull link by number:{source_pr_repo[-1]}
            delete state: {result['del_result']}
            detail message: {result['detail']}"""
    )

    if result["del_result"] == "success":
        _update_pull_link(
            source_pr_repo[0], source_pr_repo[-1], pull, result["del_result"]
        )
        click.echo("Delete Pull Link: " + click.style(result["del_result"], fg="green"))
    else:
        click.echo("Delete Pull Link: " + click.style(result["del_result"], fg="red"))
    click.echo("Detail: " + result["detail"])


def sync(pull, source_pr_repo, *args):
    """
    Force all associated PR to be synchronized
    :param pull: pull objecct
    :param source_pr_repo: merge pr number and repo
    """
    if not pull.synchronous_merge(source_pr_repo[-1], source_pr_repo[0]):
        click.echo(click.style("No", fg="red"))
        exit(1)
    click.echo(click.style("Yes", fg="green"))


def forced(pull, source_pr_repo, *args):
    """
    Force all associated PR to be synchronized
    :param pull: pull objecct
    :param source_pr_repo: merge pr number and repo
    """
    pull.forced_merge(source_pr_repo[-1], source_pr_repo[0])


@click.command("link", help="pull link")
@click.option(
    "-b",
    "--behavior",
    help="PR execution action",
    type=click.Choice(
        ["link", "verify", "delete", "sync", "forced"], case_sensitive=False
    ),
    default="link",
    show_default=True,
    required=True,
)
@click.option("-pr", help="PR complete path (source PR)")
@click.option("-tpr", "--target-pr", "target_pr", help="Target PR (PR to be linked)")
def pull_link(behavior, pr, target_pr):
    """Pr link operation"""
    source_pr_repo = extract_repo_pull(pr)
    target_pr_repo = extract_repo_pull(target_pr)
    if behavior == "link" and not all([source_pr_repo, target_pr_repo]):
        click.echo(click.style("Not a correct PR link", fg="red"))
        click.echo(
            click.style(
                "For example: https://gitee.com/openeuler/community/pulls/1", fg="green"
            )
        )
        exit(1)
    eval(behavior)(Pull(), source_pr_repo, target_pr_repo)


__all__ = ("pull_link",)
