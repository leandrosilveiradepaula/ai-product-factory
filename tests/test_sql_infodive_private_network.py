"""Offline safety checks for reuse of the EXISTING VPS WireGuard tunnel."""
import json
import unittest
from unittest.mock import patch

from ai_product_factory.private_chat_provider import PrivateModelError
from ai_product_factory.private_model_vps_route import (
    PrivateVpsRouteError, verify_existing_vps_route,
)
from scripts.sql_infodive_private_network import check_vps

ENV={
    "FACTORY_SQL_INFODIVE_BASE_URL": "http://10.66.66.1",
    "FACTORY_SQL_INFODIVE_MODEL": "SQL-InfoDive",
    "FACTORY_SQL_INFODIVE_HTTP_HOST": "chat.internal",
    "FACTORY_SQL_INFODIVE_ALLOW_PRIVATE_HTTP": "true",
    "FACTORY_SQL_INFODIVE_WG_INTERFACE": "wg-ibm",
}


class ExistingVpsWireGuardTests(unittest.TestCase):
    def test_existing_tunnel_and_tcp_only_no_secrets_or_model(self):
        got=[]
        receipt=check_vps(ENV,route_reader=lambda ip:[{"dev":"wg-ibm"}],
                          tcp_dialer=lambda ip,port:got.append((ip,port)))
        self.assertEqual(got,[("10.66.66.1",80)])
        self.assertEqual(receipt["status"],"network_route_verified_only")
        self.assertEqual(receipt["interface"],"wg-ibm")
        self.assertFalse(receipt["model_invoked"])
        self.assertFalse(receipt["api_key_read"])
        self.assertNotIn("10.66.66.1",json.dumps(receipt))
        self.assertNotIn("Authorization",json.dumps(receipt))

    def test_default_internet_route_is_rejected_before_tcp(self):
        for routes in ([{"dev":"eth0"}],[],[{"dev":"wg-alt"}],
                       [{"dev":"wg-ibm"},{"dev":"eth0"}]):
            got=[]
            with self.subTest(routes=routes),self.assertRaises(PrivateVpsRouteError):
                check_vps(ENV,route_reader=lambda ip:routes,
                          tcp_dialer=lambda ip,port:got.append(ip))
            self.assertFalse(got)

    def test_no_public_or_loopback_addresses_or_invalid_interface(self):
        for url in ("http://8.8.8.8","https://example.org","http://127.0.0.1",
                    "file:///etc/passwd","http://10.66.66.1/more"):
            with self.subTest(url=url),self.assertRaises((PrivateModelError,PrivateVpsRouteError)):
                check_vps({**ENV,"FACTORY_SQL_INFODIVE_BASE_URL":url},
                          route_reader=lambda ip:[{"dev":"wg-ibm"}],
                          tcp_dialer=lambda ip,port:None)
        with self.assertRaises(PrivateVpsRouteError):
            check_vps({**ENV,"FACTORY_SQL_INFODIVE_WG_INTERFACE":"eth0"},
                      route_reader=lambda ip:[{"dev":"eth0"}],
                      tcp_dialer=lambda ip,port:None)

    def test_host_check_does_not_need_any_wireguard_key_or_api_bearer(self):
        forbidden_keys=("FACTORY_SQL_INFODIVE_API_KEY","FACTORY_INFODIVE_WG_CLIENT_PRIVATE_KEY",
                        "OPENAI_COMPATIBLE_SQL_API_KEY","LANGGRAPH_S2S_TOKEN")
        for key in forbidden_keys:
            self.assertNotIn(key, ENV)
        receipt=check_vps(ENV,route_reader=lambda ip:[{"dev":"wg-ibm"}],
                          tcp_dialer=lambda ip,port:None)
        self.assertFalse(receipt["api_key_read"])

    def test_missing_route_command_fails_closed(self):
        with patch("ai_product_factory.private_model_vps_route.subprocess.run",
                   side_effect=FileNotFoundError()):
            with self.assertRaises(PrivateVpsRouteError):
                verify_existing_vps_route("http://10.66.66.1",tcp=False)

if __name__=="__main__":
    unittest.main()
