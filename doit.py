#!/usr/bin/env python3

import argparse
import logging
import os
import sys

import requests

import yaml

STATUS_FILE = "status.yaml"


def _headers(args):
    headers = {
        "Accept": "application/vnd.github+json",
    }
    if args.token is not None:
        headers["Authorization"] = f"Bearer {args.token}"
    return headers


def _get_all(url, **kwargs):
    page = 1
    while True:
        logging.debug(f"Loading {url} page {page}")

        if "params" not in kwargs:
            kwargs["params"] = {"page": page}
        else:
            kwargs["params"]["page"] = page

        response = requests.get(url, **kwargs)
        if not response.ok:
            raise Exception(f"Failed to get reposnse {url} page {page}: {response.status_code} {response.text}")

        if len(response.json()) == 0:
            break

        results = response.json()
        logging.debug(f"Got {len(response.json())} results")
        page += 1

        for r in results:
            yield r


def _load_status():
    if not os.path.isfile(STATUS_FILE):
        with open(STATUS_FILE, "w+") as fp:
            yaml.dump({}, fp)

    with open(STATUS_FILE, "r+") as fp:
        data = yaml.load(fp, Loader=yaml.Loader)

    if data is None:
        data = {}

    return data


def _dump_status(data):
    with open(STATUS_FILE, "w") as fp:
        yaml.dump(data, fp)


def find_pr(args):
    status = _load_status()

    url = f"https://api.github.com/repos/{args.owner}/{args.repo}/pulls"
    params = {
        "state": "open",
        "sort": "updated",
        "direction": "desc",
    }

    for pr in _get_all(url, params=params, headers=_headers(args)):
        pr_number = pr["number"]
        pr_issue_url = pr["issue_url"]
        pr_updated_at = pr["updated_at"]

        if pr_issue_url in status and pr_updated_at == status[pr_issue_url]["updated_at"]:
            logging.debug(f"PR {pr_number}/{pr_issue_url} last updated at {pr_updated_at} already processed, skipping it")
            continue

        logging.debug(f"PR {pr_number}/{pr_issue_url} last updated at {pr_updated_at} might need to be processed")

        pr_last_commit = [c for c in _get_all(pr["commits_url"], headers=_headers(args))][-1]
        pr_last_commit_sha = pr_last_commit["sha"]

        if pr_issue_url in status and \
           "last_commit_sha" in status[pr_issue_url] and \
           pr_last_commit_sha == status[pr_issue_url]["last_commit_sha"]:
            logging.debug(f"Last commit {pr_last_commit_sha} already processed, skipping it")
            continue

        print(f"{pr_number} {pr_issue_url} {pr_updated_at} {pr_last_commit_sha}")
        break


def processed_pr(args):
    pr_number = int(args.issue_url.split('/')[-1])
    status = _load_status()
    status[args.issue_url] = {"number": pr_number, "updated_at": args.updated_at, "last_commit_sha": args.last_commit_sha}
    _dump_status(status)


def status_commit(args):
    url = f"https://api.github.com/repos/{args.owner}/{args.repo}/statuses/{args.commit}"
    data = {
        "state": args.status_state,
        "description": args.status_description,
        "context": args.status_context,
    }
    if "status_target_url" in args:
        data["target_url"] = args.status_target_url

    response = requests.post(url, headers=_headers(args), json=data)
    if not response.ok:
        raise Exception(f"Failed to post to {url}: {response.status_code} {response.text}")


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

    parser_find_pr = subparsers.add_parser('find_pr', help='Find PR that needs to be processed')
    parser_find_pr.set_defaults(func=find_pr)
    parser_find_pr.add_argument('--owner', required=True, help='Owner of the repo')
    parser_find_pr.add_argument('--repo', required=True, help='Repo name')

    parser_processed_pr = subparsers.add_parser('processed_pr', help='Store PR as processed')
    parser_processed_pr.set_defaults(func=processed_pr)
    parser_processed_pr.add_argument('--issue-url', required=True, help='PR issue url')
    parser_processed_pr.add_argument('--updated-at', required=True, help='PR updated at')
    parser_processed_pr.add_argument('--last-commit-sha', required=True, help='PR last commit SHA')

    parser_status_commit = subparsers.add_parser('status_commit', help='Add commit status')
    parser_status_commit.set_defaults(func=status_commit)
    parser_status_commit.add_argument('--owner', required=True, help='Owner of the repo')
    parser_status_commit.add_argument('--repo', required=True, help='Repo name')
    parser_status_commit.add_argument('--commit', required=True, help='Commit sha')
    parser_status_commit.add_argument('--status-state', required=True, choices=['error', 'failure', 'pending', 'success'], help='Status state')
    parser_status_commit.add_argument('--status-target-url', help='Status target url')
    parser_status_commit.add_argument('--status-description', required=True, help='Status description')
    parser_status_commit.add_argument('--status-context', required=True, help='Satus context')

    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    logging.debug(f"Args: {args}")

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
