import unittest
from unittest.mock import MagicMock

from ai_product_factory.journey_source_inspection import inspect_journey_source

SHA = "a" * 40


class JourneySourceInspectionTests(unittest.TestCase):
    def setUp(self):
        self.github = MagicMock()
        self.github.list_file_paths.return_value = [
            "src/services/ContractService.ts",
            "src/services/OtherService.ts",
            "test/contract-access.test.ts",
        ]
        self.github.get_file_text.return_value = (
            "export class ContractService { static getContracts() { return []; } }"
        )

    def test_class_method_request_inspects_unique_exact_sha_source(self):
        result = inspect_journey_source(
            self.github, sha=SHA,
            request="Implementar issue #171: corrigir ContractService.getContracts",
        )
        self.assertEqual(result["status"], "bounded_source_inspected")
        self.assertEqual(result["assessed_commit"], SHA)
        self.assertEqual(
            [x["path"] for x in result["inspected_files"]],
            ["src/services/ContractService.ts"],
        )
        self.github.get_file_text.assert_called_once_with(
            "src/services/ContractService.ts", ref=SHA,
        )

    def test_same_issue_method_hint_inspects_frozen_source(self):
        result = inspect_journey_source(
            self.github, sha=SHA, request="Implementar CRM issue #209",
            issue_body="No SHA inicial, ContractService.getContracts(organizationId) usa admin.",
        )
        self.assertEqual(result["status"], "bounded_source_inspected")
        self.assertEqual(result["inspected_files"][0]["path"], "src/services/ContractService.ts")
        self.assertEqual(result["inspected_files"][0]["assessed_commit"], SHA)
        self.github.get_file_text.assert_called_once_with(
            "src/services/ContractService.ts", ref=SHA,
        )

    def test_issue_hint_without_class_does_not_invent_source(self):
        result = inspect_journey_source(
            self.github, sha=SHA, request="Implementar CRM issue #209",
            issue_body="Apenas critérios de tenant e owner sem path e sem método",
        )
        self.assertEqual(result["status"], "no_scoped_source_paths")
        self.github.get_file_text.assert_not_called()

    def test_issue_hint_ambiguous_or_oversized_is_rejected_before_code_read(self):
        with self.assertRaisesRegex(PermissionError, "issue discovery hint invalid"):
            inspect_journey_source(
                self.github, sha=SHA, request="CRM issue #209",
                issue_body="x" * 12001,
            )
        self.github.get_file_text.assert_not_called()
        self.github.list_file_paths.return_value.append("packages/crm/ContractService.ts")
        with self.assertRaisesRegex(PermissionError, "ambiguous"):
            inspect_journey_source(
                self.github, sha=SHA, request="CRM issue #209",
                issue_body="ContractService.getContracts(organizationId)",
            )
        self.github.get_file_text.assert_not_called()

    def test_ambiguous_class_is_fail_closed(self):
        self.github.list_file_paths.return_value.append(
            "packages/crm/ContractService.ts"
        )
        with self.assertRaisesRegex(PermissionError, "ambiguous"):
            inspect_journey_source(
                self.github, sha=SHA, request="ContractService.getContracts"
            )
        self.github.get_file_text.assert_not_called()

    def test_no_inferred_paths_cannot_claim_source_inspection(self):
        result = inspect_journey_source(
            self.github, sha=SHA, request="Implementar issue #171"
        )
        self.assertEqual(result["status"], "no_scoped_source_paths")
        self.assertEqual(result["inspected_files"], [])
        self.github.get_file_text.assert_not_called()

    def test_explicit_paths_are_bounded_and_source_pinned(self):
        result = inspect_journey_source(
            self.github, sha=SHA,
            request="src/services/ContractService.ts test/contract-access.test.ts"
        )
        self.assertEqual(len(result["inspected_files"]), 2)
        self.assertTrue(all(x["assessed_commit"] == SHA for x in result["inspected_files"]))

    def test_invalid_inventory_and_secret_fail_closed(self):
        self.github.list_file_paths.return_value = ["../private.py"]
        with self.assertRaises(PermissionError):
            inspect_journey_source(
                self.github, sha=SHA, request="ContractService.getContracts"
            )
        self.github.list_file_paths.return_value = ["src/services/ContractService.ts"]
        self.github.get_file_text.return_value = "const key = 'sb_secret_abcdefghijklmnop'"
        with self.assertRaises(PermissionError):
            inspect_journey_source(
                self.github, sha=SHA, request="ContractService.getContracts"
            )


if __name__ == "__main__":
    unittest.main()
