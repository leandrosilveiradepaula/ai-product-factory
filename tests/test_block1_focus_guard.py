"""B1-B4 scope-gate adversarial tests: no network, models, or writes."""
import unittest

from scripts.check_block1_focus import FocusDenied, REPOSITORY, verify, ALL_CRITERIA

BASE = "a" * 40
HEAD = "b" * 40
BODY = "\n".join([
    "Factory-Block: B2, B3",
    "Factory-Criteria: functional_completeness/mock_noop_demo_inventory, product_experience/states",
    "Factory-Intent: advance",
    "Factory-Acceptance: Supabase independent evidence persisted for exact main SHA; protect the ten prior PASS criteria.",
    "Factory-Scope: " + REPOSITORY,
    "Factory-Cross-Repo: read-only",
    "Factory-Human-Gates: human-review for protected paths; no automatic merge",
])


def event(body=BODY, action="opened", head=HEAD):
    return {
        "action": action,
        "pull_request": {
            "number": 1329, "body": body,
            "base": {"sha": BASE, "ref": "main",
                     "repo": {"full_name": REPOSITORY}},
            "head": {"sha": head, "repo": {"full_name": REPOSITORY}},
        },
    }


def check(body=BODY, files=None, ev=None, base=BASE, head=HEAD, repository=REPOSITORY):
    return verify(event(body) if ev is None else ev, repository, base, head,
                  ["src/ai_product_factory/runtime_cli.py"] if files is None else files)


class Block1FocusGate(unittest.TestCase):
    def assert_denied(self, **kwargs):
        with self.assertRaises(FocusDenied):
            check(**kwargs)

    def test_all_19_are_exactly_bound_to_four_blocks(self):
        self.assertEqual(len(ALL_CRITERIA), 19)
        result = check()
        self.assertEqual(result["blocks"], ["B2", "B3"])
        self.assertEqual(len(result["criteria"]), 2)
        self.assertFalse(result["certification_pass_claimed"])
        self.assertFalse(result["production_release_authorized"])
        self.assertFalse(result["cross_repo_writes_authorized"])

    def test_missing_duplicate_unknown_metadata_rejected(self):
        self.assert_denied(body="Please improve CRM")
        self.assert_denied(body=BODY.replace("Factory-Criteria:", "Other-Criteria:"))
        self.assert_denied(body=BODY + "\nFactory-Block: B4")
        self.assert_denied(body=BODY.replace("product_experience/states", "fake/states"))
        self.assert_denied(body=BODY.replace("B2, B3", "B2"))

    def test_cross_repo_and_unbounded_scope_rejected(self):
        self.assert_denied(repository="leandrosilveiradepaula/crm-infodive")
        self.assert_denied(body=BODY.replace("Factory-Cross-Repo: read-only",
                                           "Factory-Cross-Repo: write"))
        self.assert_denied(body=BODY.replace("Factory-Scope: " + REPOSITORY,
                                           "Factory-Scope: all repositories"))
        changed = event()
        changed["pull_request"]["head"]["repo"]["full_name"] = "other/crm"
        self.assert_denied(ev=changed)

    def test_bad_paths_rejected(self):
        for files in ([], ["../crm-infodive/foo.py"], ["/etc/passwd"],
                      ["unrelated_project/main.py"], ["src/runtime_cli.py"] * 2,
                      ["src/../malicious/file.py"], [".github/workflows/x.yml\nbad"]):
            with self.subTest(files=files):
                self.assert_denied(files=files)

    def test_sha_and_target_branch_are_real(self):
        self.assert_denied(head="wrong")
        self.assert_denied(base=HEAD)
        self.assert_denied(ev=event(head="c"*40))
        changed = event()
        changed["pull_request"]["base"]["ref"] = "preview/candidate"
        self.assert_denied(ev=changed)
        changed = event()
        changed["pull_request"]["base"]["sha"] = "c"*40
        self.assert_denied(ev=changed)

    def test_no_documentation_only_false_progress(self):
        self.assert_denied(files=["docs/marketing.md"])
        self.assert_denied(body=BODY.replace("Supabase independent evidence persisted for exact main SHA",
                                             "CI passing on GitHub only"))

    def test_intent_must_be_advance_or_authenticated_regression(self):
        self.assert_denied(body=BODY.replace("Factory-Intent: advance",
                                             "Factory-Intent: miscellaneous"))
        repair = BODY.replace("Factory-Intent: advance", "Factory-Intent: repair-regression")
        self.assert_denied(body=repair)
        repair += ("\nFactory-Incident: https://github.com/"
                   + REPOSITORY + "/issues/713")
        self.assertEqual(check(body=repair)["blocks"], ["B2", "B3"])
        self.assert_denied(body=repair.replace("/issues/713", "/pull/713"))

    def test_sensitive_files_need_human_gate_declaration(self):
        without = BODY.replace("Factory-Human-Gates: human-review for protected paths; no automatic merge", "")
        for path in ("apps/console/app/page.tsx", ".github/workflows/validate.yml",
                     "supabase/migrations/20990101.sql",
                     "supabase/functions/factory-runtime-control-plane/index.ts"):
            with self.subTest(path=path):
                self.assert_denied(body=without, files=[path])
                self.assertFalse(check(files=[path])["production_release_authorized"])

    def test_fail_closed_on_forks_and_changed_event(self):
        self.assert_denied(ev=event(action="unknown"))
        changed = event()
        changed["pull_request"]["number"] = True
        self.assert_denied(ev=changed)
        self.assert_denied(ev={"action": "opened"})

    def test_no_external_entrypoint_self_authorizes(self):
        receipt = check(files=["scripts/check_block1_focus.py", "tests/test_block1_focus_guard.py"])
        self.assertEqual(receipt["changed_files"], 2)
        self.assertFalse(receipt["certification_pass_claimed"])


if __name__ == "__main__":
    unittest.main()
