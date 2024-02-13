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


def _get_raw(url, **kwargs):
    response = requests.get(url, **kwargs)
    if not response.ok:
        raise Exception(f"Failed to get reposnse {url}: {response.status_code} {response.text}")
    return response


def _get_all(url, **kwargs):
    while True:
        response = _get_raw(url, **kwargs)

        results = response.json()
        logging.debug(f"From {url} got {len(response.json())} results")

        for r in results:
            yield r

        if "next" in response.links:
            url = response.links["next"]["url"]
        else:
            break

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
        pr_user_login = pr["user"]["login"]
        pr_last_commit_sha = pr["head"]["sha"]
        logging.debug(f"PR {pr_number}/{pr_issue_url} last updated at {pr_updated_at} head commit {pr_last_commit_sha} is being considered")

        if pr["draft"] == True:
            logging.debug(f"PR {pr_number}/{pr_issue_url} last updated at {pr_updated_at} is a draft, skipping it")

        if pr_issue_url in status and pr_updated_at == status[pr_issue_url]["updated_at"]:
            logging.debug(f"PR {pr_number}/{pr_issue_url} last updated at {pr_updated_at} already processed, skipping it")
            continue

        if pr_issue_url in status and \
           "last_commit_sha" in status[pr_issue_url] and \
           pr_last_commit_sha == status[pr_issue_url]["last_commit_sha"]:
            logging.debug(f"PR {pr_number}/{pr_issue_url} last commit {pr_last_commit_sha} already processed, skipping it")
            continue

        if args.author_in_org is not None:
            url = f"https://api.github.com/orgs/{args.author_in_org}/memberships/{pr_user_login}"
            response = requests.get(url, headers=_headers(args))
            if response.status_code != 200 \
               or "organization" not in response.json() \
               or args.author_in_org != response.json()["organization"]["login"]:
                logging.debug(f"PR {pr_number}/{pr_issue_url} author {pr_user_login} is not member of {args.author_in_org}, skipping it")
                continue

        if args.successful_check is not None:
            url = f"https://api.github.com/repos/{args.owner}/{args.repo}/statuses/{pr_last_commit_sha}"
            statuses_filtered = [s for s in _get_all(url, headers=_headers(args)) if s["context"] == args.successful_check]
            logging.debug(f"PR {pr_number}/{pr_issue_url} have '{args.successful_check}' checks from {', '.join([s['updated_at'] for s in statuses_filtered])}")
            if len(statuses_filtered) != 0:
                status_max = max(statuses_filtered, key=lambda s: s["updated_at"])
                if status_max["state"] != "success":
                    logging.debug(f"PR {pr_number}/{pr_issue_url} - {pr_last_commit_sha} does not have expected state, skipping it")
                    continue
            else:
                logging.debug(f"PR {pr_number}/{pr_issue_url} does not have expected '{args.successful_check}' check, skipping it")
                continue

        print(f"{pr_number} {pr_issue_url} {pr_updated_at} {pr_last_commit_sha}")
        break


def load_pr(args):
    url = f"https://api.github.com/repos/{args.owner}/{args.repo}/pulls/{args.pr_number}"
    response = requests.get(url, headers=_headers(args))
    pr = response.json()

    pr_number = pr["number"]
    pr_issue_url = pr["issue_url"]
    pr_updated_at = pr["updated_at"]

    pr_last_commit = [c for c in _get_all(pr["commits_url"], headers=_headers(args))][-1]
    pr_last_commit_sha = pr_last_commit["sha"]

    print(f"{pr_number} {pr_issue_url} {pr_updated_at} {pr_last_commit_sha}")


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
    parser_find_pr.add_argument('--author-in-org', default=None, help='Skip PRs from authors not in this organization')
    parser_find_pr.add_argument('--successful-check', default=None, help='Skip PRs that did not passed this check')

    parser_load_pr = subparsers.add_parser('load_pr', help='Load details for given PR')
    parser_load_pr.set_defaults(func=load_pr)
    parser_load_pr.add_argument('--owner', required=True, help='Owner of the repo')
    parser_load_pr.add_argument('--repo', required=True, help='Repo name')
    parser_load_pr.add_argument('--pr-number', default='', help='Do not find PR, just ')

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
