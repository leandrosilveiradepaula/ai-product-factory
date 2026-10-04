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
        self.assertIn('href={"/api/projects/"+encodeURIComponent(p.key)+"/attachments/"+encodeURIComponent(file.id)}',page)

    def test_attachment_download_is_authenticated_project_bound_and_private(self):
        route=(ROOT/"apps/console/app/api/projects/[key]/attachments/[attachmentId]/route.ts").read_text()
        self.assertIn("await requireConsoleOperator()",route)
        self.assertIn("project_key=eq.",route)
        self.assertIn("project_id=eq.",route)
        self.assertIn("finalized_at=not.is.null",route)
        self.assertIn("file.storage_bucket!==PROJECT_FILE_BUCKET",route)
        self.assertIn("MAX_PROJECT_FILE_BYTES",route)
        self.assertIn('"Cache-Control":"private, no-store"',route)
        self.assertIn('"X-Content-Type-Options":"nosniff"',route)
        self.assertIn('"Content-Disposition"',route)
        page=(ROOT/"apps/console/app/projects/[key]/page.tsx").read_text()
        self.assertNotIn("storage_path",page)

    def test_project_detail_shows_bounded_durable_continuation_history(self):
        control=(ROOT/"apps/console/lib/control-plane.ts").read_text()
        page=(ROOT/"apps/console/app/projects/[key]/page.tsx").read_text()
        self.assertIn("getProjectContinuationHistory",control)
        self.assertIn("event_type=eq.project.continuation.requested",control)
        self.assertIn("Math.min(25",control)
        self.assertIn("continuationHistory.slice(1)",page)
        self.assertIn("Pedidos anteriores",page)
        self.assertNotIn("storage_path",control[control.index("export type ProjectContinuationHistoryItem"):control.index("export type ProjectContinuationContext")])

if __name__=="__main__":
    unittest.main()
