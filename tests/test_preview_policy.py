import unittest

from ai_product_factory.preview_policy import evaluate_preview_applicability


class Tests(unittest.TestCase):
    def test_missing_policy_fails_closed_to_required(self):
        d=evaluate_preview_applicability(manifest={},changed_files=("src/a.py",))
        self.assertTrue(d.required)

    def test_explicit_not_required_is_respected(self):
        d=evaluate_preview_applicability(manifest={"preview":{"required":False,"reason":"backend only"}},changed_files=("src/a.py",))
        self.assertFalse(d.required)
        self.assertEqual(d.reason,"backend only")

    def test_required_paths_only_require_matching_change(self):
        manifest={"preview":{"required_paths":["apps/console/**","web/**"]}}
        no=evaluate_preview_applicability(manifest=manifest,changed_files=("src/core.py",))
        yes=evaluate_preview_applicability(manifest=manifest,changed_files=("apps/console/app/page.tsx","src/core.py"))
        self.assertFalse(no.required)
        self.assertTrue(yes.required)
        self.assertEqual(yes.matched_paths,("apps/console/app/page.tsx",))

    def test_invalid_required_paths_fails_closed_with_error(self):
        with self.assertRaises(ValueError):
            evaluate_preview_applicability(manifest={"preview":{"required_paths":"apps/**"}},changed_files=())


if __name__=="__main__": unittest.main()
