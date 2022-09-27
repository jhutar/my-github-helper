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


def load_status():
    if not os.path.isfile(STATUS_FILE):
        with open(STATUS_FILE, "w+") as fp:
            yaml.dump({}, fp)

    with open(STATUS_FILE, "r+") as fp:
        data = yaml.load(fp, Loader=yaml.Loader)

    if data is None:
        data = {}

    return data



def dump_status(data):
    with open(STATUS_FILE, "w") as fp:
        yaml.dump(data, fp)


def find_pr(args):
    status = load_status()

    url = f"https://api.github.com/repos/{args.owner}/{args.repo}/pulls"
    params = {
        "state": "open",
    }

    page = 1
    results = []
    while True:
        logging.debug(f"Loading {url} page {page}")
        params_this = {"page": page}
        params_this.update(params)

        response = requests.get(url, headers=_headers(args), params=params_this)
        if not response.ok:
            raise Exception(f"Failed to get reposnse {url} page {page}: {response.status_code} {response.text}")

        if len(response.json()) == 0:
            break

        results += response.json()
        logging.debug(f"Got {len(response.json())} results")
        page += 1

    for pr in sorted(results, key=lambda d: d['updated_at'], reverse=True):
        pr_issue_url = pr["issue_url"]
        pr_updated_at = pr["updated_at"]
        if pr_issue_url in status:
            if pr_updated_at == status[pr_issue_url]["updated_at"]:
                logging.debug(f"PR {pr_issue_url} last updated at {pr_updated_at} already processed, skipping it")
            else:
                logging.info(f"PR {pr_issue_url} last updated at {pr_updated_at} last processed for change from {status[pr_issue_url]['updated_at']}, need to process it")
                print(f"{pr_issue_url} {pr_updated_at}")
                break
        else:
            logging.info(f"PR {pr_issue_url} last updated at {pr_updated_at} not yet processed, need to process it")
            print(f"{pr_issue_url} {pr_updated_at}")
            break


def processed_pr(args):
    status = load_status()
    status[args.issue_url] = {"updated_at": args.updated_at}
    dump_status(status)


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

    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    logging.debug(f"Args: {args}")

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
