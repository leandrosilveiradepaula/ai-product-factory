#!/usr/bin/python3
"""Root-installed, fixed-scope rollout controller. Not a worker or merge adapter.

Install a reviewed immutable copy outside the Git checkout. A new revision of
this controller itself requires administrator review/install. The controller
only reads GitHub's API, fetches the exact owner-merged main, and advances the
existing native worker after its latest exact-SHA push CI passed.
"""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request

REPO = "leandrosilveiradepaula/ai-product-factory"
OWNER_ID = 256917842
VALIDATE_ID = 367143797
API = "https://api.github.com/repos/" + REPO
CHECKOUT = Path("/opt/ai-product-factory/worker")
PIN_FILE = Path("/etc/ai-product-factory/infodive.env")
STATE = Path("/var/lib/ai-product-factory-rollout")
JOURNAL = STATE / "pending.json"
PIN = b"FACTORY_SQL_INFODIVE_WORKER_SHA="
TIMERS = ("ai-product-factory-infodive-product.timer",
          "ai-product-factory-infodive-direct.timer")
SERVICES = tuple(t.replace(".timer", ".service") for t in TIMERS)
SHA = re.compile(r"[0-9a-f]{40}\Z")
# Do not pass the wake token or any worker/model secrets to subprocesses.
ENV = {"PATH": "/usr/bin:/bin", "HOME": "/root", "LANG": "C",
       "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1"}


class Blocked(Exception):
    pass


def require(condition, reason):
    if not condition:
        raise Blocked(reason)


def sha(value):
    return isinstance(value, str) and SHA.fullmatch(value) is not None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def github_reader(token):
    require(isinstance(token, str) and token.strip() == token and bool(token)
            and not any(c in token for c in "\r\n"), "wake_credential_unavailable")
    opener = urllib.request.build_opener(NoRedirect())
    def get(path):
        require(path.startswith("/") and not path.startswith("//"), "api_path_invalid")
        req = urllib.request.Request(API + path, headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + token,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "factory-native-rollout/1",
        })
        with opener.open(req, timeout=12) as response:
            require(response.status == 200, "github_read_failed")
            data = response.read(4 * 1024 * 1024 + 1)
        require(len(data) <= 4 * 1024 * 1024, "github_response_too_large")
        return json.loads(data)
    return get


def main_sha(get):
    row = get("/git/ref/heads/main")
    require(row.get("ref") == "refs/heads/main"
            and row.get("object", {}).get("type") == "commit", "main_ref_invalid")
    target = row["object"].get("sha")
    require(sha(target), "main_sha_invalid")
    return target


def admit(get, target):
    """Validate an actual owner merge plus latest successful push CI."""
    require(sha(target) and main_sha(get) == target, "main_changed")
    candidates = get("/commits/" + target + "/pulls?per_page=100")
    require(isinstance(candidates, list) and 0 < len(candidates) < 100,
            "merge_association_unavailable")
    matched = [x for x in candidates if isinstance(x, dict)
               and x.get("merge_commit_sha") == target and x.get("merged_at")]
    require(len(matched) == 1 and type(matched[0].get("number")) is int,
            "owner_merge_unverified")
    pr = get("/pulls/" + str(matched[0]["number"]))
    owner = pr.get("merged_by") or {}
    base = pr.get("base") or {}
    require(pr.get("merged") is True and pr.get("merge_commit_sha") == target
            and pr.get("merged_at") and pr.get("number") == matched[0]["number"]
            and base.get("ref") == "main"
            and (base.get("repo") or {}).get("full_name") == REPO
            and owner.get("id") == OWNER_ID and owner.get("type") == "User",
            "owner_merge_unverified")
    query = urllib.parse.urlencode({"head_sha": target, "branch": "main",
                                   "event": "push", "per_page": 100})
    result = get("/actions/workflows/" + str(VALIDATE_ID) + "/runs?" + query)
    runs = result.get("workflow_runs")
    require(isinstance(runs, list) and 0 < len(runs) == result.get("total_count") < 100,
            "push_ci_unavailable")
    require(all(type(x.get("id")) is int and type(x.get("run_number")) is int
                for x in runs), "push_ci_identity_invalid")
    run = max(runs, key=lambda x: x["run_number"])
    require(run.get("workflow_id") == VALIDATE_ID
            and run.get("path") == ".github/workflows/validate.yml"
            and run.get("event") == "push" and run.get("head_sha") == target
            and run.get("head_branch") == "main"
            and (run.get("repository") or {}).get("full_name") == REPO
            and (run.get("head_repository") or {}).get("full_name") == REPO
            and run.get("status") == "completed" and run.get("conclusion") == "success"
            and type(run.get("run_attempt")) is int and run["run_attempt"] > 0,
            "latest_push_ci_not_successful")
    jobs = get("/actions/runs/" + str(run["id"]) + "/attempts/"
               + str(run["run_attempt"]) + "/jobs?per_page=100")
    rows = jobs.get("jobs")
    require(isinstance(rows, list) and len(rows) == jobs.get("total_count") == 2,
            "push_ci_jobs_unverified")
    require({x.get("name") for x in rows} == {"test", "factory-acceptance"}
            and all(x.get("head_sha") == target
                    and x.get("run_attempt") == run["run_attempt"]
                    and x.get("status") == "completed" and x.get("conclusion") == "success"
                    for x in rows), "push_ci_jobs_unverified")
    return {"sha": target, "pr": pr["number"], "ci_run": run["id"],
            "ci_attempt": run["run_attempt"]}


