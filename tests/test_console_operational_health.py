"""Console operational health must be complete and fail closed."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
CONTROL=(ROOT/"apps/console/lib/control-plane.ts").read_text()
READER=(ROOT/"apps/console/lib/operational-health-inventory.ts").read_text()
WORKFLOW=(ROOT/".github/workflows/console.yml").read_text()
NODE_TEST=(ROOT/"scripts/test_console_operational_health.cjs").read_text()

class OperationalHealthConsoleContract(unittest.TestCase):
    def test_full_paginated_inventory_is_used_in_operator_ui(self):
        section=CONTROL.split("export async function getOperationsHealth()",1)[1].split("export type WorkQueueItem",1)[0]
        self.assertIn("readCompleteOperationalRows",section)
        self.assertIn('table:"factory_runs"',section)
        self.assertIn('table:"factory_tool_usage"',section)
        self.assertIn('idKind:"bigint"',section)
        self.assertIn("summarizeOperationalHealth",section)
        self.assertIn("offset+=100",section)
        self.assertIn('if(!response.ok)throw',section)
        self.assertNotIn("usageResponse.ok?",section)
        self.assertNotIn("limit=200",section)
        self.assertNotIn("limit=1000",section)
        self.assertNotIn("if(!cfg)return{expiredLeases:0",section)

    def test_bounded_offset_pages_never_hide_errors(self):
        self.assertIn("MAX_PAGES=20",READER)
        self.assertIn("PAGE_SIZE=200",READER)
        self.assertIn("created_at.desc,id.desc",READER)
        self.assertIn("new Set<string>()",READER)
        self.assertIn("repetiu ID",READER)
        self.assertIn("perdeu ordenação",READER)
        self.assertIn("4.000",READER)
        self.assertIn('kind==="bigint"?BigInt(a)>BigInt(b)',READER)
        self.assertIn("throw new Error",READER)
        self.assertIn("if(amount===null)",READER)
        self.assertIn('failedTasks.get(taskId)==="failed"',READER)

    def test_real_typescript_behavior_tests_run_during_console_validation(self):
        self.assertIn("run: node ../../scripts/test_console_operational_health.cjs",WORKFLOW)
        self.assertLess(WORKFLOW.index("      - run: npm ci"),WORKFLOW.index("node ../../scripts/test_console_operational_health.cjs"))
        self.assertIn("ts.transpileModule",NODE_TEST)
        self.assertIn('test("runs older than newest 200',NODE_TEST)
        self.assertIn('test("more than 1000 BIGINT',NODE_TEST)
        self.assertIn('test("HTTP failures',NODE_TEST)
        self.assertIn('test("exact 4000',NODE_TEST)
        self.assertNotIn("supabase.co/rest/v1",NODE_TEST)

if __name__=="__main__":
    unittest.main()
