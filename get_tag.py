#!/usr/bin/env python3

import argparse
import datetime
import http.client
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

_RETRIES = 3
_SEP_BRANCH = ":"
_SEP_BASE = "@"
_DEFAULT_BRANCH = ""
_DEFAULT_GH_BASE = "https://api.github.com"
_DEFAULT_GL_BASE = "https://gitlab.com"
_CR_COICES = {
    "hourly": "%Y-%m-%dT%H",
    "daily": "%Y-%m-%d",
    "weekly": "%Y-W%V",
    "monthly": "%Y-%m",
    "yearly": "%Y",
}
_CR_COICES["annually"] = _CR_COICES["yearly"]


def _urlopen(url: str, __retries: int = _RETRIES) -> http.client.HTTPResponse:
    if _RETRIES == __retries:
        print(f"{url=}", file=sys.stderr)
    try:
        response = urllib.request.urlopen(url)
        assert 200 == response.status
        return response
    except Exception:
        if __retries:
            sleep = 30 * (_RETRIES - __retries + 1)
            print(f"{sleep=}", file=sys.stderr)
            time.sleep(sleep)
            return _urlopen(url, __retries - 1)
        raise


def get_pip_versions_1(package: str) -> list[str]:
    process = subprocess.run(["pip", "install", f"{package}=="], capture_output=True)
    match = re.search(r"\(from versions: (.*)\)", process.stderr.decode())
    assert match
    return match.group(1).split(", ")


def get_pip_versions_2(package: str) -> list[str]:
    url = f"https://pypi.org/pypi/{package}/json"
    response = _urlopen(url)
    releases = json.loads(response.read())["releases"]
    versions = filter(
        lambda release: (release := releases[release]) and not release[0]["yanked"],
        releases,
    )
    return sorted(
        versions, key=lambda release: releases[release][0]["upload_time_iso_8601"]
    )


def get_pip_versions_3(package: str) -> list[str]:
    process = subprocess.run(
        ["pip", "index", "versions", package], capture_output=True, check=True
    )
    return process.stdout.decode().splitlines()[1][20:].split(", ")[::-1]


def get_pip_versions(package: str) -> list[str]:
    return get_pip_versions_2(package)


def get_pip_version_1(package: str) -> str:
    return get_pip_versions_1(package)[-1]


def get_pip_version_2(package: str) -> str:
    return get_pip_versions_2(package)[-1]


def get_pip_version_3(package: str) -> str:
    return get_pip_versions_3(package)[-1]


def get_pip_version_4(package: str) -> str:
    subprocess.check_call(["pip", "install", "--upgrade", package])
    process = subprocess.run(["pip", "freeze"], capture_output=True, check=True)
    startswith = f"{package}=="
    for frozen in process.stdout.decode().splitlines():
        if frozen.startswith(startswith):
            return frozen[len(startswith) :]
    raise AssertionError


def get_pip_version(package: str) -> str:
    return get_pip_version_2(package)


def get_npm_versions_1(package: str) -> list[str]:
    url = f"https://registry.npmjs.org/{package}"
    response = _urlopen(url)
    versions = json.loads(response.read())["versions"]
    return list(versions.keys())


def get_npm_versions_2(package: str) -> list[str]:
    process = subprocess.run(
        ["npm", "show", package, "versions", "--json"],
        shell=True,
        capture_output=True,
        check=True,
    )
    return json.loads(process.stdout)


def get_npm_versions(package: str) -> list[str]:
    return get_npm_versions_1(package)


def get_npm_version_1(package: str) -> str:
    url = f"https://registry.npmjs.org/{package}"
    response = _urlopen(url)
    return json.loads(response.read())["dist-tags"]["latest"]


def get_npm_version_2(package: str) -> str:
    process = subprocess.run(
        ["npm", "show", package, "version"],
        shell=True,
        capture_output=True,
        check=True,
    )
    return process.stdout.decode().strip()