def cmd(*argv, timeout=60):
    p = subprocess.run(argv, env=ENV, capture_output=True, check=False, timeout=timeout)
    # Never echo output, arguments or exception bodies: git credentials may
    # appear in helper diagnostics, and systemd state is locally privileged.
    require(p.returncode == 0, "local_command_failed")
    return p.stdout


def git(*args):
    return cmd("/usr/bin/git", "-c", "core.hooksPath=/dev/null",
               "-c", "core.fsmonitor=false", "-c", "submodule.recurse=false",
               "-C", str(CHECKOUT), *args)


def unit_property(unit, name):
    return cmd("/usr/bin/systemctl", "show", "--value", "-p", name, unit).decode().strip()


def assert_idle(wait_seconds=0):
    deadline = time.monotonic() + wait_seconds
    while True:
        states = [unit_property(s, "ActiveState") for s in SERVICES]
        jobs = [unit_property(s, "Job") for s in SERVICES]
        if all(s == "inactive" for s in states) and all(j in ("", "0") for j in jobs):
            return
        require(time.monotonic() < deadline, "worker_busy_or_unhealthy")
        time.sleep(2)


def timers_stop():
    cmd("/usr/bin/systemctl", "stop", *TIMERS)


def timers_start(saved):
    if saved:
        cmd("/usr/bin/systemctl", "start", *saved)


def trusted(path, *, directory=False, private=False):
    s = path.lstat()
    require(s.st_uid == 0 and not (s.st_mode & 0o022)
            and (stat.S_ISDIR(s.st_mode) if directory else stat.S_ISREG(s.st_mode))
            and (not private or not (s.st_mode & 0o077)), "local_ownership_invalid")
    return s


