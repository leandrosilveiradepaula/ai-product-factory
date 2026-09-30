import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"
ACTION_DIR = ROOT / ".github" / "actions"
USES_RE = re.compile(r"^\s*(?:-\s*)?uses:\s*([^\s#]+)", re.MULTILINE)
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class GitHubActionsPinningTests(unittest.TestCase):
    def test_external_actions_are_pinned_to_full_commit_sha(self):
        files = sorted(WORKFLOW_DIR.glob("*.yml")) + sorted(WORKFLOW_DIR.glob("*.yaml"))
        if ACTION_DIR.exists():
            files += sorted(ACTION_DIR.rglob("action.yml"))
            files += sorted(ACTION_DIR.rglob("action.yaml"))

        violations = []
        for path in files:
            text = path.read_text(encoding="utf-8")
            for target in USES_RE.findall(text):
                if target.startswith("./") or target.startswith("docker://"):
                    continue
                if "@" not in target:
                    violations.append(f"{path.relative_to(ROOT)}: {target} has no ref")
                    continue
                action, ref = target.rsplit("@", 1)
                if not action or not FULL_SHA_RE.fullmatch(ref):
                    violations.append(
                        f"{path.relative_to(ROOT)}: {target} must use a full 40-character commit SHA"
                    )

        self.assertEqual([], violations, "\n".join(violations))


if __name__ == "__main__":
    unittest.main()
