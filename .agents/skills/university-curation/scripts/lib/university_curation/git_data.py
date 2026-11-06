"""Read Git-bound data and validate exact public record bytes."""
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit
from .integrity import load_json
from .records import encode, record_path
from .preferred import fields

def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.PIPE)


def commit(repo, ref):
    if not re.fullmatch(r"[A-Za-z0-9_./-]+", ref) or ref.startswith("-"): raise ValueError("Invalid Git ref")
    return git(repo, "rev-parse", "--verify", ref + "^{commit}").decode().strip()


def blob(repo, ref, path, optional=False, max_bytes=2 * 1024**2):
    entry = git(repo, "ls-tree", "-z", ref, "--", path)
    if not entry:
        if optional: return None
        raise ValueError("Missing Git blob: " + path)
    info, found = entry.rstrip(b"\0").split(b"\t", 1)
    if found.decode() != path or info.split()[:2] != [b"100644", b"blob"]:
        raise ValueError("Data must be a regular non-executable Git blob")
    size = int(git(repo, "cat-file", "-s", info.split()[2].decode()))
    if size > max_bytes: raise ValueError("Oversized data blob")
    return git(repo, "cat-file", "blob", info.split()[2].decode())


def record_relative(entity_id):
    return record_path(Path.cwd(), entity_id).relative_to(Path.cwd().resolve()).as_posix()


def batch_slug(value):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", value): raise ValueError("Invalid batch ID")
    return value


def canonical_json(data):
    value = load_json(data)
    if encode(value) != data: raise ValueError("Public JSON must use canonical script encoding")
    return value


def check_source_revisions(record):
    """Fail closed on misleading public links to immutable Wikimedia revisions.

    Review checks the frozen source snapshot offline; this public check validates
    each record URL and source locator.
    """
    for reference, source in record.get("sources", {}).items():
        kind = source["kind"]
        if kind not in ("wikidata", "wikipedia"):
            continue
        revision = source["revision_id"]
        url = urlsplit(source["url"])
        host = "www.wikidata.org" if kind == "wikidata" else source["language"] + ".wikipedia.org"
        if (url.scheme != "https" or url.hostname != host or url.port is not None
                or url.username is not None or url.password is not None
                or url.path != "/w/index.php" or url.query != "oldid=" + str(revision)
                or url.fragment):
            raise ValueError("Source " + reference + " URL does not bind its pinned revision")
        if kind == "wikidata" and not re.fullmatch(r"Q[1-9][0-9]*", source["source_qid"]):
            raise ValueError("Source " + reference + " has invalid Wikidata subject")
    for _, field, _ in fields(record):
        for candidate in field["candidates"]:
            for evidence in candidate["evidence"]:
                if not evidence["locator"].strip():
                    raise ValueError("Empty evidence locator")




def no_legacy_duplicate(repo, base, entity_id):
    import hashlib
    old='data/universities/'+hashlib.sha256(entity_id.encode()).hexdigest()[:3]+'/'+entity_id+'.json'
    if blob(repo,base,old,optional=True) is not None:
        raise ValueError('Unsupported three-hex storage; migrate before Research')
