from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class ProjectContinuationAttachmentTests(unittest.TestCase):
    def test_continuation_accepts_private_bounded_attachments(self):
        page=(ROOT/"apps/console/app/projects/[key]/request/page.tsx").read_text()
        attachments=(ROOT/"apps/console/lib/attachments.ts").read_text()
        self.assertIn('encType="multipart/form-data"',page)
        self.assertIn('name="attachments"',page)
        self.assertIn('files.length>10',page)
        self.assertIn('uploadProjectContinuationFile(project.id,requestId,file)',page)
        self.assertIn('enqueueProjectContinuation(projectKey,request,files.length,requestId)',page)
        self.assertIn('validateProjectFile(file)',attachments)
        self.assertIn('PROJECT_FILE_BUCKET',attachments)
        self.assertIn('project_id:projectId',attachments)
        self.assertIn('finalized_at:new Date().toISOString()',attachments)
        self.assertIn('cleanupProjectContinuationFiles',page)
        self.assertIn('draft_id=eq.',attachments)
        self.assertIn('method:"DELETE"',attachments)

    def test_request_manifest_and_audit_include_attachment_evidence(self):
        control=(ROOT/"apps/console/lib/control-plane.ts").read_text()
        self.assertIn('requestedId?:string',control)
        self.assertIn('requestId=requestedId||crypto.randomUUID()',control)
        self.assertIn('attachment_count:attachmentCount',control)

if __name__=="__main__":
    unittest.main()
