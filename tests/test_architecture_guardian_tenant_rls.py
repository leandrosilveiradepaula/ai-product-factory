"""SQL authorization architecture-guardian regression across greenfield tenants.

No RLS policy, grant or synthetic database is changed in this test.
"""
import unittest

from ai_product_factory.architecture_guardian import scan_pull_request_files


def scan(path, text):
    return scan_pull_request_files([{
        "filename":path,"status":"added",
        "patch":"\n".join("+"+line for line in text.splitlines()),
    }])


MIGRATION = """
alter table public.studio_projects enable row level security;
alter table public.studio_memberships enable row level security;
grant select,insert,update on public.studio_projects to authenticated;
grant select on public.studio_memberships to authenticated;
create policy projects_visible on public.studio_projects for select
to authenticated using (
  exists (select 1 from public.studio_memberships m
  where m.organization_id=studio_projects.organization_id
  and m.user_id=(select auth.uid()))
);
create policy projects_add on public.studio_projects for insert
to authenticated with check (
  exists (select 1 from public.studio_memberships m
  where m.organization_id=studio_projects.organization_id
  and m.user_id=(select auth.uid()))
);
create policy projects_edit on public.studio_projects for update
to authenticated using (
  exists (select 1 from public.studio_memberships m
  where m.organization_id=studio_projects.organization_id
  and m.user_id=(select auth.uid()))
) with check (
  exists (select 1 from public.studio_memberships m
  where m.organization_id=studio_projects.organization_id
  and m.user_id=(select auth.uid()))
);
create policy membership_self on public.studio_memberships for select
to authenticated using (user_id=(select auth.uid()));
"""