def atomic_write(path, data, *, mode):
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".factory-rollout-",
                                     delete=False) as temp:
        name = temp.name
        try:
            os.fchmod(temp.fileno(), mode)
            temp.write(data)
            temp.flush()
            os.fsync(temp.fileno())
            os.replace(name, path)
            fd = os.open(path.parent, os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        finally:
            if os.path.exists(name):
                os.unlink(name)


def pin_value():
    trusted(PIN_FILE, private=True)
    data = PIN_FILE.read_bytes()
    lines = [line[len(PIN):] for line in data.splitlines() if line.startswith(PIN)]
    require(len(lines) == 1 and re.fullmatch(rb"[0-9a-f]{40}", lines[0]), "pin_invalid")
    return lines[0].decode()


def write_pin(old, new):
    require(sha(old) and sha(new) and pin_value() == old, "pin_changed")
    data = PIN_FILE.read_bytes()
    anchor = PIN + old.encode()
    lines = data.splitlines(keepends=True)
    require(sum(line.rstrip(b"\r\n") == anchor for line in lines) == 1, "pin_invalid")
    replacement = b"".join(PIN + new.encode() + line[len(anchor):]
                           if line.rstrip(b"\r\n") == anchor else line for line in lines)
    atomic_write(PIN_FILE, replacement, mode=0o600)
    require(pin_value() == new, "pin_update_failed")


def head():
    value = git("rev-parse", "--verify", "HEAD").decode().strip()
    require(sha(value), "checkout_sha_invalid")
    return value


def clean():
    require(not git("status", "--porcelain=v1", "--untracked-files=normal"),
            "checkout_not_clean")


def validate_origin():
    url = urllib.parse.urlsplit(git("remote", "get-url", "origin").decode().strip())
    require(url.scheme == "https" and url.hostname == "github.com"
            and url.port in (None, 443) and not url.username and not url.password
            and not url.query and not url.fragment
            and url.path.rstrip("/").removesuffix(".git") == "/" + REPO, "origin_unverified")


def compatible(old, target):
    # A Python-only checkout update must not pretend to deploy changed
    # dependencies, git filters/submodules, or installed worker unit files.
    paths = git("diff", "--name-only", "-z", "--no-renames", old, target).split(b"\0")
    forbidden = (b"pyproject.toml", b"uv.lock", b"poetry.lock", b"Pipfile",
                 b"Pipfile.lock", b".gitmodules", b".gitattributes")
    require(not any(p in forbidden or p.startswith(b"requirements")
                    or p.endswith(b"/.gitattributes")
                    or p.startswith(b"docs/systemd/ai-product-factory-infodive-")
                    or p.startswith(b"deploy/systemd/")
                    for p in paths), "dependency_or_unit_rollout_requires_admin")


def journal_read():
    trusted(JOURNAL, private=True)
    obj = json.loads(JOURNAL.read_bytes())
    require(set(obj) == {"old", "target", "timers"} and sha(obj["old"])
            and sha(obj["target"]) and obj["old"] != obj["target"]
            and isinstance(obj["timers"], list)
            and all(t in TIMERS for t in obj["timers"])
            and len(set(obj["timers"])) == len(obj["timers"]), "rollout_journal_invalid")
    return obj


def recover():
    j = journal_read()
    timers_stop()
    assert_idle(wait_seconds=60)
    clean()
    current, pin = head(), pin_value()
    require(current in (j["old"], j["target"]) and pin in (j["old"], j["target"]),
            "interrupted_rollout_identity_changed")
    if current != j["old"]:
        git("checkout", "--detach", j["old"])
    if pin != j["old"]:
        write_pin(pin, j["old"])
    clean()
    require(head() == pin_value() == j["old"], "rollback_unverified")
    timers_start(j["timers"])
    JOURNAL.unlink()
    return {"status": "rolled_back", "worker_sha": j["old"]}


def rollout(get):
    for d in (CHECKOUT.parent, CHECKOUT, CHECKOUT / ".git", PIN_FILE.parent, STATE):
        trusted(d, directory=True, private=(d in (PIN_FILE.parent, STATE)))
    if JOURNAL.exists():
        return recover()
    clean()
    old = head()
    require(pin_value() == old, "checkout_pin_mismatch")
    target = main_sha(get)
    if target == old:
        return {"status": "current", "worker_sha": old}
    receipt = admit(get, target)
    validate_origin()
    git("fetch", "--no-tags", "--no-recurse-submodules", "origin", "main")
    require(git("rev-parse", "FETCH_HEAD").decode().strip() == target, "fetched_sha_changed")
    git("merge-base", "--is-ancestor", old, target)
    compatible(old, target)
    # Do not interrupt an in-flight worker. Stop only its timers, wait
    # briefly for existing work to finish, and preserve active timer state.
    saved = [t for t in TIMERS if unit_property(t, "ActiveState") == "active"]
    atomic_write(JOURNAL, json.dumps({"old": old, "target": target, "timers": saved}).encode(),
                 mode=0o600)
    try:
        timers_stop()
        assert_idle(wait_seconds=60)
        clean()
        require(head() == pin_value() == old, "checkout_or_pin_changed")
        require(admit(get, target) == receipt, "merge_or_ci_changed")
        git("checkout", "--detach", target)
        clean()
        require(head() == target, "checkout_update_failed")
        write_pin(old, target)
        require(head() == pin_value() == target, "rollout_unverified")
        # Once the new checkout and pin agree, record the completed
        # transition before restarting timers. Keep the journal if start fails.
        timers_start(saved)
        JOURNAL.unlink()
        return {"status": "updated", "old_sha": old, "worker_sha": target, **receipt}
    except Exception:
        # If a worker became active before timers stopped, do not kill it or
        # mutate its checkout. The persistent journal enables a later recovery.
        if head() == pin_value() == old:
            timers_start(saved)
            JOURNAL.unlink()
        else:
            recover()
        raise Blocked("rollout_not_applied_or_rolled_back") from None


def main():
    try:
        require(os.geteuid() == 0, "root_installation_required")
        trusted(STATE, directory=True, private=True)
        lock = os.open(STATE / "rollout.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(lock, "wb") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = rollout(github_reader(os.environ.get("FACTORY_VPS_GITHUB_TOKEN", "")))
        print(json.dumps(result, sort_keys=True))
        return 0
    except Blocked as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}, sort_keys=True))
        return 2
    except Exception:
        print('{"status":"blocked","reason":"rollout_unavailable"}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
