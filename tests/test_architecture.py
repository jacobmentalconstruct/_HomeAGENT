"""Import-graph checks. Violations are unresolved ownership questions (docs/ARCHITECTURE.md)."""

import ast
import sys
import tempfile
import unittest
from pathlib import Path

from tests.support import ROOT

PACKAGE = "agent_harness"
INTERFACE_PART = "interfaces"
MAX_LINES = 400


def _module_name(src: Path, file: Path) -> str:
    parts = list(file.relative_to(src).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _imports(file: Path, module: str):
    """Yield (absolute dotted target, top-level name) for each import in file."""
    is_pkg = file.name == "__init__.py"
    tree = ast.parse(file.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = module.split(".")
                base = base if is_pkg else base[:-1]
                base = base[: len(base) - (node.level - 1)]
                target = ".".join(base + ([node.module] if node.module else []))
                names = [a.name for a in node.names] if not node.module else []
                for name in names:
                    yield f"{target}.{name}", PACKAGE
                if node.module:
                    yield target, PACKAGE
            else:
                target = node.module or ""
                yield target, target.split(".")[0]


def _is_interface(dotted: str) -> bool:
    return dotted.split(".")[1:2] == [INTERFACE_PART]


def analyze(src: Path, extra_files: tuple[Path, ...] = ()) -> dict:
    """Return violations found under src/PACKAGE (and any extra top-level files)."""
    modules = {_module_name(src, f): f for f in sorted((src / PACKAGE).rglob("*.py"))}
    graph, outside, core_to_interface, oversize = {}, [], [], []
    stdlib = set(sys.stdlib_module_names)
    for name, file in modules.items():
        if len(file.read_text(encoding="utf-8").splitlines()) > MAX_LINES:
            oversize.append(name)
        deps = set()
        for target, top in _imports(file, name):
            if top == PACKAGE:
                deps.add(target)
                if _is_interface(target) and not _is_interface(name):
                    core_to_interface.append((name, target))
            elif top not in stdlib:
                outside.append((name, top))
        graph[name] = {d for d in deps if d in modules and d != name}
    for file in extra_files:
        for _target, top in _imports(file, file.stem):
            if top not in stdlib and top != PACKAGE:
                outside.append((file.stem, top))
    return {"cycles": _cycles(graph), "outside": outside,
            "core_to_interface": core_to_interface, "oversize": oversize}


def _cycles(graph: dict) -> list[list[str]]:
    found, state, stack = [], {}, []

    def visit(node):
        state[node] = 1
        stack.append(node)
        for dep in sorted(graph.get(node, ())):
            if state.get(dep) == 1:
                found.append(stack[stack.index(dep):] + [dep])
            elif dep not in state:
                visit(dep)
        stack.pop()
        state[node] = 2

    for n in sorted(graph):
        if n not in state:
            visit(n)
    return found


class RepoArchitectureTests(unittest.TestCase):
    def test_real_tree_is_clean(self):
        result = analyze(ROOT / "src", extra_files=(ROOT / "harness.py",))
        self.assertEqual(result, {"cycles": [], "outside": [], "core_to_interface": [], "oversize": []})


class DetectionTests(unittest.TestCase):
    def tree(self, files: dict[str, str]) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for rel, text in files.items():
            f = root / "src" / PACKAGE / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(text, encoding="utf-8")
        return root / "src"

    def test_import_cycle_detected(self):
        src = self.tree({"__init__.py": "", "a.py": "from . import b\n", "b.py": "from . import a\n"})
        self.assertTrue(analyze(src)["cycles"])

    def test_core_importing_interfaces_detected(self):
        src = self.tree({"__init__.py": "", "interfaces/__init__.py": "", "interfaces/web.py": "",
                         "core.py": "from .interfaces import web\n"})
        self.assertEqual(analyze(src)["core_to_interface"][0][0], f"{PACKAGE}.core")

    def test_interfaces_importing_core_is_allowed(self):
        src = self.tree({"__init__.py": "", "core.py": "", "interfaces/__init__.py": "",
                         "interfaces/web.py": "from .. import core\n"})
        result = analyze(src)
        self.assertEqual((result["core_to_interface"], result["cycles"]), ([], []))

    def test_outside_import_detected(self):
        src = self.tree({"__init__.py": "", "a.py": "import requests\nimport json\n"})
        self.assertEqual(analyze(src)["outside"], [(f"{PACKAGE}.a", "requests")])

    def test_oversize_module_detected(self):
        src = self.tree({"__init__.py": "", "big.py": "x = 1\n" * (MAX_LINES + 1)})
        self.assertEqual(analyze(src)["oversize"], [f"{PACKAGE}.big"])


if __name__ == "__main__":
    unittest.main()
