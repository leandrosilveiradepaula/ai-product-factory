import unittest

from ai_product_factory.commit_provenance import provenance_commit_message


class CommitProvenanceTests(unittest.TestCase):
    def test_formats_only_explicit_safe_trailers(self):
        message=provenance_commit_message("feat: change",{
            "Factory-Run":"run-123",
            "Factory-Change-Set":"cs-123",
            "Factory-Context-SHA256":"a"*64,
        })
        self.assertIn("Factory-Run: run-123",message)
        self.assertIn("Factory-Change-Set: cs-123",message)
        self.assertIn("Factory-Context-SHA256: "+"a"*64,message)
        self.assertNotIn("secret",message.lower())

    def test_rejects_newline_injection_and_invalid_context_hash(self):
        with self.assertRaises(ValueError):
            provenance_commit_message("feat",{"Factory-Run":"run\nInjected: x"})
        with self.assertRaises(ValueError):
            provenance_commit_message("feat",{"Factory-Context-SHA256":"not-a-hash"})

    def test_rejects_unknown_trailer_namespace(self):
        with self.assertRaises(ValueError):
            provenance_commit_message("feat",{"Authorization":"Bearer x"})


if __name__=="__main__":
    unittest.main()
