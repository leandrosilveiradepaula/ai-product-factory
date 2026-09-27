from __future__ import annotations

import base64
import json
import os
import pathlib
import tempfile
import time
import unittest
from unittest.mock import patch

from ai_product_factory.codex_oidc import (
    decode_unverified_claims,
    refresh_once,
    validate_github_claims,
    write_token_atomically,
)


def jwt(claims: dict) -> str:
    def part(value: dict) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")
    return f"{part({'alg':'none'})}.{part(claims)}.signature"


class CodexOidcTests(unittest.TestCase):
    def claims(self, *, immutable: bool = False) -> dict:
        now = int(time.time())
        subject = (
            "repo:leandrosilveiradepaula@256917842/ai-product-factory@1387883686:environment:openai-codex"
            if immutable
            else "repo:leandrosilveiradepaula/ai-product-factory:environment:openai-codex"
        )
        return {
            "iss": "https://token.actions.githubusercontent.com",
            "aud": "https://codex.example.invalid",
            "sub": subject,
            "repository_owner_id": "256917842",
            "repository_id": "1387883686",
            "repository": "leandrosilveiradepaula/ai-product-factory",
            "ref": "refs/heads/main",
            "environment": "openai-codex",
            "iat": now - 5,
            "exp": now + 300,
        }

    def test_decodes_and_validates_expected_claims(self):
        claims = decode_unverified_claims(jwt(self.claims()))
        validate_github_claims(
            claims,
            audience="https://codex.example.invalid",
            repository="leandrosilveiradepaula/ai-product-factory",
            ref="refs/heads/main",
            environment="openai-codex",
        )

    def test_validates_immutable_subject_with_repository_ids(self):
        claims = decode_unverified_claims(jwt(self.claims(immutable=True)))
        validate_github_claims(
            claims,
            audience="https://codex.example.invalid",
            repository="leandrosilveiradepaula/ai-product-factory",
            ref="refs/heads/main",
            environment="openai-codex",
            repository_owner_id="256917842",
            repository_id="1387883686",
        )

    def test_immutable_subject_rejects_wrong_repository_ids(self):
        claims = self.claims(immutable=True)
        with self.assertRaises(PermissionError):
            validate_github_claims(
                claims,
                audience="https://codex.example.invalid",
                repository="leandrosilveiradepaula/ai-product-factory",
                ref="refs/heads/main",
                environment="openai-codex",
                repository_owner_id="256917842",
                repository_id="999",
            )

    def test_mismatched_identity_claims_fail_closed(self):
        for field, value in (
            ("sub", "repo:other/repo:environment:openai-codex"),
            ("repository", "other/repo"),
            ("ref", "refs/heads/feature"),
            ("environment", "Production"),
            ("aud", "wrong-audience"),
        ):
            claims = self.claims()
            claims[field] = value
            with self.subTest(field=field), self.assertRaises(PermissionError):
                validate_github_claims(
                    claims,
                    audience="https://codex.example.invalid",
                    repository="leandrosilveiradepaula/ai-product-factory",
                    ref="refs/heads/main",
                    environment="openai-codex",
                )

    def test_atomic_write_uses_protected_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "wif" / "identity-token"
            write_token_atomically(path, "secret-token")
            self.assertEqual(path.read_text(), "secret-token")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)

    def test_refresh_validates_before_replacing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "identity-token"
            token = jwt(self.claims())
            refresh_once(
                token_file=path,
                audience="https://codex.example.invalid",
                repository="leandrosilveiradepaula/ai-product-factory",
                ref="refs/heads/main",
                environment="openai-codex",
                fetcher=lambda audience: token,
            )
            self.assertEqual(path.read_text(), token)

            bad = self.claims()
            bad["repository"] = "other/repo"
            with self.assertRaises(PermissionError):
                refresh_once(
                    token_file=path,
                    audience="https://codex.example.invalid",
                    repository="leandrosilveiradepaula/ai-product-factory",
                    ref="refs/heads/main",
                    environment="openai-codex",
                    fetcher=lambda audience: jwt(bad),
                )
            self.assertEqual(path.read_text(), token)


if __name__ == "__main__":
    unittest.main()
