"""Queued descendants are visible for operator reconciliation, without dispatch."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
CODE=(ROOT/"apps/console/lib/control-plane.ts").read_text()
PAGE=(ROOT/"apps/console/app/queue/page.tsx").read_text()
QUEUE=CODE.split("export async function getWorkQueue",1)[1].split("export type EvaluationRow",1)[0]

class QueueVisibilityTests(unittest.TestCase):
    def test_no_silent_hiding_of_children_after_completed_parent(self):
        self.assertIn("requiresReconciliation",CODE)
        self.assertIn('new Set(["completed","integrated","cancelled"])',QUEUE)
        self.assertIn("requiresReconciliation:!!parent&&terminalParent.has(parent.status)",QUEUE)
        self.assertNotIn("activeRows=rows.filter",QUEUE)
        self.assertIn("return tasks.map(x=>",QUEUE)
        self.assertNotIn("return activeRows.map",QUEUE)
        self.assertIn("parent.projectId!==projectId",QUEUE)

    def test_incomplete_api_reports_are_not_transformed_into_empty_queue(self):
        self.assertIn("limit+1",QUEUE)
        self.assertIn("rows.length>limit",QUEUE)
        self.assertIn("Inventário de fila incompleto",QUEUE)
        self.assertIn("Inventário de tarefas-pai incompleto",QUEUE)
        self.assertIn("Inventário de projetos da fila incompleto",QUEUE)
        self.assertIn("if(!parentResponse.ok)throw",QUEUE)
        self.assertIn("if(!response.ok)throw",QUEUE)
        self.assertIn("cache:\"no-store\"",QUEUE)

    def test_operator_sees_distinct_read_only_reconciliation_section(self):
        self.assertIn("const operational=items.filter(x=>!x.requiresReconciliation)",PAGE)
        self.assertIn("const needsReview=items.filter(x=>x.requiresReconciliation)",PAGE)
        self.assertIn("Tarefas que exigem reconciliação",PAGE)
        self.assertIn("Um pai concluído não comprova",PAGE)
        self.assertIn("nem autoriza executá-lo novamente",PAGE)
        self.assertIn("queue.reconciliation",PAGE)
        self.assertIn("operational.map",PAGE)
        self.assertIn("needsReview.map",PAGE)
        self.assertNotIn("onClick=",PAGE)
        self.assertNotIn("enqueueProject",PAGE)
        self.assertNotIn("dispatch(",PAGE)

if __name__=="__main__":
 unittest.main()
