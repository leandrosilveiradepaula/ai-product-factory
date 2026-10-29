import unittest
from unittest.mock import MagicMock

from ai_product_factory.candidate_source_evidence import (
    _latest_scope, _request_paths, collect_candidate_source_evidence,
)


SHA = "a" * 40


class CandidateSourceEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tick = chr(96)
        self.doc = (
            "## Authorized task (2026-10-01): old work\n"
            + self.tick + "src/legacy.py" + self.tick + "\n"
            + "## Additional authorized task (2026-10-10): pipeline integrity\n"
            + "Only " + self.tick + "src/services/SettingsService.ts" + self.tick
            + ", " + self.tick + "src/services/SettingsService.stage-integrity.test.ts"
            + self.tick + " and " + self.tick + "src/missing.ts" + self.tick + ".\n"
            + "## External gate\n"
            + self.tick + "src/secret.py" + self.tick + "\n"
        )
        self.github = MagicMock()
        self.github.list_file_paths.return_value = (
            "src/legacy.py", "src/services/SettingsService.ts",
            "src/services/SettingsService.stage-integrity.test.ts",
        )
        self.github.get_file_text.side_effect = lambda path, ref: (
            "export function verified() { return true; }\n" if path.endswith(".ts")
            else "test('code', () => true)\n"
        )

    def test_select_only_latest_authorized_scope(self):
        heading, paths = _latest_scope(self.doc)
        self.assertIn("2026-10-10", heading)
        self.assertEqual(paths, [
            "src/services/SettingsService.ts",
            "src/services/SettingsService.stage-integrity.test.ts",
            "src/missing.ts",
        ])
        result = collect_candidate_source_evidence(self.doc, self.github, sha=SHA)
        self.assertEqual(result["assessed_commit"], SHA)
        self.assertEqual(result["missing_paths"], ["src/missing.ts"])
        self.assertEqual(len(result["inspected_files"]), 2)
        self.assertTrue(all(row["assessed_commit"] == SHA for row in result["inspected_files"]))
        self.github.list_file_paths.assert_called_once_with(ref=SHA)
        self.github.get_file_text.assert_any_call(
            "src/services/SettingsService.ts", ref=SHA
        )
        self.assertNotIn("src/legacy.py", [
            call.args[0] for call in self.github.get_file_text.call_args_list
        ])

    def test_refuses_path_traversal_and_sensitive_extensions(self):
        t = self.tick
        doc = ("## Authorized task (2026-10-10): guarded\n"
               + t + "src/../credentials.py" + t + " "
               + t + ".env" + t + " "
               + t + "src/app/actions.ts" + t)
        heading, paths = _latest_scope(doc)
        self.assertEqual(paths, ["src/app/actions.ts"])
        self.assertIn("guarded", heading)

    def test_no_source_scope_never_calls_github(self):
        result = collect_candidate_source_evidence(
            "# CURRENT_TASK\nNo code paths permitted.", self.github, sha=SHA
        )
        self.assertEqual(result["status"], "no_scoped_source_paths")
        self.github.list_file_paths.assert_not_called()
        self.github.get_file_text.assert_not_called()

    def test_truncation_is_truthful_and_bound(self):
        self.github.get_file_text.side_effect = lambda path, ref: "a" * 50000
        result = collect_candidate_source_evidence(self.doc, self.github, sha=SHA)
        self.assertFalse(result["inspected_files"][0]["complete"])
        self.assertLess(len(result["inspected_files"][0]["content"]), 14500)
        self.assertIn("OMITTED MIDDLE", result["inspected_files"][0]["content"])

    def test_sensitive_source_blocks_before_model_context(self):
        self.github.get_file_text.side_effect = lambda path, ref: (
            "sk-proj-abcdefghijklmnopqrstuv0123456"
        )
        with self.assertRaisesRegex(PermissionError, "secret material"):
            collect_candidate_source_evidence(self.doc, self.github, sha=SHA)

    def test_current_request_paths_take_precedence_without_granting_write_scope(self):
        request = ("CRM defect src/components/automations/AutomationBuilder.tsx "
                   "and src/services/automationRuntimeCore.ts; not src/../secret.py")
        self.github.list_file_paths.return_value = (
            "src/components/automations/AutomationBuilder.tsx",
            "src/services/automationRuntimeCore.ts",
            "src/services/SettingsService.ts",
        )
        result = collect_candidate_source_evidence(
            self.doc, self.github, sha=SHA, continuation_request=request
        )
        self.assertEqual([x["path"] for x in result["inspected_files"][:2]], [
            "src/components/automations/AutomationBuilder.tsx",
            "src/services/automationRuntimeCore.ts",
        ])
        self.assertEqual(result["governance_scope_paths"][0], "src/services/SettingsService.ts")
        self.assertEqual(result["assessed_commit"], SHA)
        self.assertNotIn("src/../secret.py", _request_paths(request))

    def test_invalid_ref_fails_before_git_access(self):
        with self.assertRaises(PermissionError):
            collect_candidate_source_evidence(self.doc, self.github, sha="main")
        self.github.list_file_paths.assert_not_called()



    def test_latest_portuguese_authorization_overrides_older_english_task(self):
        tick = chr(96)
        current_paths = [
            "src/components/RuleEditor.tsx",
            "src/lib/rule-input.ts",
            "src/lib/rule-input.test.ts",
            "src/components/RuleEditor.test.tsx",
        ]
        doc = (
            "## Additional authorized task (2026-10-10): completed old work\n"
            + tick + "src/services/LegacyService.ts" + tick + "\n"
            + "## Tarefa autorizada (2026-10-19): condições em produto existente\n"
            + "### Arquivos de escrita permitidos\n"
            + "\n".join("- " + tick + path + tick for path in current_paths)
        )
        heading, paths = _latest_scope(doc)
        self.assertIn("2026-10-19", heading)
        self.assertEqual(paths, current_paths)
        self.github.list_file_paths.return_value = tuple(current_paths + ["src/services/LegacyService.ts"])
        self.github.get_file_text.side_effect = lambda path, ref: "export const implemented = true;\n"
        receipt = collect_candidate_source_evidence(doc, self.github, sha=SHA)
        self.assertEqual(receipt["scope_heading"], heading)
        self.assertEqual(receipt["governance_scope_paths"], current_paths)
        self.assertEqual([row["path"] for row in receipt["inspected_files"]], current_paths)
        self.assertEqual(receipt["omitted_paths"], [])
        self.assertEqual(receipt["missing_paths"], [])
        self.assertTrue(all(row["complete"] for row in receipt["inspected_files"]))
        self.assertNotIn("src/services/LegacyService.ts", [
            call.args[0] for call in self.github.get_file_text.call_args_list
        ])

    def test_latest_portuguese_scope_without_code_must_not_reopen_old_task(self):
        tick = chr(96)
        doc = (
            "## Authorized task (2026-10-10): old\n"
            + tick + "src/services/LegacyService.ts" + tick + "\n"
            + "## Tarefa autorizada (2026-10-19): somente documentação\n"
            + "Arquivo " + tick + "docs/codex/CURRENT_TASK.md" + tick + " e nenhum código.\n"
        )
        heading, paths = _latest_scope(doc)
        self.assertIn("2026-10-19", heading)
        self.assertEqual(paths, [])
        receipt = collect_candidate_source_evidence(doc, self.github, sha=SHA)
        self.assertEqual(receipt["status"], "no_scoped_source_paths")
        self.github.list_file_paths.assert_not_called()
        self.github.get_file_text.assert_not_called()

    def test_four_file_budget_keeps_small_tests_and_honestly_omits_fifth(self):
        tick = chr(96)
        files = [
            "src/components/RuleEditor.tsx",
            "src/lib/rule-input.ts",
            "src/lib/rule-input.test.ts",
            "src/components/RuleEditor.test.tsx",
            "src/lib/scope-outside-budget.ts",
        ]
        doc = ("## Tarefa autorizada (2026-10-19): desenvolvimento autorizado\n"
               + "\n".join("- " + tick + path + tick for path in files))
        samples = {
            files[0]: "A" * 38000,
            files[1]: "B" * 7000,
            files[2]: "C" * 2200,
            files[3]: "D" * 1500,
            files[4]: "E" * 120,
        }
        self.github.list_file_paths.return_value = tuple(files)
        self.github.get_file_text.side_effect = lambda path, ref: samples[path]
        receipt = collect_candidate_source_evidence(doc, self.github, sha=SHA)
        self.assertEqual([row["path"] for row in receipt["inspected_files"]], files[:4])
        self.assertEqual(receipt["omitted_paths"], [files[4]])
        self.assertEqual(receipt["missing_paths"], [])
        self.assertLessEqual(sum(len(row["content"].encode("utf-8"))
                                 for row in receipt["inspected_files"]), 24000)
        self.assertTrue(all(len(row["content"].encode("utf-8")) <= 14000
                            for row in receipt["inspected_files"]))
        self.assertFalse(receipt["inspected_files"][0]["complete"])
        self.assertIn("OMITTED MIDDLE", receipt["inspected_files"][0]["content"])
        self.assertTrue(receipt["inspected_files"][2]["complete"])
        self.assertTrue(receipt["inspected_files"][3]["complete"])
        self.assertNotIn(files[4], [
            call.args[0] for call in self.github.get_file_text.call_args_list
        ])

    def test_portuguese_scope_rejects_unsafe_paths(self):
        tick = chr(96)
        doc = ("## Tarefa autorizada (2026-10-19): escopo\n"
               + tick + "src/../private.py" + tick + " "
               + tick + ".env" + tick + " "
               + tick + "src/lib/safe.ts" + tick)
        heading, paths = _latest_scope(doc)
        self.assertIn("Tarefa autorizada", heading)
        self.assertEqual(paths, ["src/lib/safe.ts"])

    def test_explicit_current_issue_mismatch_is_proven_without_model(self):
        from ai_product_factory.candidate_source_evidence import (
            source_issue_scope_alignment, latest_authorization_excerpt,
        )
        doc = (
            "## Authorized task (2026-10-10): historical\n"
            "Origem: CRM issue #24\n"
            "## Tarefa autorizada (2026-10-19): automações\n"
            "Origem: demanda autorizada do piloto, CRM issue #33.\n"
            + self.tick + "src/lib/current.ts" + self.tick + "\n"
        )
        request = "Reconciliar a issue CRM #24 e implementar correções justificadas."
        self.assertEqual(source_issue_scope_alignment(doc, request), {
            "status": "conflict", "requested_issue": 24, "authorized_issue": 33,
        })
        excerpt = latest_authorization_excerpt(doc)
        self.assertNotIn("historical", excerpt)
        self.assertIn("2026-10-19", excerpt)
        self.assertEqual(source_issue_scope_alignment(doc, "Reconciliar CRM issue #33.")["status"], "matched")

    def test_ambiguous_and_different_namespace_issue_refs_are_not_conflicts(self):
        from ai_product_factory.candidate_source_evidence import source_issue_scope_alignment
        doc = "## Tarefa autorizada (2026-10-19)\nOrigem: CRM issue #33\n"
        for request in (
            "Auditar a Factory issue #24.",
            "Auditar CRM issue #24 e CRM issue #33.",
            "Auditar tema sem issue numerada.",
            "Auditar a issue #24.",
        ):
            with self.subTest(request=request):
                self.assertEqual(source_issue_scope_alignment(doc, request)["status"], "unverified")
        self.assertEqual(source_issue_scope_alignment(doc, "Auditar CRM issue #24.")["status"], "conflict")

    def test_mismatched_scope_receipt_does_not_grant_writes(self):
        doc = (
            "## Tarefa autorizada (2026-10-19): escopo atual\n"
            "Origem: CRM issue #33\n"
            + self.tick + "src/lib/current.ts" + self.tick
        )
        self.github.list_file_paths.return_value = ("src/lib/current.ts",)
        receipt = collect_candidate_source_evidence(
            doc, self.github, sha=SHA, continuation_request="Implementar CRM issue #24",
        )
        self.assertEqual(receipt["issue_scope_alignment"]["status"], "conflict")
        self.assertEqual(receipt["governance_scope_paths"], ["src/lib/current.ts"])
        self.assertEqual(receipt["assessed_commit"], SHA)

    def test_issue_urls_in_active_governance_block_new_owner_scope_pre_model(self):
        from ai_product_factory.candidate_source_evidence import source_issue_scope_alignment
        doc = (
            "## Tarefa autorizada (24/10/2026) — Service Desk\n"
            "Issue funcional: https://github.com/leandrosilveiradepaula/crm-infodive/issues/194\n"
            "Escopo técnico: https://github.com/leandrosilveiradepaula/crm-infodive/issues/194#issuecomment-6390960882\n"
            "### Escopo máximo de escrita\n"
            "`src/components/layout/Sidebar.tsx`\n"
        )
        repo = "leandrosilveiradepaula/crm-infodive"
        observed = source_issue_scope_alignment(
            doc, "Concluir as pendências reais da issue #22 do CRM Infodive.",
            repository=repo,
        )
        self.assertEqual(observed, {
            "status": "conflict", "requested_issue": 22, "authorized_issue": 194,
        })
        self.assertEqual(source_issue_scope_alignment(
            doc, "Concluir a issue CRM #194", repository=repo,
        )["status"], "matched")
        self.assertEqual(source_issue_scope_alignment(
            doc, "Concluir https://github.com/leandrosilveiradepaula/crm-infodive/issues/194",
            repository=repo,
        )["status"], "matched")
        # An issue of another repo is never treated as permission for this CRM.
        self.assertEqual(source_issue_scope_alignment(
            doc, "Auditar https://github.com/other/repo/issues/194",
            repository=repo,
        )["status"], "unverified")

    def test_mixed_urls_cannot_become_one_authorization(self):
        from ai_product_factory.candidate_source_evidence import source_issue_scope_alignment
        doc = (
            "## Tarefa autorizada (2026-10-29)\n"
            "https://github.com/leandrosilveiradepaula/crm-infodive/issues/194\n"
            "https://github.com/leandrosilveiradepaula/crm-infodive/issues/195\n"
        )
        self.assertEqual(source_issue_scope_alignment(
            doc, "Concluir issue #22", repository="leandrosilveiradepaula/crm-infodive",
        )["status"], "unverified")

if __name__ == "__main__":
    unittest.main()
