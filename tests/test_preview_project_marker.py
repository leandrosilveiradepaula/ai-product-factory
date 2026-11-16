import unittest

from ai_product_factory.preview_project_marker import (
    ProjectMarkerBlocked, require_exact_project_marker,
)

REPO = "owner/new-project"
ROW = {"repository": REPO, "is_active": True, "name": "Dark Channel Studio",
       "manifest": {"preview": {"required": True, "provider": "vercel", "mode": "github"}}}


class ProjectMarkerTests(unittest.TestCase):
    def test_real_project_name_is_the_expected_unchanged_marker(self):
        self.assertEqual(require_exact_project_marker([ROW],REPO,"Dark Channel Studio"),"Dark Channel Studio")

    def test_not_permitted_to_request_a_login_or_sss_page_marker(self):
        for fake in ("Sign in to Vercel", "Login", "Dark Channel", "", "Dark Channel Studio\nSign in"):
            with self.subTest(text=fake),self.assertRaises(ProjectMarkerBlocked):
                require_exact_project_marker([ROW],REPO,fake)

    def test_explicit_privileged_policy_marker_overrides_project_name(self):
        record={**ROW,"manifest":{"preview":{"required":True,"expected_text":"Authorized Studio"}}}
        self.assertEqual(require_exact_project_marker([record],REPO,"Authorized Studio"),"Authorized Studio")
        with self.assertRaises(ProjectMarkerBlocked):
            require_exact_project_marker([record],REPO,"Dark Channel Studio")

    def test_ambiguous_inactive_untrusted_missing_policy_fail_closed(self):
        invalid=[
            [],[ROW,ROW],[{**ROW,"repository":"attacker/other"}],
            [{**ROW,"is_active":False}], [{**ROW,"manifest":{}}],
            [{**ROW,"name":None}], [{**ROW,"manifest":{"preview":{"required":False}}}],
        ]
        for rows in invalid:
            with self.subTest(rows=rows),self.assertRaises(ProjectMarkerBlocked):
                require_exact_project_marker(rows,REPO,"Dark Channel Studio")
