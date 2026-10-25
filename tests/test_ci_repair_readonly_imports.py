"""Generic exact-SHA import symbol lookup for bounded TypeScript CI repairs."""
import unittest
from unittest.mock import MagicMock

from ai_product_factory.change_set_worker import ChangeSetBuilderWorker
from ai_product_factory.ci_repair_readonly_imports import resolve_verified_readonly_imports
from ai_product_factory.work_unit_context import enforce_write_scopes

SHA="a"*40
PAGE="src/app/(dashboard)/service-desk/page.tsx"
SOURCE="src/lib/session.ts"
OTHER="src/lib/auth/session.ts"
SCOPES=[PAGE,"src/components/layout/Sidebar.tsx","src/lib/service-desk/entry-guard.ts"]
DIAG=PAGE+":2:28 TS2307 import=@/lib/auth/session"
FILES={
  PAGE:"import { redirect } from 'next/navigation';\n"
       "import { getSession } from '@/lib/auth/session';\n"
       "export async function Page() { return getSession(); }\n",
  SOURCE:"export async function getSession() { return { isLoggedIn: true }; }\n",
  "src/components/layout/Sidebar.tsx":"export const Sidebar=()=>null;\n",
  "src/lib/service-desk/entry-guard.ts":"export function decide() {return true;}\n",
  "AGENTS.md":"Read before committing.\n",
  "docs/codex/CURRENT_TASK.md":"Only edit scoped files.\n",
}


def src(diag=DIAG):
    return {
      "project_kind":"existing","project_key":"sample-crm",
      "repository":"owner/project","wave":2,
      "plan_task_key":"ci-repair-2",
      "task":{"title":"Repair verified TypeScript import"},
      "assignment":{"scope_keys":list(SCOPES),"context_paths":[PAGE]},
      "repair":{"repair_kind":"ci","verified_typecheck_diagnostics":[diag]},
    }


def github(files=None):
    files=files if files is not None else FILES
    adapter=MagicMock()
    adapter.list_file_paths.return_value=tuple(sorted(files))
    def read(path,*,ref):
        assert ref==SHA,(path,ref)
        assert path in files,path
        return files[path]
    adapter.get_file_text.side_effect=read
    return adapter


class ReadonlyTypeScriptImportTests(unittest.TestCase):
    def test_unambiguous_export_verified_at_exact_sha(self):
        h=github()
        evidence=resolve_verified_readonly_imports(
            github=h,source=src(),base_commit=SHA,
            all_paths=h.list_file_paths(ref=SHA),
        )
        self.assertEqual([(x.symbol,x.exported_from) for x in evidence],
                         [("getSession",SOURCE)])
        refs=[call.kwargs["ref"] for call in h.get_file_text.call_args_list]
        self.assertEqual(refs,[SHA,SHA])

    def test_generic_non_crm_export(self):
        page="src/app/accounts/page.ts"
        module="src/lib/profile.ts"
        files={
            page:"import { loadProfile } from '@/lib/nonexistent';\n",
            module:"export async function loadProfile() { return {}; }\n",
        }
        h=github(files)
        context=src(page+":1:10 TS2307 import=@/lib/nonexistent")
        context["assignment"]["scope_keys"]=[page]
        result=resolve_verified_readonly_imports(
            github=h,source=context,base_commit=SHA,all_paths=tuple(files),
        )
        self.assertEqual(result[0].exported_from,module)

    def test_worker_adds_full_dependency_as_required_readonly_context(self):
        h=github()
        worker=ChangeSetBuilderWorker(github=h,store=MagicMock(),producer=MagicMock(),impact_engine=MagicMock(),provenance=MagicMock())
        enriched,_=worker._resolved_repository_context(source=src(),base_commit=SHA)
        self.assertEqual(enriched["assignment"]["scope_keys"],SCOPES)
        self.assertEqual(enriched["ci_verified_readonly_import_paths"],[SOURCE])
        self.assertIn(SOURCE,enriched["assignment"]["context_paths"])
        self.assertIn("getSession is exported from "+SOURCE,
                      " ".join(enriched["constraints"]))
        snapshot,unsafe=worker._repository_snapshot_with_safety(
            source=enriched,base_commit=SHA
        )
        self.assertEqual(snapshot[SOURCE],FILES[SOURCE])
        self.assertNotIn(SOURCE,unsafe)
        self.assertIn(SOURCE,snapshot)
        self.assertNotIn(SOURCE,enriched["assignment"]["scope_keys"])
        with self.assertRaises(PermissionError):
            enforce_write_scopes([SOURCE],enriched["assignment"]["scope_keys"])

    def test_ambiguous_or_unexported_module_blocks_before_model(self):
        cases=[
          {**FILES,OTHER:"export async function getSession() {return null;}\n"},
          {**FILES,SOURCE:"const getSession=()=>false;\n"},
        ]
        for files in cases:
            with self.subTest(files=tuple(files)):
                h=github(files)
                with self.assertRaisesRegex(PermissionError,"no unique"):
                    resolve_verified_readonly_imports(
                        github=h,source=src(),base_commit=SHA,
                        all_paths=h.list_file_paths(ref=SHA),
                    )

    def test_line_or_alias_drift_cannot_authorize_a_dependency(self):
        cases=[
          src(PAGE+":2:28 TS2307 import=@/lib/other"),
          src(PAGE+":9:28 TS2307 import=@/lib/auth/session"),
          src("src/app/another/page.tsx:2:28 TS2307 import=@/lib/auth/session"),
        ]
        for context in cases:
            with self.subTest(context=context):
                with self.assertRaises(PermissionError):
                    resolve_verified_readonly_imports(
                        github=github(),source=context,base_commit=SHA,
                        all_paths=tuple(FILES),
                    )

    def test_missing_module_cannot_expand_write_scopes_or_guess(self):
        files={**FILES}
        files.pop(SOURCE)
        with self.assertRaisesRegex(PermissionError,"no unique"):
            resolve_verified_readonly_imports(
                github=github(files),source=src(),base_commit=SHA,
                all_paths=tuple(files),
            )

    def test_bounded_candidates_large_files_and_redaction_fail(self):
        too_many={**FILES}
        for i in range(17):
            too_many[f"src/m{i}/session.ts"]="export const noop=1;\n"
        with self.assertRaisesRegex(PermissionError,"candidates exceed"):
            resolve_verified_readonly_imports(
                github=github(too_many),source=src(),base_commit=SHA,
                all_paths=tuple(too_many),
            )
        files={**FILES,SOURCE:"export async function getSession() {}\n"+"x"*16385}
        with self.assertRaisesRegex(PermissionError,"safe byte limit"):
            resolve_verified_readonly_imports(
                github=github(files),source=src(),base_commit=SHA,
                all_paths=tuple(files),
            )
        files={**FILES,SOURCE:"export async function getSession() {} // sb_secret_veryveryprivate\n"}
        with self.assertRaisesRegex(PermissionError,"redacted"):
            resolve_verified_readonly_imports(
                github=github(files),source=src(),base_commit=SHA,
                all_paths=tuple(files),
            )

    def test_non_repair_is_unchanged(self):
        context=src()
        context["repair"]={}
        result=resolve_verified_readonly_imports(
            github=github(),source=context,base_commit=SHA,all_paths=tuple(FILES)
        )
        self.assertEqual(result,())


if __name__=="__main__":
    unittest.main()
