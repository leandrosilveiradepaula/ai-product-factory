"""Lockfile must retain the published Next.js 15.5.x critical security patch.

Only production code is checked: no network, API key or speculative npm probes.
The npm audit policy in Console CI remains the authoritative live advisory gate.
"""
import json
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]
APP=ROOT/"apps/console"
PACKAGE=json.loads((APP/"package.json").read_text())
LOCK=json.loads((APP/"package-lock.json").read_text())

def semver(value):
    if not isinstance(value,str) or re.fullmatch(r"\d+\.\d+\.\d+",value) is None:
        raise AssertionError("Console Next.js version must be exact semver")
    return tuple(int(x) for x in value.split("."))

class NextSecurityFloor(unittest.TestCase):
    def test_next_version_is_vetted_patch_or_newer(self):
        installed=PACKAGE["dependencies"]["next"]
        self.assertGreaterEqual(semver(installed),(15,5,28))
        self.assertEqual(LOCK["packages"][""]["dependencies"]["next"],installed)
        self.assertEqual(LOCK["packages"]["node_modules/next"]["version"],installed)

    def test_compiler_platforms_follow_next_patch(self):
        version=PACKAGE["dependencies"]["next"]
        packages=LOCK["packages"]
        self.assertIn("node_modules/@next/env",packages)
        for key,value in packages.items():
            if key=="node_modules/next" or key.startswith("node_modules/@next/"):
                with self.subTest(package=key):
                    self.assertEqual(value["version"],version)
                    self.assertTrue(value["integrity"].startswith("sha512-"))
                    self.assertTrue(value["resolved"].startswith("https://registry.npmjs.org/"))
        for key,required in packages["node_modules/next"]["optionalDependencies"].items():
            if key.startswith("@next/"):
                self.assertEqual(required,version)

    def test_image_optimization_patch_not_downgraded(self):
        sharp=LOCK["packages"]["node_modules/sharp"]
        self.assertGreaterEqual(semver(sharp["version"]),(0,35,5))
        self.assertIn("0.35.5",LOCK["packages"]["node_modules/next"]["optionalDependencies"]["sharp"])

if __name__=="__main__":
    unittest.main()