def get_npm_version(package: str) -> str:
    return get_npm_version_1(package)


def get_go_versions_1(module: str) -> list[str]:
    url = f"https://proxy.golang.org/{module}/@v/list"
    response = _urlopen(url)
    versions: list[dict[str, str]] = []
    for version in response.read().decode().splitlines():
        url_version = f"https://proxy.golang.org/{module}/@v/{version}.info"
        response_version = _urlopen(url_version)
        versions.append(json.loads(response_version.read()))
    raise NotImplementedError


def get_go_versions_2(module: str) -> list[str]:
    process = subprocess.run(
        ["go", "list", "-json", "-m", "-versions", module],
        capture_output=True,
        check=True,
    )
    return json.loads(process.stdout)["Versions"]


def get_go_versions(module: str) -> list[str]:
    return get_go_versions_2(module)


def get_go_version_1(module: str) -> str:
    url = f"https://proxy.golang.org/{module}/@latest"
    response = _urlopen(url)
    return json.loads(response.read())["Version"]


def get_go_version_2(module: str) -> str:
    return get_go_versions_2(module)[-1]


def get_go_version(module: str) -> str:
    return get_go_version_1(module)


def _get_repository_base(repository: str, default_base: str) -> tuple[str, str]:
    if _SEP_BASE not in repository:
        repository += _SEP_BASE + default_base
    return tuple(repository.split(_SEP_BASE, 1))  # type: ignore[return-value]


def _get_repository_branch(repository: str) -> tuple[str, str]:
    if _SEP_BRANCH not in repository:
        repository += _SEP_BRANCH + _DEFAULT_BRANCH
    return tuple(repository.split(_SEP_BRANCH, 1))  # type: ignore[return-value]


def _get_repository_path(repository: str) -> tuple[str, str]:
    if 1 == repository.count("/"):
        repository += "/"
    owner, repository, path = repository.split("/", 2)
    return f"{owner}/{repository}", path


def _get_gh_repository_base(repository: str) -> tuple[str, str]:
    return _get_repository_base(repository, _DEFAULT_GH_BASE)


def get_gh_commits(repository: str) -> list[str]:
    repository, base = _get_gh_repository_base(repository)
    repository, branch = _get_repository_branch(repository)
    repository, path = _get_repository_path(repository)
    url = f"{base}/repos/{repository}/commits?sha={branch}&path={path}"
    response = _urlopen(url)
    return [result["sha"] for result in reversed(json.loads(response.read()))]


def get_gh_commit(repository: str) -> str:
    return get_gh_commits(repository)[-1]


def get_gh_tags(repository: str) -> list[str]:
    repository, base = _get_gh_repository_base(repository)
    url = f"{base}/repos/{repository}/tags"
    response = _urlopen(url)
    return [result["name"] for result in reversed(json.loads(response.read()))]


def get_gh_tag(repository: str) -> str:
    return get_gh_tags(repository)[-1]


def get_gh_releases_1(repository: str) -> list[str]:
    repository, base = _get_gh_repository_base(repository)
    url = f"{base}/repos/{repository}/releases"
    response = _urlopen(url)
    return [
        result["tag_name"]
        for result in reversed(json.loads(response.read()))
        if not result["draft"] and not result["prerelease"]
    ]


def get_gh_release_1(repository: str) -> str:
    return get_gh_releases_1(repository)[-1]


def get_gh_release_2(repository: str) -> str:
    repository, base = _get_gh_repository_base(repository)
    url = f"{base}/repos/{repository}/releases/latest"
    response = _urlopen(url)
    return json.loads(response.read())["tag_name"]


def get_gh_release(repository: str) -> str:
    return get_gh_release_2(repository)


def get_gh_deployments(repository: str) -> list[str]:
    repository, base = _get_gh_repository_base(repository)
    url = f"{base}/repos/{repository}/deployments"
    response = _urlopen(url)
    return [result["sha"] for result in reversed(json.loads(response.read()))]


