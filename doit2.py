#!/usr/bin/env python3

import argparse
import datetime
import logging
import os
import re
import sys

import requests

import json

import tabulate


class _JSONDecoder(json.JSONDecoder):
    def __init__(self, *args, **kwargs):
        json.JSONDecoder.__init__(self, object_hook=self.object_hook, *args, **kwargs)

    def object_hook(self, obj):
        ret = {}
        for key, value in obj.items():
            if key in {'created_at'}:
                ret[key] = datetime.datetime.fromisoformat(value)
            else:
                ret[key] = value
        return ret

class _JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime.date, datetime.datetime)):
            return obj.isoformat()
        return json.JSONEncoder.default(obj)


def _headers(args):
    headers = {
        "Accept": "application/vnd.github+json",
    }
    if args.token is not None:
        headers["Authorization"] = f"Bearer {args.token}"
    return headers


def _post_raw(url, **kwargs):
    response = requests.post(url, **kwargs)
    if not response.ok:
        raise Exception(f"Failed to get reposnse {url}: {response.status_code} {response.text}")
    return response


def _get_raw(url, **kwargs):
    response = requests.get(url, **kwargs)
    if not response.ok:
        raise Exception(f"Failed to get reposnse {url}: {response.status_code} {response.text}")
    return response


def _json_loads(text):
    return json.loads(text, cls=_JSONDecoder)


def _json_dumps(data):
    return json.dumps(data, cls=_JSONEncoder)


def _get_all(url, **kwargs):
    while True:
        response = _get_raw(url, **kwargs)

        results = _json_loads(response.text)
        logging.debug(f"From {url} got {len(results)} results")

        for r in results:
            yield r

        if "next" in response.links:
            url = response.links["next"]["url"]
        else:
            break


def list_commit_statuses_for_reference(args):
    url = f"https://api.github.com/repos/{args.owner}/{args.repo}/commits/{args.commit}/statuses"
    data = []
    for response in _get_all(url, headers=_headers(args)):
        data.append(response)
    return data


def get_pull_request(args):
    url = f"https://api.github.com/repos/{args.owner}/{args.repo}/pulls/{args.pull_number}"
    data = _json_loads(_get_raw(url, headers=_headers(args)).text)
    return data


def create_issue_comment(args):
    url = f"https://api.github.com/repos/{args.owner}/{args.repo}/issues/{args.issue_number}/comments"
    data = _post_raw(url, headers=_headers(args), json={"body": args.body})


def add_comment(args):
    create_issue_comment(args)

def list_checks(args):
    data = get_pull_request(args)
    args.commit = data["head"]["sha"]

    data = list_commit_statuses_for_reference(args)

    if args.latest_by_context:
        data_new = {}
        for d in data:
            if d["context"] not in data_new:
                data_new[d["context"]] = d
            else:
                if d["created_at"] > data_new[d["context"]]["created_at"]:
                    data_new[d["context"]] = d
        data = list(data_new.values())

    fields = ["created_at", "state", "context", "target_url"]
    table = []
    for d in data:
        logging.debug(f"Processing: {_json_dumps(d)}")
        if args.filter_by_state is not None:
            if d["state"] != args.filter_by_state:
                continue
        if args.filter_by_context_re is not None:
            if d["context"] is None or re.search(args.filter_by_context_re, d["context"]) is None:
                continue
        if args.filter_by_target_url_re is not None:
            if d["target_url"] is None or re.search(args.filter_by_target_url_re, d["target_url"]) is None:
                continue
        if args.filter_by_created_at_ge is not None:
            if d["created_at"] < args.filter_by_created_at_ge:
                continue
        row = []
        for f in fields:
            row.append(d[f] if f in d else None)
        table.append(row)
    print(tabulate.tabulate(table, headers=fields))

    #data = create_issue_comment(args)

    #print(json.dumps(data))


# job=rehearse-47362-pull-ci-openshift-pipelines-performance-main-max-concurrency-downstream-1-13-1000-60-b
# name=max-concurrency-downstream-1-13-1000-60-b
# scenario=1000-60
# run=1746829502866001920
# gs://test-platform-results/pr-logs/pull/openshift_release/$pr/$job/$run/artifacts/$name/openshift-pipelines-max-concurrency/artifacts/run-$scenario/ . &>gsutil.log

# ci/rehearse/openshift-pipelines/performance/main/max-concurrency-downstream-1-13-1000-60-g
# https://prow.ci.openshift.org/view/gs/test-platform-results/pr-logs/pull/openshift_release/47362/rehearse-47362-pull-ci-openshift-pipelines-performance-main-max-concurrency-downstream-1-13-1000-60-g/1746917217628327936


def main():
    parser = argparse.ArgumentParser(
        description="Let's talk to GitHub, record what was done",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--token',
                        default=os.getenv(f'GITHUB_TOKEN', None),
                        help='GitHub personal access token')
    parser.add_argument('-d', '--debug', action='store_true',
                        help='Show debug output')
    subparsers = parser.add_subparsers(help='Sub-command help')

    parser_list_checks = subparsers.add_parser('list_checks', help='List checks')
    parser_list_checks.set_defaults(func=list_checks)
    parser_list_checks.add_argument('--owner', required=True, help='Owner of the repo')
    parser_list_checks.add_argument('--repo', required=True, help='Repo name')
    parser_list_checks.add_argument('--pull-number', help='PR number')
    parser_list_checks.add_argument('--filter-by-state', help='Only show checks with this state')
    parser_list_checks.add_argument('--filter-by-context-re', help='Only show checks with context matching this regexp, check automatically excluded if its context is empty')
    parser_list_checks.add_argument('--filter-by-target-url-re', help='Only show checks with target_url matching this regexp, check automatically excluded if its target_url is empty')
    parser_list_checks.add_argument('--filter-by-created-at-ge', type=datetime.datetime.fromisoformat, help='Only show checks with created_at >= of given date')
    parser_list_checks.add_argument('--latest-by-context', action='store_true', help='Only show latest checks for every context by created_at time')

    parser_add_comment = subparsers.add_parser('add_comment', help='Add comment')
    parser_add_comment.set_defaults(func=add_comment)
    parser_add_comment.add_argument('--owner', required=True, help='Owner of the repo')
    parser_add_comment.add_argument('--repo', required=True, help='Repo name')
    parser_add_comment.add_argument('--issue-number', help='Issue (or PR) number')
    parser_add_comment.add_argument('--body', help='Comment body')

    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    logging.debug(f"Args: {args}")

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
