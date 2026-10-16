#!/usr/bin/env python3
"""Reconcile a harness repo with an upstream core. Standard library only.

A harness has harness.manifest.json:
  {"side": "work",
   "upstreams": [{"name": "core", "dir": "../harness-core", "subdir": "core",
                  "local": "core", "push": "patch-only"}],
   "tags": {"core/**": "core", "work/**": "work"}}

  upstream dir    where the upstream checkout is (relative to the harness root)
  subdir          the folder inside the upstream that holds shareable files
  local           the folder inside this harness that mirrors it
  push            "never", "patch-only" (a patch file, nothing written upstream) or "direct"

Commands (run from the harness root):
  status [--upstream NAME]
  pull FILE... [--force]            upstream -> harness; refuses a file changed here unless --force
  promote FILE... [--out DIR] [--apply]
                                    harness -> upstream; scan gate first; patch file unless --apply and push=direct

State: .reconcile-base.json records each file's hash at the last sync, so a change is told apart as
"changed here", "changed upstream" or "both" (a conflict). Exit 0 ok, 1 refused or conflict, 2 bad input.
"""
import argparse
import difflib
import fnmatch
import hashlib
import json
import subprocess
import sys
from pathlib import Path

BASE_FILE = ".reconcile-base.json"
SCAN = Path(__file__).resolve().parent.parent / "scan" / "scan_core.py"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def files(root):
    if not root.is_dir():
        return {}
    return {f.relative_to(root).as_posix(): f for f in sorted(root.rglob("*"))
            if f.is_file() and ".git" not in f.parts}


def load_manifest(root):
    p = root / "harness.manifest.json"
    if not p.is_file():
        sys.exit("no harness.manifest.json in " + str(root))
    return json.loads(p.read_text(encoding="utf-8"))


def pick_upstream(m, name):
    ups = m.get("upstreams") or []
    for u in ups:
        if name in (None, u["name"]):
            return u
    sys.exit("no such upstream: %s" % name)


def tag_of(m, rel):
    for pat, tag in (m.get("tags") or {}).items():
        if fnmatch.fnmatch(rel, pat):
            return tag
    return None


def classify(root, u, base):
    here = files(root / u["local"])
    up = files((root / u["dir"]).resolve() / u["subdir"])
    out = {}
    for rel in sorted(set(here) | set(up)):
        h = sha(here[rel]) if rel in here else None
        r = sha(up[rel]) if rel in up else None
        b = base.get(u["name"], {}).get(rel)
        if h == r:
            state = "same"
        elif rel not in up:
            state = "only-here"
        elif rel not in here:
            state = "only-upstream"
        elif b is None:
            state = "differs-no-base"
        elif h == b:
            state = "changed-upstream"
        elif r == b:
            state = "changed-here"
        else:
            state = "both-changed"
        out[rel] = state
    return out


def load_base(root):
    p = root / BASE_FILE
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def save_base(root, base):
    (root / BASE_FILE).write_text(json.dumps(base, indent=1, sort_keys=True), encoding="utf-8")


def cmd_status(root, m, a):
    u = pick_upstream(m, a.upstream)
    st = classify(root, u, load_base(root))
    for rel, s in st.items():
        if s != "same":
            print("%-17s %s" % (s, rel))
    print("%d files, %d differ" % (len(st), sum(1 for s in st.values() if s != "same")))
    return 0


def cmd_pull(root, m, a):
    u = pick_upstream(m, a.upstream)
    base = load_base(root)
    st = classify(root, u, base)
    up_root = (root / u["dir"]).resolve() / u["subdir"]
    code = 0
    for rel in a.files:
        s = st.get(rel)
        if s is None or s in ("same", "only-here", "changed-here"):
            print("skip %s (%s; nothing newer upstream)" % (rel, s or "unknown"))
            continue
        if s in ("both-changed", "differs-no-base") and not a.force:
            print("REFUSED %s (%s); use --force to overwrite the harness copy" % (rel, s))
            code = 1
            continue
        dest = root / u["local"] / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((up_root / rel).read_bytes())
        base.setdefault(u["name"], {})[rel] = sha(dest)
        print("pulled %s" % rel)
    save_base(root, base)
    return code


def cmd_promote(root, m, a):
    u = pick_upstream(m, a.upstream)
    if u.get("push", "never") == "never":
        print("REFUSED: upstream %s does not accept changes from this harness" % u["name"])
        return 1
    base = load_base(root)
    st = classify(root, u, base)
    up_root = (root / u["dir"]).resolve() / u["subdir"]
    chosen, code = [], 0
    for rel in a.files:
        s = st.get(rel)
        local = root / u["local"] / rel
        if s is None or not local.is_file():
            print("REFUSED %s (not a file in %s)" % (rel, u["local"]))
            code = 1
        elif tag_of(m, u["local"] + "/" + rel) != "core":
            print("REFUSED %s (not tagged core in the manifest)" % rel)
            code = 1
        elif s == "same":
            print("skip %s (already the same)" % rel)
        elif s in ("changed-upstream", "both-changed"):
            print("REFUSED %s (%s): pull and merge first" % (rel, s))
            code = 1
        else:
            chosen.append(rel)
    if not chosen:
        return code
    r = subprocess.run([sys.executable, "-I", str(SCAN)] + [str(root / u["local"] / c) for c in chosen],
                       capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    if r.returncode != 0:
        print("REFUSED: scan gate exit %d; nothing promoted" % r.returncode)
        return 1
    out = Path(a.out or root)
    out.mkdir(parents=True, exist_ok=True)
    patch = []
    for rel in chosen:
        old = (up_root / rel).read_text(encoding="utf-8").splitlines(True) if (up_root / rel).is_file() else []
        new = (root / u["local"] / rel).read_text(encoding="utf-8").splitlines(True)
        patch += difflib.unified_diff(old, new, "a/%s/%s" % (u["subdir"], rel), "b/%s/%s" % (u["subdir"], rel))
    pf = out / ("promote-%s.patch" % u["name"])
    pf.write_text("".join(patch), encoding="utf-8")
    print("patch written: %s (%d files)" % (pf, len(chosen)))
    if a.apply:
        if u.get("push") != "direct":
            print("REFUSED --apply: upstream push policy is %s" % u.get("push"))
            return 1
        for rel in chosen:
            d = up_root / rel
            d.parent.mkdir(parents=True, exist_ok=True)
            d.write_bytes((root / u["local"] / rel).read_bytes())
            base.setdefault(u["name"], {})[rel] = sha(d)
        save_base(root, base)
        print("applied to upstream working tree")
    return code


def main(argv):
    ap = argparse.ArgumentParser(prog="reconcile")
    ap.add_argument("--root", default=".")
    ap.add_argument("--upstream")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    p = sub.add_parser("pull"); p.add_argument("files", nargs="+"); p.add_argument("--force", action="store_true")
    q = sub.add_parser("promote"); q.add_argument("files", nargs="+"); q.add_argument("--out"); q.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    root = Path(a.root).resolve()
    m = load_manifest(root)
    return {"status": cmd_status, "pull": cmd_pull, "promote": cmd_promote}[a.cmd](root, m, a)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
