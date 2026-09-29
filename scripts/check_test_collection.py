from __future__ import annotations

import ast
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]
TESTS=ROOT/"tests"


def _is_testcase_class(node:ast.ClassDef)->bool:
    for base in node.bases:
        if isinstance(base,ast.Attribute) and base.attr=="TestCase":
            return True
        if isinstance(base,ast.Name) and base.id=="TestCase":
            return True
    return False


def uncollected_tests(path:Path)->list[tuple[str,int,str]]:
    tree=ast.parse(path.read_text(encoding="utf-8"),filename=str(path))
    offenders=[]

    for node in tree.body:
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            offenders.append((node.name,node.lineno,"module_level"))

        if isinstance(node,ast.ClassDef):
            testcase=_is_testcase_class(node)
            for child in node.body:
                if isinstance(child,(ast.FunctionDef,ast.AsyncFunctionDef)) and child.name.startswith("test_") and not testcase:
                    offenders.append((child.name,child.lineno,"non_testcase_class"))

        for descendant in ast.walk(node):
            if descendant is node:
                continue
            if not isinstance(descendant,(ast.FunctionDef,ast.AsyncFunctionDef)) or not descendant.name.startswith("test_"):
                continue
            if isinstance(node,ast.ClassDef) and descendant in node.body:
                continue
            if descendant in tree.body:
                continue
            offenders.append((descendant.name,descendant.lineno,"nested"))

    return sorted(set(offenders),key=lambda x:(x[1],x[0],x[2]))


def main()->int:
    offenders=[]
    for path in sorted(TESTS.glob("test_*.py")):
        for name,line,kind in uncollected_tests(path):
            offenders.append((path.relative_to(ROOT).as_posix(),name,line,kind))
    if offenders:
        print("Tests not collected by unittest discover:")
        for path,name,line,kind in offenders:
            print(f"{path}:{line}: {name} [{kind}]")
        print(f"TOTAL_UNCOLLECTED={len(offenders)}")
        return 1
    print("TEST_COLLECTION_GUARD_OK")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
