"""Trusted GitHub OWNER command only; no database or GitHub transport."""
import unittest

from scripts.rotate_released_existing_candidate import validate_event

ENV = {
    "GITHUB_REPOSITORY": "leandrosilveiradepaula/ai-product-factory",
    "GITHUB_ACTOR": "leandrosilveiradepaula",
    "GITHUB_REF": "refs/heads/main",
}

def event(body="/factory-rotate-released-candidate crm-infodive pr=204 issue=22"):
    return {
        "action":"created",
        "repository":{"id":1387883686,"full_name":ENV["GITHUB_REPOSITORY"]},
        "issue":{"number":713,"state":"open"},
        "comment":{"author_association":"OWNER","user":{
            "id":256917842,"login":ENV["GITHUB_ACTOR"],
        },"body":body},
        "sender":{"id":256917842,"login":ENV["GITHUB_ACTOR"]},
    }

class EventTests(unittest.TestCase):
    def test_strict_valid_command(self):
        self.assertEqual(
            validate_event(event(), ENV), ("crm-infodive",204,22),
        )

    def test_untrusted_identity_rejected(self):
        for mutate in (
            lambda e:e["sender"].update(id=1),
            lambda e:e["comment"]["user"].update(id=1),
            lambda e:e["comment"].update(author_association="COLLABORATOR"),
            lambda e:e["repository"].update(id=1),
            lambda e:e["issue"].update(number=1055),
            lambda e:e["issue"].update(pull_request={}),
            lambda e:e.update(action="edited"),
        ):
            v=event()
            mutate(v)
            with self.subTest(v=v),self.assertRaises(PermissionError):
                validate_event(v, ENV)

    def test_malformed_or_ambiguous_commands_rejected(self):
        for body in (
            "/factory-rotate-released-candidate crm-infodive pr=204 issue=22\njunk",
            "/factory-rotate-released-candidate crm-infodive pr=0204 issue=22",
            "/factory-rotate-released-candidate crm-infodive pr=204 issue=0",
            "/factory-rotate-released-candidate crm-infodive pr=204 issue=22 ",
            "/factory-rotate-released-candidate crm-infodive pr=204 issue=22; rm -rf",
            "/factory-rotate-released-candidate crm-infodive pr=204 issue=23\n",
        ):
            with self.subTest(body=body),self.assertRaises(PermissionError):
                validate_event(event(body), ENV)

    def test_wrong_ref_refused(self):
        with self.assertRaises(PermissionError):
            validate_event(event(),{**ENV,"GITHUB_REF":"refs/heads/pr"})

if __name__ == "__main__":
    unittest.main()
