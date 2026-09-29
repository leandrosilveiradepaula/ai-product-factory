from __future__ import annotations

import ast
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]
TESTS=ROOT/"tests"


def free_test_functions(path:Path)->list[tuple[str,int]]:
    tree=ast.parse(path.read_text(encoding="utf-8"),filename=str(path))
    return [
        (node.name,node.lineno)
        for node in tree.body
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name.startswith("test_")
    ]


def main()->int:
    offenders=[]
    for path in sorted(TESTS.glob("test_*.py")):
        for name,line in free_test_functions(path):
            offenders.append((path.relative_to(ROOT).as_posix(),name,line))
    if offenders:
        print("Function-style tests are not collected by unittest discover:")
        for path,name,line in offenders:
            print(f"{path}:{line}: {name}")
        print(f"TOTAL_UNCOLLECTED={len(offenders)}")
        return 1
    print("TEST_COLLECTION_GUARD_OK")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
