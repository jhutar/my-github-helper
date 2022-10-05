# my-github-helper

My helper for various tasks I need to achieve using GitHub API


## Usage

### `find_pr` - Find PR that needs to be processed

We go through PRs in given repository, sort them by last updated time
and we print first one where we have not marked it's last commit as
processed one.

If author's organization filter is provided, GH token needs `read:org`
scope to access non public membership of users.

We print one line with something like this:

    3525 https://api.github.com/repos/RedHatInsights/insights-core/issues/3525 2022-09-30T15:31:27Z eae440afe116293de760180a240bf290fc5e6c69

It is number of the PR, API link to the PR, last updated at time
and latest commit in the PR.

List of PRs: <https://api.github.com/repos/RedHatInsights/insights-core/pulls>

Get info about given PR: <https://api.github.com/repos/RedHatInsights/insights-core/pulls/3525>

Get commits in given PR: <https://api.github.com/repos/RedHatInsights/insights-core/pulls/3525/commits>

Check if user is member of organization: <https://api.github.com/orgs/RedHatInsights/memberships/userxyz>


### `processed_pr` - Store PR as processed

We mark given PR commit as processed, so `find_pr` will skip it next
time until new commit is added into the PR. This stores local database
of processed commits in yaml file:

    $ cat status.yaml
    https://api.github.com/repos/RedHatInsights/insights-core/issues/3531:
      last_commit_sha: 6e2aade957e16814b67697af16b1e1a27ae1b542
      number: 3531
      updated_at: '2022-09-26T08:54:48Z'
    https://api.github.com/repos/RedHatInsights/insights-core/issues/3539:
      last_commit_sha: e1937c3530f71777687293e3547265dcb37b1fc8
      number: 3539
      updated_at: '2022-10-04T19:07:13Z'


### `status_commit` - Add commit status

Add status for a given commit (i.e. also to relevant PR). You will need write
permission to the repo and GH token with `repo:status` scope for this.

About status checks: <https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/about-status-checks>

Commit statuses API: <https://docs.github.com/en/rest/commits/statuses>

Get list of statuses for given commit: <https://api.github.com/repos/RedHatInsights/insights-core/statuses/fa1d21a0c6ae621d710a313a1a27d8fcac21dc15>
