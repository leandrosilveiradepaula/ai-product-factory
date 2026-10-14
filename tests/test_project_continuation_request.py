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
        self.assertNotIn('const activeTasks=project.tasks.filter',page)
        self.assertIn('Produção continua sob gate humano',page)

    def test_continuation_uses_one_atomic_rpc_with_idempotency(self):
        control=(ROOT/"apps/console/lib/control-plane.ts").read_text()
        self.assertIn('export async function enqueueProjectContinuation',control)
        self.assertIn('rpc/factory_enqueue_project_continuation',control)
        self.assertIn('p_request_id:requestId',control)
        self.assertIn('p_attachment_count:attachmentCount',control)
        self.assertIn('result.request_id!==requestId',control)
        self.assertIn('Já existe trabalho ativo neste projeto',control)
        self.assertNotIn('await enqueueProjectBootstrap(projectKey)',control[control.index('export async function enqueueProjectContinuation'):control.index('export async function getDashboard')])
        self.assertNotIn('factory_projects?id=eq.',control[control.index('export async function enqueueProjectContinuation'):control.index('export async function getDashboard')])
        self.assertNotIn('OPENAI_API_KEY',control)
        self.assertNotIn('merge_pull_request',control)


if __name__=="__main__":
    unittest.main()
