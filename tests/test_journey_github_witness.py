"""Contract tests for the GET-only GitHub witness used by the J3/J7 auditor."""
import unittest
from types import SimpleNamespace

from ai_product_factory.journey_github_witness import (
    observe_candidate,require_unchanged_candidate,
)

SHA="a"*40
BASE="b"*40
MERGE="c"*40
BRANCH="factory/change-set-123"
REPO="owner/repo"


class GithubStub:
    def __init__(self,*,merged=False):
        self.pr=SimpleNamespace(
            number=42,head_sha=SHA,head_repository=REPO,head_ref=BRANCH,
            base_ref="main",base_sha=BASE,state="closed" if merged else "open",
            draft=False,merged=merged,merge_commit_sha=MERGE if merged else None,
        )
        self.ref_sha=SHA
        self.pr_reads=0
        self.ref_reads=0

    def get_pull_request(self,number):
        self.pr_reads+=1
        if number!=42:raise AssertionError("unrelated PR")
        return self.pr

    def get_branch_sha(self,branch):
        self.ref_reads+=1
        if branch!=BRANCH:raise AssertionError("unrelated branch")
        return self.ref_sha


def read(github):
    return observe_candidate(github,number=42,sha=SHA,repository=REPO,branch=BRANCH)


class CandidateWitnessTests(unittest.TestCase):
    def test_open_pr_requires_exact_ref_and_two_stable_observations(self):
        github=GithubStub()
        witness=read(github)
        require_unchanged_candidate(github,witness)
        self.assertEqual(witness.head_sha,SHA)
        self.assertFalse(witness.merged)
        self.assertEqual(github.pr_reads,2)
        self.assertEqual(github.ref_reads,2)

    def test_closed_merged_pr_can_have_deleted_branch(self):
        github=GithubStub(merged=True)
        def deleted_branch(_):
            raise AssertionError("deleted branch cannot be consulted after merge")
        github.get_branch_sha=deleted_branch
        witness=read(github)
        require_unchanged_candidate(github,witness)
        self.assertTrue(witness.merged)
        self.assertEqual(witness.merge_sha,MERGE)

    def test_move_between_snapshot_and_recheck_is_rejected(self):
        for key,new in (
            ("head_sha","d"*40),("base_ref","preview/unrelated"),
            ("base_sha","e"*40),("head_repository","other/repo"),
            ("head_ref","factory/other"),("draft",True),("state","closed"),
        ):
            with self.subTest(key=key):
                gh=GithubStub()
                old=read(gh)
                setattr(gh.pr,key,new)
                with self.assertRaises(RuntimeError):
                    require_unchanged_candidate(gh,old)

    def test_open_ref_move_blocks_even_if_pr_response_is_stale(self):
        gh=GithubStub()
        before=read(gh)
        gh.ref_sha="f"*40
        with self.assertRaisesRegex(RuntimeError,"candidate branch changed"):
            require_unchanged_candidate(gh,before)

    def test_wrong_repository_branch_draft_and_base_are_rejected_upfront(self):
        changes=(
            ("number",41),("head_sha","f"*40),
            ("head_repository","attacker/repo"),("head_ref","wrong"),
            ("draft",True),("draft",None),("state","closed"),
            ("base_sha",None),("base_ref",None),("merged","false"),
        )
        for key,new in changes:
            with self.subTest(key=key,value=new):
                gh=GithubStub()
                setattr(gh.pr,key,new)
                with self.assertRaises(RuntimeError):
                    read(gh)

    def test_invalid_requested_identity_cannot_call_github(self):
        for candidate in (
            {"number":True},
            {"sha":"not-a-sha"},
            {"repository":"unscoped"},
            {"branch":"main"},
            {"branch":"../outside"},
            {"branch":"factory//unsafe"},
            {"branch":"factory bad"},
        ):
            with self.subTest(candidate=candidate):
                gh=GithubStub()
                args=dict(number=42,sha=SHA,repository=REPO,branch=BRANCH)
                args.update(candidate)
                with self.assertRaises(RuntimeError):
                    observe_candidate(gh,**args)
                self.assertEqual(gh.pr_reads,0)

    def test_merge_requires_closed_state_and_exact_merge_commit(self):
        for state,merge in (
            ("open",MERGE),
            ("closed",None),
            ("closed","invalid"),
        ):
            with self.subTest(state=state,merge=merge):
                gh=GithubStub(merged=True)
                gh.pr.state=state
                gh.pr.merge_commit_sha=merge
                with self.assertRaises(RuntimeError):
                    read(gh)


if __name__=="__main__":
    unittest.main()
