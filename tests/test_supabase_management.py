import json
import unittest

from ai_product_factory.supabase_management import (
    SupabaseManagementClient,
    SupabaseProjectBinding,
    SupabaseProvisionRequest,
    create_project,
)


class Transport:
    def __init__(self):
        self.calls=[]
    def __call__(self,method,url,headers,body):
        self.calls.append((method,url,headers,body))
        return 201,json.dumps({"ok":True}).encode()


class SupabaseManagementTests(unittest.TestCase):
    def test_read_only_query_uses_management_read_only_endpoint(self):
        transport=Transport()
        client=SupabaseManagementClient(SupabaseProjectBinding("abc","secret","read"),transport=transport)
        client.read_only_query("select 1")
        method,url,headers,body=transport.calls[0]
        self.assertEqual(method,"POST")
        self.assertTrue(url.endswith("/v1/projects/abc/database/query/read-only"))
        self.assertEqual(json.loads(body),{"query":"select 1"})
        self.assertNotIn("secret",url)

    def test_write_is_fail_closed_for_read_binding(self):
        client=SupabaseManagementClient(SupabaseProjectBinding("abc","secret","read"),transport=Transport())
        with self.assertRaises(PermissionError):
            client.write_query("select 1",approved=True)

    def test_write_requires_explicit_approval_even_with_write_binding(self):
        client=SupabaseManagementClient(SupabaseProjectBinding("abc","secret","read_write"),transport=Transport())
        with self.assertRaises(PermissionError):
            client.write_query("select 1")

    def test_create_project_requires_human_cost_approval(self):
        request=SupabaseProvisionRequest("new-app","org")
        with self.assertRaises(PermissionError):
            create_project("secret",request,"db-password",transport=Transport())

    def test_create_project_uses_smart_region_after_approval(self):
        transport=Transport()
        request=SupabaseProvisionRequest("new-app","org")
        create_project("secret",request,"db-password",approved_cost=True,transport=transport)
        method,url,headers,body=transport.calls[0]
        self.assertEqual(method,"POST")
        self.assertTrue(url.endswith("/v1/projects"))
        payload=json.loads(body)
        self.assertEqual(payload["region_selection"],{"type":"smartGroup","code":"americas"})
        self.assertNotIn("desired_instance_size",payload)


if __name__=="__main__":
    unittest.main()
