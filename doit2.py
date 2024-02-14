#!/usr/bin/env python3

import argparse
import datetime
import logging
import os
import re
import subprocess
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
            if key in {"created_at"}:
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
        raise Exception(
            f"Failed to get reposnse {url}: {response.status_code} {response.text}"
        )
    return response


def _get_raw(url, **kwargs):
    response = requests.get(url, **kwargs)
    if not response.ok:
        raise Exception(
            f"Failed to get reposnse {url}: {response.status_code} {response.text}"
        )
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
    _post_raw(url, headers=_headers(args), json={"body": args.body})


def add_comment(args):
    create_issue_comment(args)


def _checks_filter(args, data):
    if args.latest_by_context:
        data_new = {}
        for d in data:
            if d["context"] not in data_new:
                data_new[d["context"]] = d
            else:
                if d["created_at"] > data_new[d["context"]]["created_at"]:
                    data_new[d["context"]] = d
        data = list(data_new.values())

    if args.filter_by_state is not None:
        data = [d for d in data if d["state"] == args.filter_by_state]

    if args.filter_by_context_re is not None:
        data = [
            d
            for d in data
            if d["context"] is not None
            and re.search(args.filter_by_context_re, d["context"]) is not None
        ]

    if args.filter_by_target_url_re is not None:
        data = [
            d
            for d in data
            if d["target_url"] is not None
            and re.search(args.filter_by_target_url_re, d["target_url"]) is not None
        ]

    if args.filter_by_created_at_ge is not None:
        data = [d for d in data if d["created_at"] >= args.filter_by_created_at_ge]

    return data


def list_checks(args):
    data = get_pull_request(args)
    args.commit = data["head"]["sha"]

    data = list_commit_statuses_for_reference(args)

    data = _checks_filter(args, data)

    fields = ["created_at", "state", "context", "target_url"]
    table = []
    for d in data:
        logging.debug(f"Processing: {_json_dumps(d)}")
        row = [d[f] if f in d else None for f in fields]
        table.append(row)
    print(tabulate.tabulate(table, headers=fields))

    if args.prow_download_path is not None:
        print("")
        for d in data:
            guess_run_id = d["target_url"].split("/")[-1]
            guess_job_name = d["target_url"].split("/")[-2]
            guess_test_name = d["context"].split("/")[-1]

            if not os.path.exists(guess_run_id):
                os.makedirs(guess_run_id)

            runme = [
                "gsutil",
                "-m",
                "cp",
                "-r",
                f"gs://test-platform-results/pr-logs/pull/{args.owner}_{args.repo}/{args.pull_number}/{guess_job_name}/{guess_run_id}/artifacts/{guess_test_name}/{args.prow_download_path}",
                f"{guess_run_id}/",
            ]
            print(f"Downloading: {' '.join(runme)}")

            process = subprocess.Popen(
                runme, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            stdout, stderr = process.communicate()
            exit_code = process.returncode

            if exit_code != 0:
                logging.error(f"Failed to run: '{' '.join(runme)}'")
                logging.error(f"stdout: {stdout.decode()}")
                logging.error(f"stderr: {stderr.decode()}")
                logging.error(f"Exit code: {exit_code}")
                sys.exit(1)

            print(f"...finished with {exit_code}")


def main():
    parser = argparse.ArgumentParser(
        description="Let's talk to GitHub, record what was done",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--token",
        default=os.getenv("GITHUB_TOKEN", None),
        help="GitHub personal access token",
    )
    parser.add_argument("-d", "--debug", action="store_true", help="Show debug output")
    subparsers = parser.add_subparsers(help="Sub-command help")

    parser_list_checks = subparsers.add_parser("list_checks", help="List checks")
    parser_list_checks.set_defaults(func=list_checks)
    parser_list_checks.add_argument("--owner", required=True, help="Owner of the repo")
    parser_list_checks.add_argument("--repo", required=True, help="Repo name")
    parser_list_checks.add_argument("--pull-number", help="PR number")
    parser_list_checks.add_argument(
        "--filter-by-state", help="Only show checks with this state"
    )
    parser_list_checks.add_argument(
        "--filter-by-context-re",
        help="Only show checks with context matching this regexp, check automatically excluded if its context is empty",
    )
    parser_list_checks.add_argument(
        "--filter-by-target-url-re",
        help="Only show checks with target_url matching this regexp, check automatically excluded if its target_url is empty",
    )
    parser_list_checks.add_argument(
        "--filter-by-created-at-ge",
        type=datetime.datetime.fromisoformat,
        help="Only show checks with created_at >= of given date",
    )
    parser_list_checks.add_argument(
        "--latest-by-context",
        action="store_true",
        help="Only show latest checks for every context by created_at time",
    )
    parser_list_checks.add_argument(
        "--prow-download-path",
        help="Download artifacts from Prow at this path (e.g. 'openshift-pipelines-max-concurrency/artifacts/'",
    )

    parser_add_comment = subparsers.add_parser("add_comment", help="Add comment")
    parser_add_comment.set_defaults(func=add_comment)
    parser_add_comment.add_argument("--owner", required=True, help="Owner of the repo")
    parser_add_comment.add_argument("--repo", required=True, help="Repo name")
    parser_add_comment.add_argument("--issue-number", help="Issue (or PR) number")
    parser_add_comment.add_argument("--body", help="Comment body")

    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    logging.debug(f"Args: {args}")

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
