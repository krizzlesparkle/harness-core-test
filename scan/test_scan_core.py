import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCAN = Path(__file__).with_name("scan_core.py")


def run(content, name="f.md"):
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / name).write_text(content, encoding="utf-8")
        r = subprocess.run([sys.executable, "-I", str(SCAN), d], capture_output=True, text=True)
        return r.returncode, r.stdout


class ScanTests(unittest.TestCase):
    def test_clean(self):
        self.assertEqual(run("Run postflight before you stop.\n")[0], 0)

    def test_blocks_each_class(self):
        cases = {
            "lhp-name": "see the LHP plugin",
            "itsm-key": "tracked in ITSM-220",
            "keeper-pointer": "keeper://abc/field/password",
            "atlassian-site": "https://x.atlassian.net/browse/A-1",
            "work-system": "export from Workday",
            "work-identity": "ryan.kreigh@example.com",
            "gh-token": "t = ghp_" + "a" * 24,
            "aws-key": "AKIA" + "A" * 16,
            "private-key": "-----BEGIN RSA PRIVATE KEY-----",
            "secret-assign": "api_key = abcdef1234567890xyz",
        }
        for name, text in cases.items():
            code, out = run(text + "\n")
            self.assertEqual(code, 1, name)
            self.assertIn(name, out)

    def test_binary_is_unread_not_clean(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "b.bin").write_bytes(b"\x00\x01\x02")
            r = subprocess.run([sys.executable, "-I", str(SCAN), d], capture_output=True, text=True)
            self.assertEqual(r.returncode, 2)

    def test_missing_path_is_not_clean(self):
        r = subprocess.run([sys.executable, "-I", str(SCAN), "no/such/path"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
