"""V2 material governance gate: no model-proposed permission is trusted."""
import json
import unittest

from ai_product_factory.v2_material_decision import validated_material_decision
from ai_product_factory.execution_worker import DirectExecutionItem
from ai_product_factory.implementation_producer import ModelImplementationProducer
from ai_product_factory.model_executor import ModelExecutor,ModelResult,ModelRole


QUOTE="Não modificar sem decisão humana explícita a visibilidade de contratos legados sem deal_id."
SOURCE={"journey_binding":{"binding_version":2}}
SNAPSHOT={"docs/codex/CURRENT_TASK.md":"# Governance\n"+QUOTE+"\nEnd."}
DECISION={
    "decision_kind":"material_requirement_change",
    "question":"Qual deve ser a regra de acesso a contratos legados sem negócio?",
    "why_needed":"Sem proprietário verificável, a regra atual não pode ser alterada com segurança.",
    "governance_path":"docs/codex/CURRENT_TASK.md",
    "governance_quote":QUOTE,
}


class GateValidationTests(unittest.TestCase):
    def test_real_quote_and_frozen_v2_binding_create_bounded_question(self):
        row=validated_material_decision(
            DECISION,source=SOURCE,snapshot=SNAPSHOT,
            blocked_reason="the governance rule blocks a write",
        )
        self.assertEqual(row["decision_kind"],"material_requirement_change")
        self.assertEqual(row["governance_quote"],QUOTE)
        self.assertEqual(row["reason"],"the governance rule blocks a write")

    def test_missing_decision_is_a_normal_block_not_a_human_gate(self):
        self.assertIsNone(validated_material_decision(
            None,source=SOURCE,snapshot=SNAPSHOT,blocked_reason="missing source",
        ))

    def test_forged_quote_or_unverified_path_cannot_open_gate(self):
        cases=[
            (dict(DECISION,governance_quote="There is no authorization to work here"),SNAPSHOT),
            (dict(DECISION,governance_path="docs/README.md"),SNAPSHOT),
            (dict(DECISION,governance_path="AGENTS.md"),SNAPSHOT),
            (dict(DECISION,decision_kind="production_change"),SNAPSHOT),
            (dict(DECISION,question="short"),SNAPSHOT),
            (dict(DECISION,unknown_flag=True),SNAPSHOT),
        ]
        for decision,snap in cases:
            with self.subTest(decision=decision):
                with self.assertRaises(PermissionError):
                    validated_material_decision(
                        decision,source=SOURCE,snapshot=snap,blocked_reason="blocked",
                    )

    def test_v1_unbound_run_and_missing_governance_quote_are_denied(self):
        for source in ({}, {"journey_binding":{"binding_version":1}}):
            with self.assertRaises(PermissionError):
                validated_material_decision(
                    DECISION,source=source,snapshot=SNAPSHOT,blocked_reason="blocked",
                )
        with self.assertRaises(PermissionError):
            validated_material_decision(
                DECISION,source=SOURCE,snapshot={},blocked_reason="blocked",
            )

    def test_producer_parses_structured_gate_without_issuing_code(self):
        class Provider:
            def execute(self,request):
                self.schema=request.output_schema
                return ModelResult(ModelRole.PRIMARY,json.dumps({
                    "plan_markdown":"blocked by governance",
                    "files":[],"commit_message":"","pr_title":"","pr_body":"",
                    "blocked_reason":"need explicit business rule",
                    "decision_needed":DECISION,
                }),provider_ref="test")
        provider=Provider()
        item=DirectExecutionItem(
            "run","task","crm","org/repo",209,"Contracts","Access","factory/cs/x",False,
            "cs","wu",1,context_packet={"source":"frozen","repository_snapshot":SNAPSHOT},
        )
        artifact=ModelImplementationProducer(ModelExecutor(primary=provider)).produce(item)
        self.assertEqual(artifact.files,{})
        self.assertEqual(artifact.decision_needed,DECISION)
        self.assertIn("decision_needed",provider.schema["required"])
        self.assertFalse(provider.schema["properties"]["decision_needed"]["additionalProperties"])

    def test_unblocked_output_cannot_smuggle_human_decision(self):
        class Provider:
            def execute(self,request):
                return ModelResult(ModelRole.PRIMARY,json.dumps({
                    "plan_markdown":"patch","files":[{"path":"src/a.ts","content":"x"}],
                    "commit_message":"patch","pr_title":"patch","pr_body":"patch",
                    "blocked_reason":"","decision_needed":DECISION,
                }),provider_ref="test")
        with self.assertRaisesRegex(ValueError,"material decision"):
            ModelImplementationProducer(ModelExecutor(primary=Provider())).produce(
                DirectExecutionItem("run","task","p","org/repo",1,"x","x","factory/a"),
            )


if __name__=="__main__":
    unittest.main()
