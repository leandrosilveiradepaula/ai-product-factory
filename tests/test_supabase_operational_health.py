import json
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from ai_product_factory.supabase_operational_health import SupabaseOperationalHealthReader


class Response:
    def __init__(self,data): self.data=data
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self): return json.dumps(self.data).encode()


class Tests(unittest.TestCase):
    def test_maps_operational_health_without_side_effects(self):
        runs=[
            {"status":"running","attempt_count":1,"last_error":None,"lease_expires_at":"2026-01-01T00:00:00+00:00"},
            {"status":"failed","attempt_count":3,"last_error":"maximum attempts reached","lease_expires_at":None},
        ]
        usage=[{"estimated_cost":"1.25"},{"estimated_cost":None}]
        with patch("urllib.request.urlopen",side_effect=[Response(runs),Response(usage)]):
            reader=SupabaseOperationalHealthReader(url="https://x.supabase.co",secret_key="sb_secret_x")
            out=reader.read(budget=Decimal("5"),now=datetime(2026,9,26,tzinfo=timezone.utc))
        self.assertEqual(out.expired_leases,1)
        self.assertEqual(out.dead_letter_runs,1)
        self.assertEqual(out.failed_runs,1)
        self.assertEqual(out.unknown_cost_events,1)
        self.assertEqual(out.known_cost,Decimal("1.25"))


if __name__ == "__main__":
    unittest.main()
