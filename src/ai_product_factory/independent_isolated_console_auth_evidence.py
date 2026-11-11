"""Bounded B2 evidence from an exact-tree isolated PostgreSQL execution."""
from __future__ import annotations

import re
from dataclasses import dataclass
from .product_readiness_certification import VerifiedCriterionEvidence


class IsolatedConsoleAuthEvidenceBlocked(RuntimeError):
    pass


SHA = re.compile(r"[0-9a-f]{40}\Z", re.ASCII)
POSTGRES_RECEIPT_FIELDS = frozenset({
    "run_id", "source_sha", "tree_oid", "source_tree_oid", "scope",
    "non_document_tree_digest",
})


@dataclass(frozen=True)
class IsolatedConsoleAuthEvidence:
    repository: str
    assessed_commit: str
    run_id: int
    source_sha: str

    def evidence(self) -> list[str]:
        return ["https://github.com/" + self.repository + "/actions/runs/" + str(self.run_id)
                + "#sha=" + self.assessed_commit]

    def receipt(self) -> dict:
        return {"schema":"factory-b2-isolated-console-auth-proof-v1",
                "repository":self.repository,"assessed_commit":self.assessed_commit,
                "workflow_run_id":self.run_id,"source_sha":self.source_sha,
                "isolated_sql_role_and_rpc_negatives_verified":True,
                "does_not_certify":["authn_authz","data_access_boundaries","product_ready"],
                "writes":0,"paid_calls":0}


def verify_isolated_console_auth(*, repository: str, assessed_commit: str,
                                 regression_proof: object) -> IsolatedConsoleAuthEvidence:
    if not isinstance(regression_proof, VerifiedCriterionEvidence):
        raise IsolatedConsoleAuthEvidenceBlocked("b2_postgres_regression_unavailable")
    receipt = regression_proof.retained_receipt
    postgres = receipt.get("postgres_qa") if isinstance(receipt, dict) else None
    if (regression_proof.repository != repository or regression_proof.assessed_commit != assessed_commit
            or regression_proof.domain != "test_strategy" or regression_proof.criterion != "regression_gates"
            or not isinstance(postgres, dict) or set(postgres) != POSTGRES_RECEIPT_FIELDS
            or type(postgres.get("run_id")) is not int or postgres["run_id"] < 1
            or any(not isinstance(postgres.get(key), str) or SHA.fullmatch(postgres[key]) is None
                   for key in ("source_sha", "tree_oid", "source_tree_oid", "non_document_tree_digest"))
            or postgres.get("scope") not in {"identical_git_tree", "identical_non_markdown_git_blobs"}
            or (postgres["scope"] == "identical_git_tree" and
                (postgres["tree_oid"] != postgres["source_tree_oid"]
                 or postgres["non_document_tree_digest"] != postgres["tree_oid"]))):
        raise IsolatedConsoleAuthEvidenceBlocked("b2_postgres_receipt_invalid")
    return IsolatedConsoleAuthEvidence(repository, assessed_commit, postgres["run_id"], postgres["source_sha"])
