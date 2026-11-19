import base64
import json
import tempfile
from pathlib import Path
import unittest
from ai_product_factory.private_chat_provider import PrivateChatConfig, PrivateModelError
from scripts.sql_infodive_private_network import IFACE, prepare, probe, require_manual_main

PVT = base64.b64encode(bytes(range(32))).decode()
PUB = base64.b64encode(bytes(range(32, 64))).decode()
ENV = {
    "FACTORY_SQL_INFODIVE_ENABLED": "true",
    "FACTORY_SQL_INFODIVE_BASE_URL": "http://10.66.66.1",
    "FACTORY_SQL_INFODIVE_MODEL": "SQL-InfoDive",
    "FACTORY_SQL_INFODIVE_HTTP_HOST": "chat.internal",
    "FACTORY_SQL_INFODIVE_ALLOW_PRIVATE_HTTP": "true",
    "FACTORY_INFODIVE_WG_CLIENT_PRIVATE_KEY": PVT,
    "FACTORY_INFODIVE_WG_PEER_PUBLIC_KEY": PUB,
    "FACTORY_INFODIVE_WG_ENDPOINT": "vpn.example.invalid:51820",
    "FACTORY_INFODIVE_WG_CLIENT_ADDRESS": "10.66.66.9/32",
    "GITHUB_SHA": "a" * 40,
    "GITHUB_REPOSITORY": "leandrosilveiradepaula/ai-product-factory",
    "GITHUB_REF": "refs/heads/main",
    "GITHUB_EVENT_NAME": "workflow_dispatch",
}

class PrivateRouteTests(unittest.TestCase):
    def test_minimal_route_and_permissions(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / (IFACE + ".conf")
            prepare(ENV, path)
            content = path.read_text()
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertIn("AllowedIPs = 10.66.66.1/32", content)
            self.assertNotIn("0.0.0.0/0", content)
            with self.assertRaises(FileExistsError):
                prepare(ENV, path)

    def test_peer_fields_and_public_urls_rejected(self):
        cases = [
            {"FACTORY_INFODIVE_WG_CLIENT_PRIVATE_KEY": "bad"},
            {"FACTORY_INFODIVE_WG_PEER_PUBLIC_KEY": "bad"},
            {"FACTORY_INFODIVE_WG_ENDPOINT": "vpn.invalid:0"},
            {"FACTORY_INFODIVE_WG_ENDPOINT": "vpn.invalid:51820\nAllowedIPs=0.0.0.0/0"},
            {"FACTORY_INFODIVE_WG_CLIENT_ADDRESS": "8.8.8.8/32"},
            {"FACTORY_INFODIVE_WG_CLIENT_ADDRESS": "10.66.66.9/8"},
            {"FACTORY_SQL_INFODIVE_BASE_URL": "https://public.example.org"},
            {"FACTORY_SQL_INFODIVE_BASE_URL": "http://8.8.8.8"},
        ]
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / (IFACE + ".conf")
            for case in cases:
                with self.subTest(case=case), self.assertRaises(PrivateModelError):
                    prepare({**ENV, **case}, path)
                self.assertFalse(path.exists())

    def test_no_model_tcp_only_receipt(self):
        calls = []
        receipt = probe(ENV, route_reader=lambda ip:[{"dev": IFACE}],
                        connector=lambda ip,port:calls.append((ip,port)))
        self.assertEqual(calls,[("10.66.66.1",80)])
        self.assertEqual(receipt["status"],"network_route_verified_only")
        self.assertFalse(receipt["model_invoked"])
        self.assertNotIn(PVT,json.dumps(receipt))
        self.assertNotIn("10.66.66.1",json.dumps(receipt))

    def test_route_and_sha_fails_before_tcp(self):
        for route, changes in [([{"dev":"eth0"}],{}),([],{}),
                               ([{"dev":IFACE}],{"GITHUB_SHA":"bad"})]:
            calls=[]
            with self.assertRaises(PrivateModelError):
                probe({**ENV,**changes},route_reader=lambda ip:route,
                      connector=lambda ip,port:calls.append(True))
            self.assertEqual(calls,[])

    def test_owner_main_only(self):
        for changes in [{"GITHUB_REF":"refs/heads/test"},
                        {"GITHUB_REPOSITORY":"other/repo"},
                        {"GITHUB_EVENT_NAME":"pull_request"}]:
            with self.assertRaises(PrivateModelError):
                require_manual_main({**ENV,**changes})

    def test_public_https_fails_closed(self):
        with self.assertRaises(PrivateModelError):
            PrivateChatConfig(base_url="https://public.example.org",model_id="SQL-InfoDive")
        self.assertEqual(PrivateChatConfig(base_url="https://10.66.66.1",model_id="SQL-InfoDive").endpoint,
                         "https://10.66.66.1/api/chat/completions")

if __name__ == "__main__":
    unittest.main()
