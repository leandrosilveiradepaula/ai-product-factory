"""Security regressions for authentic operator-blocked-work recovery (offline)."""
from __future__ import annotations

import copy
import json
import re
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ai_product_factory.operator_blocked_recovery_source import inspect_operator_sql_recovery
from ai_product_factory.source_scope_admission import SourceScopeBlocked
from ai_product_factory.supabase_runtime_queue import SupabaseRuntimeQueue
from ai_product_factory.product_stage_executor import (
    ProductStageExecutor, _verified_greenfield_source_for_reconciliation,
)
from ai_product_factory.model_executor import ModelExecutor, ModelResult, ModelRole

PID="11111111-1111-1111-1111-111111111111"
RID="22222222-2222-2222-2222-222222222222"
REQUEST="33333333-3333-3333-3333-333333333333"
COMMAND="44444444-4444-4444-4444-444444444444"
JOB="55555555-5555-5555-5555-555555555555"
SOURCE="66666666-6666-6666-6666-666666666666"
CS="77777777-7777-7777-7777-777777777777"
TASK="88888888-8888-8888-8888-888888888888"
ROOT="99999999-9999-9999-9999-999999999999"
ROOT_TASK="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
ACTOR="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
ORIGINAL_TASK="cccccccc-cccc-cccc-cccc-cccccccccccc"
RETRY="dddddddd-dddd-dddd-dddd-dddddddddddd"
HEAD="c"*40
OLDER="b"*40
PATH="supabase/migrations/20261116132000_tenant_persistence_rls.sql"
FINDING={"kind":"database_security","code":"permissive_public_grant",
         "path":PATH,"severity":"error","scope_keys":[PATH],"source":"architecture_guardian_v1"}
MANIFEST={"source":"factory-console","onboarding_mode":"greenfield",
          "bootstrap_request_id":"01234567-89ab-cdef-0123-456789abcdef"}
PROJECT={"id":PID,"repository":"owner/greenfield","project_kind":"greenfield","manifest":MANIFEST}


def fixture():
    return {
      "factory_runs": [
        {"id":RID,"task_id":TASK,"status":"running","execution_route":None,
         "metadata":{"source":"operator-blocked-work-recovery",
                    "stages":["reconciliation","gap_analysis","planning"],
                    "recovery_request_id":COMMAND,"recovery_source_run_id":SOURCE,
                    "repair_job_id":JOB,"terminal_change_set_id":CS,
                    "execution_generation":1}},
        {"id":SOURCE,"task_id":ORIGINAL_TASK,"status":"blocked",
         "metadata":{"change_set_id":CS},"lease_owner":None,"lease_expires_at":None},
        {"id":ROOT,"task_id":ROOT_TASK,"status":"merged"},
      ],
      "factory_blocked_work_recovery_requests":[{
        "id":REQUEST,"project_id":PID,"command_id":COMMAND,
        "source_task_id":ORIGINAL_TASK,"source_run_id":SOURCE,
        "repair_job_id":JOB,"continuation_task_id":TASK,
        "continuation_run_id":RID,"status":"running","execution_generation":1,
      }],
      "factory_project_execution_commands":[{
        "project_id":PID,"command_id":COMMAND,"command":"restart",
        "expected_version":1,"actor_id":ACTOR,
        "result":{"created":True,"project_id":PID,"run_id":RID,"task_id":TASK,
                  "recovery_request_id":REQUEST,"command":"restart",
                  "state":"running","version":1,"generation":1},
      }],
      "factory_console_operators":[{"user_id":ACTOR,"is_active":True}],
      "factory_project_execution_controls":[{
        "project_id":PID,"state":"running","version":1,"generation":1,
      }],
      "factory_repair_jobs":[{
        "id":JOB,"project_id":PID,"change_set_id":CS,"source_run_id":ROOT,
        "task_id":ORIGINAL_TASK,"status":"blocked","source_role":"security",
        "cycle":2,"max_cycles":3,"candidate_commit":OLDER,
        "finding":FINDING,"write_scopes":[PATH],
      }],
      "factory_tasks":[{
        "id":TASK,"project_id":PID,"status":"running",
        "acceptance_criteria":[{"finding":FINDING,"source_role":"security"}],
      }],
      "factory_change_sets":[{
        "id":CS,"project_id":PID,"root_task_id":ROOT_TASK,"status":"completed",
        "lease_owner":None,"lease_expires_at":None,
      }],
    }


class FakeGithub:
    repository="owner/greenfield"
    def __init__(self):
        self.reads=[]
        self.sha=HEAD
        self.compare={"status":"ahead","behind_by":0}
    def get_branch_sha(self, branch):
        self.reads.append(("branch",branch))
        return self.sha
    def compare_commits(self, source, target):
        self.reads.append(("compare",source,target))
        return self.compare
    def get_file_text(self, path, *, ref):
        self.reads.append(("file",path,ref))
        if path=="README.md":return "# Product with authenticated editor"
        if path=="package.json":return '{"name":"generic-greenfield"}'
        if path==PATH:return "-- versioned SQL\nrevoke all on public.foo from public;\n"
        raise AssertionError("unexpected read")
    def create_branch(self,*a,**kw):raise AssertionError("unexpected write")
    def commit_files(self,*a,**kw):raise AssertionError("unexpected write")


