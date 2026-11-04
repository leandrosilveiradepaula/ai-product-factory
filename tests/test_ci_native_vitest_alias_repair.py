from __future__ import annotations

import unittest
from dataclasses import dataclass

from ai_product_factory.ci_native_vitest_alias_repair import (
    verified_native_vitest_alias_patch,
)

SHA = "a" * 40
REPO = "owner/crm"
URL = f"https://github.com/{REPO}/actions/runs/41764182167/job/126358570861"
ALIAS = "@/services/ContractService"
TEST = "test/contract-access.test.ts"
SOURCE = "src/services/ContractService.ts"
TSCONFIG = '{"compilerOptions":{"paths":{"@/*":["./src/*"]}}}'
PACKAGE = '{"scripts":{"test":"vitest run"},"devDependencies":{"vitest":"^3.2.4"}}'
FILE = (
    "import { describe, vi } from 'vitest';\n"
    "vi.mock('@/lib/supabase/admin', () => ({}));\n"
    "import { ContractService } from '@/services/ContractService';\n"
)
LOG = (
    "2026-11-04T02:59:49Z FAIL test/contract-access.test.ts\n"
    "2026-11-04T02:59:49Z ##[error]Error: Cannot find package "
    "'@/services/ContractService' imported from "
    "'/home/runner/work/crm-infodive/crm-infodive/test/contract-access.test.ts'\n"
)


@dataclass
class Failure:
    name: str = "native-ci/tests"
    conclusion: str = "failure"
    failure_class: str = "code"
    details_url: str = URL


class GitHub:
    def __init__(self):
        self.paths = [
            TEST, SOURCE, "tsconfig.json", "package.json",
            "src/lib/supabase/admin.ts",
        ]
        self.files = {
            TEST: FILE, SOURCE: "export class ContractService {}",
            "tsconfig.json": TSCONFIG, "package.json": PACKAGE,
        }
        self.log = LOG
        self.failures = (Failure(),)
        self.requested_sha = None
        self.log_job = None

    def get_failed_checks(self, pr_number, *, expected_head_sha):
        assert pr_number == 212
        self.requested_sha = expected_head_sha
        return self.failures

    def list_file_paths(self, *, ref):
        assert ref == SHA
        return self.paths

    def get_file_text(self, path, *, ref):
        assert ref == SHA
        return self.files[path]

    def native_log_reader(self, job_id):
        self.log_job = job_id
        return self.log


def source():
    return {
        "repair": {
            "repair_kind": "ci",
            "candidate_commit": SHA,
            "repair_request_id": "c10117af-1111-4111-8111-111111111111",
            "pr_number": 212,
            "failures": [
                {
                    "name": "native-ci/tests",
                    "conclusion": "failure",
                    "failure_class": "code",
                    "details_url": URL,
                }
            ],
        },
        "ci_repair_evidence": {
            "kind": "verified_native_ci_repair_candidate",
            "repository": REPO,
            "candidate_commit": SHA,
            "repair_request_id": "c10117af-1111-4111-8111-111111111111",
            "pr_number": 212,
        },
    }


def run(gh=None, src=None, scopes=(TEST,), commit=SHA):
    return verified_native_vitest_alias_patch(
        github=gh if gh is not None else GitHub(),
        source=src if src is not None else source(),
        base_commit=commit,
        repository=REPO,
        write_scopes=scopes,
    )


class NativeVitestAliasRepairTests(unittest.TestCase):
    def test_real_shaped_log_exact_sha_and_existing_scope_yields_one_test_file(self):
        gh = GitHub()
        patch = run(gh)
        self.assertEqual(set(patch), {TEST})
        self.assertIn("from '../src/services/ContractService'", patch[TEST])
        self.assertIn("vi.mock('@/lib/supabase/admin'", patch[TEST])
        self.assertNotIn("import { ContractService } from '@/services/ContractService'", patch[TEST])
        self.assertEqual(gh.requested_sha, SHA)
        self.assertEqual(gh.log_job, 126358570861)

    def test_no_scope_no_model_no_edit(self):
        gh = GitHub()
        self.assertIsNone(run(gh, scopes=(SOURCE,)))
        self.assertIsNone(run(gh, scopes=()))
        self.assertIsNone(gh.log_job)

    def test_unrelated_failure_or_job_is_not_rewritten(self):
        for failure in (
            Failure(name="native-ci/typescript"),
            Failure(details_url=URL.replace("126358570861", "126358570862")),
            Failure(failure_class="unknown"),
        ):
            with self.subTest(failure=failure):
                gh = GitHub()
                gh.failures = (failure,)
                self.assertIsNone(run(gh))

    def test_no_trusted_job_or_ambiguous_error(self):
        for log in (
            LOG + LOG,
            LOG.replace("##[error]Error:", "Error:"),
            LOG.replace("contract-access.test.ts", "other.test.ts"),
            LOG.replace(ALIAS, "@/services/MissingService"),
            "",
        ):
            with self.subTest(log=log[:80]):
                gh = GitHub()
                gh.log = log
                self.assertIsNone(run(gh))

    def test_alias_config_or_path_mapping_changes_fail_closed(self):
        gh = GitHub()
        gh.paths.append("vitest.config.ts")
        self.assertIsNone(run(gh))
        gh = GitHub()
        gh.files["tsconfig.json"] = '{"compilerOptions":{"paths":{"@/*":["./app/*"]}}}'
        self.assertIsNone(run(gh))
        gh = GitHub()
        gh.files["package.json"] = '{"scripts":{"test":"node test.js"}}'
        self.assertIsNone(run(gh))

    def test_duplicate_or_nonexistent_source_is_not_rewritten(self):
        gh = GitHub()
        gh.paths.remove(SOURCE)
        self.assertIsNone(run(gh))
        gh = GitHub()
        gh.paths.append("src/services/ContractService.tsx")
        self.assertIsNone(run(gh))

    def test_missing_or_duplicate_test_import_is_not_rewritten(self):
        gh = GitHub()
        gh.files[TEST] = FILE.replace(
            "import { ContractService } from '@/services/ContractService';", ""
        )
        self.assertIsNone(run(gh))
        gh = GitHub()
        gh.files[TEST] = FILE + "import { ContractService } from '@/services/ContractService';\n"
        self.assertIsNone(run(gh))

    def test_forged_candidate_or_request_identity_rejected(self):
        for key, value in (
            ("candidate_commit", "b" * 40),
            ("repository", "owner/other"),
            ("repair_request_id", "00000000-0000-4000-8000-000000000000"),
        ):
            with self.subTest(key=key):
                src = source()
                src["ci_repair_evidence"][key] = value
                with self.assertRaises(PermissionError):
                    run(src=src)
        with self.assertRaises(PermissionError):
            run(commit="b" * 40)

    def test_no_fallback_for_any_unverified_failure_or_wrong_project(self):
        src = source()
        src["repair"]["failures"].append(src["repair"]["failures"][0])
        self.assertIsNone(run(src=src))
        src = source()
        src["ci_repair_evidence"]["kind"] = "nonverified"
        self.assertIsNone(run(src=src))
        gh = GitHub()
        gh.failures = (Failure(), Failure())
        self.assertIsNone(run(gh))


if __name__ == "__main__":
    unittest.main()
