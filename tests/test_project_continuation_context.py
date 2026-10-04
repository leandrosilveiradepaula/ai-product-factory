from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class ProjectContinuationContextTests(unittest.TestCase):
    def test_project_detail_shows_latest_continuation_and_private_attachment_metadata(self):
        control=(ROOT/"apps/console/lib/control-plane.ts").read_text()
        page=(ROOT/"apps/console/app/projects/[key]/page.tsx").read_text()
        self.assertIn("getProjectContinuationContext",control)
        self.assertIn("manifest?.continuation_request",control)
        self.assertIn("factory_project_attachments?select=id,original_name,mime_type,size_bytes",control)
        self.assertIn("finalized_at=not.is.null",control)
        self.assertNotIn("storage_path",control[control.index("export type ProjectContinuationContext"):control.index("export type GitHubAppInstallAction")])
        self.assertIn('title="Último pedido"',page)
        self.assertIn("continuation.summary",page)
        self.assertIn("continuation.attachments.map",page)

if __name__=="__main__":
    unittest.main()
