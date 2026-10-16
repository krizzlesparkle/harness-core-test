import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).with_name("reconcile.py")


def run(root, *args):
    r = subprocess.run([sys.executable, "-I", str(TOOL), "--root", str(root), *args], capture_output=True, text=True)
    return r.returncode, r.stdout


def make(tmp, push="patch-only"):
    up = Path(tmp) / "up"
    h = Path(tmp) / "h"
    (up / "core").mkdir(parents=True)
    (h / "core").mkdir(parents=True)
    (h / "work").mkdir()
    (h / "harness.manifest.json").write_text(json.dumps({
        "side": "work",
        "upstreams": [{"name": "core", "dir": "../up", "subdir": "core", "local": "core", "push": push}],
        "tags": {"core/**": "core", "work/**": "work"}}), encoding="utf-8")
    return up, h


class ReconcileTests(unittest.TestCase):
    def test_pull_new_file_then_same(self):
        with tempfile.TemporaryDirectory() as t:
            up, h = make(t)
            (up / "core" / "a.md").write_text("one\n")
            self.assertIn("only-upstream", run(h, "status")[1])
            self.assertEqual(run(h, "pull", "a.md")[0], 0)
            self.assertEqual((h / "core" / "a.md").read_text(), "one\n")
            self.assertIn("0 differ", run(h, "status")[1])

    def test_changed_here_blocks_pull_and_both_changed_is_conflict(self):
        with tempfile.TemporaryDirectory() as t:
            up, h = make(t)
            (up / "core" / "a.md").write_text("one\n")
            run(h, "pull", "a.md")
            (h / "core" / "a.md").write_text("here\n")
            self.assertIn("changed-here", run(h, "status")[1])
            self.assertEqual(run(h, "pull", "a.md")[0], 0)  # upstream unchanged: nothing to pull, skipped
            (up / "core" / "a.md").write_text("up\n")
            self.assertIn("both-changed", run(h, "status")[1])
            code, out = run(h, "pull", "a.md")
            self.assertEqual(code, 1)
            self.assertIn("REFUSED", out)
            self.assertEqual((h / "core" / "a.md").read_text(), "here\n")

    def test_promote_writes_patch_not_upstream(self):
        with tempfile.TemporaryDirectory() as t:
            up, h = make(t)
            (up / "core" / "a.md").write_text("one\n")
            run(h, "pull", "a.md")
            (h / "core" / "a.md").write_text("one\ntwo\n")
            code, out = run(h, "promote", "a.md", "--out", str(Path(t) / "out"))
            self.assertEqual(code, 0, out)
            self.assertTrue((Path(t) / "out" / "promote-core.patch").is_file())
            self.assertEqual((up / "core" / "a.md").read_text(), "one\n")

    def test_promote_blocked_by_scan(self):
        with tempfile.TemporaryDirectory() as t:
            up, h = make(t)
            (h / "core" / "b.md").write_text("tracked in " + "ITSM" + "-220\n")
            code, out = run(h, "promote", "b.md", "--out", str(Path(t) / "out"))
            self.assertEqual(code, 1)
            self.assertIn("scan gate", out)
            self.assertFalse((Path(t) / "out" / "promote-core.patch").exists())

    def test_promote_refuses_untagged_and_never_policy(self):
        with tempfile.TemporaryDirectory() as t:
            up, h = make(t)
            (h / "work" / "w.md").write_text("x\n")
            self.assertEqual(run(h, "promote", "w.md")[0], 1)
        with tempfile.TemporaryDirectory() as t:
            up, h = make(t, push="never")
            (h / "core" / "c.md").write_text("x\n")
            code, out = run(h, "promote", "c.md")
            self.assertEqual(code, 1)
            self.assertIn("does not accept", out)

    def test_apply_needs_direct_policy(self):
        with tempfile.TemporaryDirectory() as t:
            up, h = make(t, push="patch-only")
            (h / "core" / "c.md").write_text("fine\n")
            self.assertEqual(run(h, "promote", "c.md", "--apply", "--out", str(Path(t) / "o"))[0], 1)
            self.assertFalse((up / "core" / "c.md").exists())
        with tempfile.TemporaryDirectory() as t:
            up, h = make(t, push="direct")
            (h / "core" / "c.md").write_text("fine\n")
            self.assertEqual(run(h, "promote", "c.md", "--apply", "--out", str(Path(t) / "o"))[0], 0)
            self.assertEqual((up / "core" / "c.md").read_text(), "fine\n")


if __name__ == "__main__":
    unittest.main()