class TenantSecurityClassifier(unittest.TestCase):
    def test_real_tenant_membership_and_explicit_rls_is_not_public_grant(self):
        report=scan("supabase/migrations/tenant.sql",MIGRATION)
        self.assertEqual(report.evidence["blocking_findings"],0)
        self.assertNotIn("public_rls_policy",{x["code"] for x in report.findings})
        self.assertNotIn("permissive_public_grant",{x["code"] for x in report.findings})

    def test_real_disposable_auth_bootstrap_is_not_public_table_access(self):
        text="""create schema auth;
grant usage on schema auth to authenticated;
grant execute on function auth.uid() to authenticated;
grant usage on schema public to authenticated;
"""
        out=scan("supabase/tests/bootstrap_auth.sql",text)
        self.assertEqual(out.evidence["blocking_findings"],0)

    def test_negative_service_key_marker_is_not_long_random_credential(self):
        out=scan("src/persistence/supabase-tenancy.test.ts",
                 'const invalidPublishable="sb_secret_unacceptable";')
        self.assertEqual(out.evidence["blocking_findings"],0)
        assert not out.findings

    def test_long_realistic_supabase_secret_literal_is_critical(self):
        out=scan("src/app/server.ts",
                 'const stolen="sb_secret_'+("a1"*22)+'";')
        self.assertIn("supabase_secret",{x["code"] for x in out.findings})
        self.assertGreater(out.evidence["blocking_findings"],0)

    def test_unrestricted_authenticated_polices_fail_closed(self):
        for fragment in [
            "create policy p on public.x for select to authenticated using (true);",
            "create policy p on public.x for select to authenticated using (auth.uid() is not null);",
            "create policy p on public.x for insert to authenticated with check (true);",
            "create policy p on public.x for update to authenticated using (user_id=auth.uid());",
            "create policy p on public.x for select to anon using (user_id=auth.uid());",
            "create policy p on public.x for select to public using (true);",
            "create policy p on public.x for select to authenticated using (user_id=auth.uid());",
        ]:
            # If policies don't have a relational tenant/owner identity, fail closed;
            # the last case exercises *positive* direct owner filtering instead.
            expected_clean=(fragment == "create policy p on public.x for select to authenticated using (user_id=auth.uid());")
            with self.subTest(fragment=fragment):
                out=scan("supabase/migrations/x.sql",fragment)
                codes={x["code"] for x in out.findings}
                if expected_clean:self.assertNotIn("public_rls_policy",codes)
                else:self.assertIn("public_rls_policy",codes)

    def test_authenticated_invoker_rpc_with_explicit_revocation_and_tenant_rls(self):
        # A real REST RPC grant is necessary for an end-user JWT, and may
        # be safe only with invoker+empty search_path+full tenant RLS.
        text="""
        create table public.tenant_items(id uuid,user_id uuid);
        alter table public.tenant_items enable row level security;
        alter table public.tenant_items force row level security;
        create policy owner_items on public.tenant_items for select
        to authenticated using (user_id=(select auth.uid()));
        create or replace function public.read_items(p_id uuid)
        returns boolean language plpgsql security invoker set search_path='' as $scope$
        begin
          return exists(select 1 from public.tenant_items
            where id=p_id and user_id=(select auth.uid()));
        end;
        $scope$;
        revoke all on function public.read_items(uuid) from public,anon;
        grant execute on function public.read_items(uuid) to authenticated;
        """
        out=scan("supabase/migrations/scoped_rpc.sql",text)
        self.assertEqual(out.evidence["blocking_findings"],0,out.findings)
        self.assertNotIn("permissive_public_grant",{x["code"] for x in out.findings})

    def test_public_or_unbounded_rpc_grants_never_become_safe(self):
        base="""
        alter table public.tenant_items enable row level security;
        alter table public.tenant_items force row level security;
        create policy owner_items on public.tenant_items for select
          to authenticated using (user_id=(select auth.uid()));
        create or replace function public.read_items(p_id uuid)
        returns boolean language plpgsql security invoker set search_path='' as $scope$
        begin
          return exists(select 1 from public.tenant_items
            where user_id=(select auth.uid()));
        end;
        $scope$;
        revoke all on function public.read_items(uuid) from public,anon;
        grant execute on function public.read_items(uuid) to authenticated;
        """
        bad=[
            base.replace("security invoker","security definer"),
            base.replace("set search_path=''","set search_path='public'"),
            base.replace("revoke all on function public.read_items(uuid) from public,anon;",""),
            base.replace("force row level security;","disable row level security;"),
            base.replace("enable row level security;",""),
            base.replace("using (user_id=(select auth.uid()))","using (true)"),
            base.replace("to authenticated;\n", "to anon;\n"),
            base.replace("grant execute on function public.read_items(uuid)",
                         "grant all on function public.read_items(uuid)"),
            base.replace("where user_id=(select auth.uid())",
                         "where id=p_id from public.unscoped_data"),
            base.replace("security invoker set search_path='' as $scope$",
                         "security invoker set search_path='' as $scope$\n"
                         "execute 'delete from public.tenant_items';"),
            base.replace("revoke all on function public.read_items(uuid)",
                         "revoke all on function public.other_items(uuid)"),
        ]
        for idx,fragment in enumerate(bad):
            with self.subTest(case=idx):
                out=scan("supabase/migrations/scope.sql",fragment)
                self.assertGreater(out.evidence["blocking_findings"],0)
                self.assertIn("permissive_public_grant",
                              {x["code"] for x in out.findings})

    def test_unsafe_grants_and_missing_rls_fail_closed(self):
        for sql in [
            "grant select on public.studio_projects to anon;",
            "grant all on public.studio_projects to authenticated;",
            "grant update on public.studio_projects to public;",
            "grant select on public.studio_projects to authenticated;",
            "alter table public.a enable row level security;\ngrant select on public.a,public.b to authenticated;",
            "grant select on public.studio_projects to authenticated",
        ]:
            with self.subTest(sql=sql):
                out=scan("supabase/migrations/x.sql",sql)
                self.assertGreater(out.evidence["blocking_findings"],0)

    def test_private_key_and_rls_disable_are_still_critical(self):
        out=scan("supabase/migrations/x.sql", "alter table public.a disable row level security;")
        self.assertIn("disable_rls",{x["code"] for x in out.findings})

    def test_dependency_revisions_still_raise_evidence_warning(self):
        out=scan("package-lock.json",'"lockfileVersion":3,')
        self.assertIn("dependency_surface_changed",{x["code"] for x in out.findings})
        self.assertFalse(out.evidence["coverage"]["dependency_vulnerability_scan"])

if __name__=="__main__":
    unittest.main()
