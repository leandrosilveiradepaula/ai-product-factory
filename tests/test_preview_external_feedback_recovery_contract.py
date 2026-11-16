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