def get_gh_deployment(repository: str) -> str:
    return get_gh_deployments(repository)[-1]


def _get_gl_repository_base(repository: str) -> tuple[str, str]:
    return _get_repository_base(repository, _DEFAULT_GL_BASE)


def _get_gl_repository(repository: str, base: str) -> int:
    if repository.isdigit():
        return int(repository)
    else:
        url = f"{base}/api/v4/projects/{repository.replace('/', '%2F')}"
        response = _urlopen(url)
        return json.loads(response.read())["id"]


def get_gl_commits(repository: str) -> list[str]:
    repository, base = _get_gl_repository_base(repository)
    repository, branch = _get_repository_branch(repository)
    url = f"{base}/api/v4/projects/{_get_gl_repository(repository, base)}/repository/commits?ref_name={branch}"
    response = _urlopen(url)
    return [result["id"] for result in reversed(json.loads(response.read()))]


def get_gl_commit(repository: str) -> str:
    return get_gl_commits(repository)[-1]


def get_gl_tags(repository: str) -> list[str]:
    repository, base = _get_gl_repository_base(repository)
    url = f"{base}/api/v4/projects/{_get_gl_repository(repository, base)}/repository/tags?order_by=version"
    response = _urlopen(url)
    return [result["name"] for result in reversed(json.loads(response.read()))]


def get_gl_tag(repository: str) -> str:
    return get_gl_tags(repository)[-1]


def get_cron_tag(cron: str) -> str:
    timestamp = datetime.datetime.now(datetime.UTC)
    return timestamp.strftime(_CR_COICES[cron])


def get_docker_tags(repository: str) -> list[str]:
    if repository == "":
        return []
    url = f"https://hub.docker.com/v2/repositories/{repository}/tags"
    response = _urlopen(url)
    return [result["name"] for result in json.loads(response.read())["results"]]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("docker_tag", default=os.environ.get("TAG_DOCKER"))
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--pip", default=os.environ.get("TAG_PIP"))
    group.add_argument("--npm", default=os.environ.get("TAG_NPM"))
    group.add_argument("--go", default=os.environ.get("TAG_GO"))
    group.add_argument("--gh-commit", default=os.environ.get("TAG_GH_COMMIT"))
    group.add_argument("--gh-tag", default=os.environ.get("TAG_GH_TAG"))
    group.add_argument("--gh-release", default=os.environ.get("TAG_GH_RELEASE"))
    group.add_argument("--gh-deployment", default=os.environ.get("TAG_GH_DEPLOYMENT"))
    group.add_argument("--gl-commit", default=os.environ.get("TAG_GL_COMMIT"))
    group.add_argument("--gl-tag", default=os.environ.get("TAG_GL_TAG"))
    group.add_argument("--cr", default=os.environ.get("TAG_CR"), choices=_CR_COICES)
    args = parser.parse_args()
    tags = get_docker_tags(args.docker_tag)
    if args.pip:
        tag = get_pip_version(args.pip)
    elif args.npm:
        tag = get_npm_version(args.npm)
    elif args.go:
        tag = get_go_version(args.go)
    elif args.gh_commit:
        tag = get_gh_commit(args.gh_commit)
    elif args.gh_tag:
        tag = get_gh_tag(args.gh_tag)
    elif args.gh_release:
        tag = get_gh_release(args.gh_release)
    elif args.gh_deployment:
        tag = get_gh_deployment(args.gh_deployment)
    elif args.gl_commit:
        tag = get_gl_commit(args.gl_commit)
    elif args.gl_tag:
        tag = get_gl_tag(args.gl_tag)
    elif args.cr:
        tag = get_cron_tag(args.cr)
    else:
        raise NotImplementedError
    if tag not in tags:
        print(f"tag={tag}")


if __name__ == "__main__":
    main()