class FakeGet:
    def __init__(self,data=None):
        self.data=copy.deepcopy(data if data is not None else fixture())
        self.calls=[]
    def __call__(self,path):
        self.calls.append(path)
        table=path.split("?",1)[0]
        if table not in self.data:raise RuntimeError("unexpected table")
        matches=re.findall(r"(?:^|&)([a-z_]+)=eq\.([0-9a-f-]{36})",path)
        return [copy.deepcopy(row) for row in self.data[table]
                if all(row.get(key)==value for key,value in matches)]


class OperatorRecoveryTests(unittest.TestCase):
    def inspect(self,db=None,github=None,run_id=RID):
        db=db or FakeGet()
        github=github or FakeGithub()
        return inspect_operator_sql_recovery(
            project=PROJECT,context={"manifest":MANIFEST},
            run_id=run_id,get=db,github=github,
        ),db,github

    def test_valid_history_produces_exact_sha_single_file_only(self):
        context,db,gh=self.inspect()
        proof=context["current_state_facts"]["operator_recovery"]
        self.assertEqual(proof["status"],"validated_operator_restart")
        self.assertEqual(proof["scope_paths"],[PATH])
        self.assertEqual(proof["terminal_change_set_id"],CS)
        candidate=context["current_state_facts"]["live_candidate"]
        self.assertEqual(candidate["sha"],HEAD)
        self.assertIsNone(candidate["verified_open_pr"])
        self.assertEqual(candidate["source_evidence"]["request_source_paths"],[PATH])
        self.assertTrue(_verified_greenfield_source_for_reconciliation(context))
        self.assertEqual(gh.reads[-1],("branch","main"))
        self.assertIn(("file",PATH,HEAD),gh.reads)
        self.assertTrue(any(p.startswith("factory_console_operators?") for p in db.calls))

    def test_wrong_actor_generation_scope_status_block_before_github(self):
        cases=[
            ("factory_console_operators",0,"is_active",False),
            ("factory_project_execution_commands",0,"command","start"),
            ("factory_project_execution_commands",0,"actor_id","f"*36),
            ("factory_project_execution_controls",0,"state","stopped"),
            ("factory_project_execution_controls",0,"generation",2),
            ("factory_blocked_work_recovery_requests",0,"project_id","f"*36),
            ("factory_blocked_work_recovery_requests",0,"repair_job_id","f"*36),
            ("factory_change_sets",0,"status","running"),
            ("factory_repair_jobs",0,"write_scopes",["."]),
            ("factory_repair_jobs",0,"status","passed"),
            ("factory_repair_jobs",0,"cycle",3),
            ("factory_tasks",0,"acceptance_criteria",[]),
        ]
        for table,index,key,value in cases:
            with self.subTest(table=table,key=key):
                db=FakeGet()
                db.data[table][index][key]=value
                gh=FakeGithub()
                with self.assertRaises(SourceScopeBlocked):
                    self.inspect(db=db,github=gh)
                self.assertFalse(gh.reads)

    def test_missing_or_moved_or_redacted_code_fails_closed(self):
        gh=FakeGithub()
        gh.compare={"status":"diverged","behind_by":2}
        with self.assertRaises(SourceScopeBlocked):self.inspect(github=gh)
        gh=FakeGithub()
        gh.get_file_text=lambda p,ref: (
            'key="' + "sk-proj-" + "abcdefghijklmnopqrstuvwx123456" + '"'
            if p==PATH else "# safe"
        )
        with self.assertRaises(SourceScopeBlocked):self.inspect(github=gh)
        gh=FakeGithub()
        gh.get_branch_sha=Mock(side_effect=[HEAD,"d"*40])
        with self.assertRaises(SourceScopeBlocked):self.inspect(github=gh)

    def test_only_exact_retry_of_original_operator_recovery_is_admitted(self):
        db=FakeGet()
        original=db.data["factory_runs"][0]
        original["status"]="failed"
        original["last_error"]="reconciliation_context_preflight_failed"
        retried=copy.deepcopy(original)
        retried["id"]=RETRY
        retried["status"]="running"
        retried.pop("last_error")
        retried["metadata"].pop("execution_generation")
        retried["metadata"]["retry_source_generation"]="1"
        retried["metadata"]["retry_of"]=RID
        db.data["factory_runs"].insert(0,retried)
        db.data["factory_blocked_work_recovery_requests"][0]["status"]="blocked"
        context,_,_=self.inspect(db=db,run_id=RETRY)
        self.assertEqual(context["current_state_facts"]["operator_recovery"]["run_id"],RETRY)
        original["last_error"]="unrelated_failure"
        with self.assertRaises(SourceScopeBlocked):self.inspect(db=db,run_id=RETRY)

    def test_second_retry_requires_original_failed_auth_and_no_third_replay(self):
        db=FakeGet()
        first=db.data["factory_runs"][0]
        first["status"]="failed"
        first["last_error"]="reconciliation_context_preflight_failed"
        second=copy.deepcopy(first)
        second["id"]="dddddddd-dddd-dddd-dddd-dddddddddddd"
        second["metadata"]["retry_of"]=RID
        second["metadata"]["retry_source_generation"]="1"
        # A claimed first retry has the real execution epoch reinstated.
        self.assertEqual(second["metadata"]["execution_generation"],1)
        second["status"]="failed"
        second["last_error"]="reconciliation_context_preflight_failed"
        third=copy.deepcopy(second)
        third["id"]="eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
        third["status"]="running"
        third["metadata"]["retry_of"]=second["id"]
        # RPC projects the source epoch to TEXT, never null.
        third["metadata"]["retry_source_generation"]="1"
        db.data["factory_runs"].extend([second,third])
        db.data["factory_blocked_work_recovery_requests"][0]["status"]="blocked"
        ctx,_,_=self.inspect(db=db,run_id=third["id"])
        self.assertEqual(ctx["current_state_facts"]["operator_recovery"]["run_id"],third["id"])
        second["last_error"]="model_failed"
        with self.assertRaises(SourceScopeBlocked):
            self.inspect(db=db,run_id=third["id"])
        second["last_error"]="reconciliation_context_preflight_failed"
        fourth=copy.deepcopy(third)
        fourth["id"]="ffffffff-ffff-ffff-ffff-ffffffffffff"
        fourth["metadata"]["retry_of"]=third["id"]
        db.data["factory_runs"].append(fourth)
        with self.assertRaises(SourceScopeBlocked):
            self.inspect(db=db,run_id=fourth["id"])
        for invalid in (None, 1, "0", "2", "1 "):
            with self.subTest(epoch=invalid):
                gh=FakeGithub()
                third["metadata"]["retry_source_generation"]=invalid
                with self.assertRaises(SourceScopeBlocked):
                    self.inspect(db=db,github=gh,run_id=third["id"])
                self.assertEqual(gh.reads,[])
        third["metadata"]["retry_source_generation"]="1"

    def test_queue_recovery_uses_claimed_run_not_arbitrary_source(self):
        queue=SupabaseRuntimeQueue(url="https://example.supabase.co",service_role_key="offline")
        db=FakeGet()
        queue._get=Mock(side_effect=lambda path: (
            [{**PROJECT}] if path.startswith("factory_projects?") else db(path)
        ))
        queue._live_candidate_context=Mock(side_effect=SourceScopeBlocked(
            "greenfield_owner_continuation_required"))
        with patch("ai_product_factory.supabase_runtime_queue.GitHubRestAdapter",
                   return_value=FakeGithub()):
            context=queue._live_claimed_candidate_context(
                PID,{"manifest":MANIFEST},run_id=RID,
            )
        self.assertEqual(context["current_state_facts"]["operator_recovery"]["command_id"],COMMAND)
        with self.assertRaisesRegex(SourceScopeBlocked,"greenfield_owner_continuation_required"):
            queue._live_claimed_candidate_context(
                PID,{"manifest":{"source":"factory-console"}},run_id=RID,
            )

    def test_planning_never_accepts_extra_sql_or_unscoped_changes(self):
        context,_,_=self.inspect()
        class Provider:
            def __init__(self,scopes):
                self.scopes=scopes
            def execute(self,req):
                return ModelResult(ModelRole.PRIMARY,
                    json.dumps({
                        "architecture":"scoped review",
                        "workstreams":[],
                        "tasks":[{
                            "task_key":"repair-one","scope_keys":self.scopes,
                            "required_capabilities":["implementation"],
                            "depends_on":[],
                        }],
                        "decisions_needed":[],
                        "specialist_reviews":[],
                        "test_strategy":{},
                        "release_strategy":{},
                        "risks":[],
                    }),provider_ref="offline")
        item=SimpleNamespace(context=context,project_key="generic-greenfield",
                             run_id=RID,task_id=TASK,
                             stages=("reconciliation","gap_analysis","planning"),
                             execution_generation=1)
        for scopes in ([PATH,"AGENTS.md"],["."]):
            with self.subTest(scopes=scopes):
                with self.assertRaisesRegex(PermissionError,"frozen repair scope"):
                    ProductStageExecutor(ModelExecutor(primary=Provider(scopes))).execute(item,"planning")
        good=ProductStageExecutor(ModelExecutor(primary=Provider([PATH]))).execute(
            item,"planning"
        )
        self.assertEqual(good["tasks"][0]["scope_keys"],[PATH])
        self.assertIn("Operator Restart",good["_operator_recovery_constraint"])


if __name__=="__main__":unittest.main()
