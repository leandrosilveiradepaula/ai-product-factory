from __future__ import annotations

import argparse
import json
import os
import sys

from ai_product_factory.supabase_management import SupabaseManagementClient, SupabaseProjectBinding


def main() -> int:
    parser=argparse.ArgumentParser(description="Verify bounded read access to a project Supabase instance.")
    parser.add_argument("--project-ref",required=True)
    args=parser.parse_args()
    token=os.environ.get("FACTORY_PROJECT_SUPABASE_ACCESS_TOKEN","").strip()
    if not token:
        print(json.dumps({"ok":False,"reason":"missing_access_token"}))
        return 2

    client=SupabaseManagementClient(SupabaseProjectBinding(args.project_ref,token,"read"))
    project=client.project()
    observed=str(project.get("ref") or project.get("id") or "").strip()
    if observed != args.project_ref:
        print(json.dumps({"ok":False,"reason":"project_ref_mismatch","expected":args.project_ref,"observed":observed}))
        return 3

    result=client.read_only_query("select current_database() as database_name, current_user as database_user")
    print(json.dumps({"ok":True,"project_ref":args.project_ref,"read_only_query_verified":True,"result_shape":type(result).__name__}))
    return 0


if __name__=="__main__":
    sys.exit(main())
