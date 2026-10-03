from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]


class ProjectContinuationRequestTests(unittest.TestCase):
    def test_console_exposes_project_scoped_continuation_action(self):
        detail=(ROOT/"apps/console/app/projects/[key]/page.tsx").read_text()
        page=(ROOT/"apps/console/app/projects/[key]/request/page.tsx").read_text()
        self.assertIn('Pedir alteração',detail)
        self.assertIn('href={"/projects/"+p.key+"/request"}',detail)
        self.assertIn('enqueueProjectContinuation',page)
        self.assertIn('A Factory não abre dois ciclos concorrentes',page)
        self.assertIn('Produção continua sob gate humano',page)

    def test_continuation_is_durable_fail_closed_and_reuses_existing_bootstrap(self):
        control=(ROOT/"apps/console/lib/control-plane.ts").read_text()
        self.assertIn('export async function enqueueProjectContinuation',control)
        self.assertIn('continuation_request',control)
        self.assertIn('reconcile_first:true',control)
        self.assertIn('source:"factory-console"',control)
        self.assertIn('const terminal=new Set(["completed","cancelled","failed","merged"])',control)
        self.assertIn('Já existe trabalho ativo neste projeto',control)
        self.assertIn('project.continuation.requested',control)
        self.assertIn('await enqueueProjectBootstrap(projectKey)',control)
        self.assertNotIn('OPENAI_API_KEY',control)
        self.assertNotIn('merge_pull_request',control)


if __name__=="__main__":
    unittest.main()
