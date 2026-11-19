"""No-network tests proving a green route cannot authorize SQL or model use."""
import json
import unittest
from decimal import Decimal
from unittest.mock import Mock
from ai_product_factory.private_model_vps_readiness import assess
from ai_product_factory.private_model_vps_route import PrivateVpsRouteError

SHA = "a"*40
ENV = {
    "FACTORY_SQL_INFODIVE_WORKER_SHA": SHA,
    "FACTORY_SQL_INFODIVE_BASE_URL": "http://10.66.66.1",
    "FACTORY_SQL_INFODIVE_MODEL": "SQL-InfoDive",
    "FACTORY_SQL_INFODIVE_HTTP_HOST": "chat.internal",
    "FACTORY_SQL_INFODIVE_WG_INTERFACE": "wg-ibm",
    "FACTORY_SQL_INFODIVE_ALLOW_PRIVATE_HTTP": "true",
    "FACTORY_SQL_INFODIVE_API_KEY": "test-only-never-print",
    "FACTORY_SQL_INFODIVE_PRICING_APPROVED": "true",
    "FACTORY_SQL_INFODIVE_INPUT_USD_PER_MILLION": "0",
    "FACTORY_SQL_INFODIVE_OUTPUT_USD_PER_MILLION": "0",
}
class Policy:
    reserve_usd = Decimal("0.50")

class Tests(unittest.TestCase):
    def test_all_green_never_enables_worker_or_model(self):
        calls=[]
        result=assess(ENV,head=SHA,
                      route=lambda base,**kw:calls.append(kw),
                      capacity=lambda:Policy(),tcp=True)
        self.assertEqual(calls,[{"interface":"wg-ibm","tcp":True}])
        self.assertEqual(result.network,"verified")
        self.assertEqual(result.budget,"available")
        self.assertEqual(result.worker,"not_provisioned")
        receipt=result.receipt()
        self.assertEqual(receipt["status"],"blocked")
        self.assertFalse(receipt["model_invoked"])
        self.assertFalse(receipt["run_claimed"])
        self.assertNotIn("test-only-never-print",json.dumps(receipt))
        self.assertNotIn("10.66.66.1",json.dumps(receipt))

    def test_wrong_sha_or_tunnel_stops_paid_ledger_read(self):
        reader=Mock()
        result=assess(
            ENV,head="b"*40,
            route=lambda *a,**kw: (_ for _ in ()).throw(PrivateVpsRouteError()),
            capacity=reader)
        reader.assert_not_called()
        self.assertEqual(result.code,"blocked")
        self.assertEqual(result.network,"blocked")
        self.assertEqual(result.budget,"unverified")

    def test_no_price_approval_stops_ledger_read(self):
        reader=Mock()
        result=assess(
            {**ENV,"FACTORY_SQL_INFODIVE_PRICING_APPROVED":"false"},
            head=SHA,route=lambda *a,**kw:None,capacity=reader)
        reader.assert_not_called()
        self.assertEqual(result.price,"unapproved")

    def test_budget_failure_never_returns_success(self):
        result=assess(
            ENV,head=SHA,route=lambda *a,**kw:None,
            capacity=lambda:(_ for _ in ()).throw(PermissionError("budget")))
        self.assertEqual(result.budget,"blocked")
        self.assertEqual(result.receipt()["status"],"blocked")

if __name__=="__main__":
    unittest.main()
