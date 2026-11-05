"""Bounded GitHub PR transport. Credentials never enter commands, files or logs."""
import json
import os
import re
import shutil
import subprocess
from urllib.request import Request, urlopen
from urllib.error import HTTPError


class GitHub:
    def __init__(self, repository):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository): raise ValueError("Invalid GitHub repository")
        self.repository = repository
        self._token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if not self._token and shutil.which("gh"):
            result = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True)
            if not result.returncode: self._token = result.stdout.strip()
        if not self._token:
            result = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
                capture_output=True, text=True, env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "Never"})
            if not result.returncode:
                fields = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
                self._token = fields.get("password")
        if not self._token: raise RuntimeError("GitHub authentication unavailable; configure gh auth login or GH_TOKEN")

    def request(self, method, path, body=None):
        if (path and not path.startswith("/")) or ".." in path: raise ValueError("Invalid GitHub endpoint")
        url = "https://api.github.com/repos/" + self.repository + path
        headers = {"Authorization": "Bearer " + self._token, "Accept": "application/vnd.github+json", "User-Agent": "UniversitySeedCuration/1"}
        data = json.dumps(body).encode() if body is not None else None
        if data is not None: headers["Content-Type"] = "application/json"
        try:
            with urlopen(Request(url, data=data, headers=headers, method=method), timeout=45) as response: return json.load(response)
        except HTTPError as error:
            raise RuntimeError("GitHub request failed (HTTP " + str(error.code) + "); credentials and response body withheld") from None

    def pull(self, number): return self.request("GET", "/pulls/" + str(int(number)))

    def open_research(self):
        rows = []
        for page in range(1, 21):
            batch = self.request("GET", "/pulls?state=open&per_page=100&page=" + str(page))
            rows += [p for p in batch if p["base"]["ref"] == "main" and p["head"]["ref"].startswith("codex/research-batch-")
                     and p["head"].get("repo", {}).get("full_name") == self.repository]
            if len(batch) < 100: return rows
        raise RuntimeError("Too many open PRs to safely enumerate; preserve state and reduce backlog")

    def create(self, branch, title, body, draft=False):
        return self.request("POST", "/pulls", {"head": branch, "base": "main", "title": title, "body": body, "draft": draft})

    def find_branch(self, branch):
        from urllib.parse import urlencode
        query = urlencode({"state": "all", "head": self.repository.split("/")[0] + ":" + branch, "per_page": 100})
        return [p for p in self.request("GET", "/pulls?" + query) if p["base"]["ref"] == "main" and p["head"]["ref"] == branch]

    def university_pulls(self):
        result = []
        for page in range(1, 21):
            batch = self.request("GET", "/pulls?state=open&per_page=100&page=" + str(page))
            result += [p for p in batch if p["base"]["ref"] == "main" and p["head"]["ref"].startswith("codex/university-")
                       and p["head"].get("repo", {}).get("full_name") == self.repository]
            if len(batch) < 100: return result
        raise RuntimeError("Open PR limit exceeded")

    def set_draft(self, pull, draft):
        name = "convertPullRequestToDraft" if draft else "markPullRequestReadyForReview"
        query = "mutation($id: ID!) { " + name + "(input: {pullRequestId: $id}) { pullRequest { isDraft } } }"
        body = json.dumps({"query": query, "variables": {"id": pull["node_id"]}}).encode()
        headers = {"Authorization": "Bearer " + self._token, "Content-Type": "application/json", "User-Agent": "UniversitySeedCuration/1"}
        try:
            with urlopen(Request("https://api.github.com/graphql", data=body, headers=headers, method="POST"), timeout=45) as response: result = json.load(response)
        except HTTPError as error: raise RuntimeError("GitHub draft transition failed (HTTP " + str(error.code) + ")") from None
        if result.get("errors"): raise RuntimeError("GitHub rejected the Draft transition; PR state is not assumed changed")
        return result


def marker(batch_id, qids):
    return "<!-- university-research " + json.dumps({"batch_id": batch_id, "qids": qids}, separators=(",", ":")) + " -->"


def parse_marker(pull):
    found = re.search(r"<!-- university-research (\{[^\n]*\}) -->", pull.get("body") or "")
    if not found: return None
    value = json.loads(found[1])
    if set(value) != {"batch_id", "qids"} or not 1 <= len(value["qids"]) <= 5 or any(not re.fullmatch(r"Q[1-9][0-9]*", q) for q in value["qids"]): raise ValueError("Invalid research PR marker")
    return value
