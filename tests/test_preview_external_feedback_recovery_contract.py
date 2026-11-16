import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
SQL=(ROOT/"supabase/migrations/20261116032000_resume_preview_external_feedback_once.sql").read_text()

class ExternalFeedbackRecoveryContract(unittest.TestCase):
    def test_exact_sha_epoch_task_and_running_control_are_mandatory(self):
        for marker in (
            "v_set.status<>'ci_pending'","v_run.status<>'failed'","v_task.status<>'failed'",
            "v_control.state is distinct from 'running'",
            "v_run.metadata->>'execution_generation' is distinct from v_control.generation::text",
            "v_run.branch_name is distinct from v_set.integration_branch",
            "v_set.candidate_commit is distinct from p_candidate_commit",
            "v_set.lease_owner is not null","v_run.lease_owner is not null",
            "v_set.root_task_id","v_project.manifest->'preview'->>'required'",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker,SQL)

    def test_real_separate_sha_bound_first_party_browser_proof_is_required(self):
        for marker in (
            "factory_project_state_snapshots","s.created_at>v_eval.created_at",
            "s.evidence->>'candidate_commit'=p_candidate_commit",
            "s.evidence->>'target_repository'=v_project.repository",
            "s.evidence->'preview'->>'status'='browser_verified'",
            "s.evidence->'preview'->>'verifier_factory_commit'",
            "browser_visual_validation'='success'","source_status->>'vercel_preview'='resolved'",
            "http_403: ping [external]","preview.external_vercel_feedback_noise.retry_queued",
            "preview.external_feedback.browser_verified_resume",
            "e.eval_type='github_ci'","e.eval_type='quality_gate'","d.environment='preview'",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker,SQL)

    def test_privileged_status_only_and_no_release_or_fabricated_evaluations(self):
        text=SQL.lower()
        for marker in ("security invoker","revoke all on function","from public,anon,authenticated",
                       "to service_role","original_browser_failure_preserved',true",
                       "release_authorized',false"):
            self.assertIn(marker,text)
        for forbidden in ("delete from public.factory_evaluations",
                          "update public.factory_evaluations","update public.factory_release_reports",
                          "security definer","http_post"):
            self.assertNotIn(forbidden,text)


class OidcOriginRecoveryContract(unittest.TestCase):
    SQL2=(ROOT/"supabase/migrations/20261116123000_resume_preview_oidc_origin_mismatch_once.sql").read_text()

    def test_new_failure_requires_fresh_independent_browser_proof(self):
        for marker in (
            "factory_resume_preview_oidc_origin_mismatch_once_v1",
            "v_eval.result->>'detail' is distinct from 'preview_application_origin_mismatch'",
            "'[\"page_load\"]'::jsonb",
            "s.created_at>v_eval.created_at",
            "s.evidence->>'candidate_commit'=p_candidate_commit",
            "s.evidence->>'target_repository'=v_project.repository",
            "s.evidence->'preview'->>'status'='browser_verified'",
            "s.evidence->'preview'->>'verifier_factory_commit'",
            "s.source_status->>'browser_visual_validation'='success'",
            "s.constraints->>'production_merge_authorized'='false'",
            "v_run.status<>'failed'",
            "v_task.status<>'failed'",
            "v_set.status<>'ci_pending'",
            "v_set.root_task_id",
            "v_control.state is distinct from 'running'",
            "e.eval_type='github_ci'",
            "e.eval_type='quality_gate'",
            "preview.oidc_origin_mismatch.browser_verified_resume",
            "d.environment='preview'",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker,self.SQL2)

    def test_oidc_migration_is_service_only_and_status_only(self):
        sql=self.SQL2.lower()
        for marker in ("security invoker","revoke all on function",
                       "from public,anon,authenticated","to service_role",
                       "original_browser_failure_preserved',true",
                       "release_authorized',false"):
            self.assertIn(marker,sql)
        for forbidden in ("security definer","update public.factory_evaluations",
                          "delete from public.factory_evaluations",
                          "update public.factory_release_reports",
                          "http_post","update public.factory_change_sets"):
            self.assertNotIn(forbidden,sql)

    def test_recovery_dispatch_is_exact_and_fail_closed(self):
        import sys
        import importlib.util
        sys.path.insert(0,str(ROOT/"src"))
        spec=importlib.util.spec_from_file_location(
            "factory_preview_external_recovery",
            ROOT/"scripts/resume_preview_external_feedback.py")
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.select_recovery_rpc({
            "detail":"preview_application_origin_mismatch",
            "checks":["page_load"]}),
            "factory_resume_preview_oidc_origin_mismatch_once_v1")
        self.assertEqual(module.select_recovery_rpc({
            "detail":"console: Failed to load resource: the server responded with a status of 403 () | http_403: ping [external]",
            "checks":["page_load","http_status","body_visible"]}),
            "factory_resume_preview_external_feedback_once_v1")
        for bad in (None,{},{"detail":"preview_application_origin_mismatch","checks":[]},
                    {"detail":"preview_application_origin_mismatch","checks":["page_load","expected_text"]},
                    {"detail":"http_503: fetch /api/session","checks":["page_load"]},
                    {"detail":"preview_application_origin_mismatch","checks":"page_load"}):
            with self.subTest(bad=bad),self.assertRaises(module.RecoveryBlocked):
                module.select_recovery_rpc(bad)

