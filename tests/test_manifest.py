import json
import unittest
from pathlib import Path

from ai_product_factory.manifest import ManifestError, load_manifest, validate_manifest


ROOT = Path(__file__).resolve().parents[1]


class ManifestTests(unittest.TestCase):
    def test_example_manifest_is_valid(self):
        data = load_manifest(ROOT / "config" / "factory.example.json")
        self.assertEqual(data["factory_version"], 1)

    def test_prod_requires_human_in_v01(self):
        data = json.loads((ROOT / "config" / "factory.example.json").read_text())
        data["autonomy"]["production_requires_human"] = False
        with self.assertRaises(ManifestError):
            validate_manifest(data)


if __name__ == "__main__":
    unittest.main()
