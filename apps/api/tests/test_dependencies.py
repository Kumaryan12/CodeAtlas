import pytest

from codeatlas.dependencies.config import read_resolution_config
from codeatlas.dependencies.graph import build_graph, find_cycles
from codeatlas.parsers.javascript import parse_javascript
from codeatlas.parsers.python import parse_python
from codeatlas.parsers.types import ImportReference, ResolutionConfig
from codeatlas.schemas.graph import GraphEdge, GraphFile


def file(path, source="", *, legacy=False):
    language = (
        "python"
        if path.endswith(".py")
        else "typescript"
        if path.endswith((".ts", ".tsx"))
        else "javascript"
    )
    parsed = (
        parse_python(source)
        if language == "python"
        else parse_javascript(
            source, typescript=language == "typescript", tsx=path.endswith(".tsx")
        )
    )
    return GraphFile(
        id=path,
        path=path,
        language=language,
        imports=parsed.imports,
        import_references=None if legacy else parsed.import_references,
    )


def pairs(graph):
    return {(edge.source, edge.target) for edge in graph.edges}


def test_python_package_imports_and_child_modules():
    graph = build_graph(
        "repo",
        [
            file("apps/api/pkg/__init__.py"),
            file("apps/api/pkg/routes.py", "from . import service\nfrom pkg.service import login"),
            file("apps/api/pkg/service.py", "def login(): pass"),
        ],
        [],
    )
    assert pairs(graph) == {
        ("apps/api/pkg/routes.py", "apps/api/pkg/__init__.py"),
        ("apps/api/pkg/routes.py", "apps/api/pkg/service.py"),
    }
    service = next(edge for edge in graph.edges if edge.target.endswith("service.py"))
    assert [e.line for e in service.evidence] == [1, 2]
    assert not graph.unresolved


def test_python_absolute_and_parent_relative_imports():
    graph = build_graph(
        "repo",
        [
            file("pkg/__init__.py"),
            file("pkg/shared.py"),
            file("pkg/sub/__init__.py"),
            file("pkg/sub/a.py", "from ..shared import Thing\nimport os"),
        ],
        [],
    )
    assert ("pkg/sub/a.py", "pkg/shared.py") in pairs(graph)
    assert graph.unresolved[0].specifier == "os"
    assert graph.unresolved[0].reason == "external_or_unresolved"


def test_python_src_layout_and_ambiguous_roots():
    graph = build_graph("repo", [file("src/pkg/a.py", "import pkg.b"), file("src/pkg/b.py")], [])
    assert pairs(graph) == {("src/pkg/a.py", "src/pkg/b.py")}
    graph = build_graph(
        "repo",
        [
            file("entry.py", "import pkg.a"),
            file("one/pkg/__init__.py"),
            file("one/pkg/a.py"),
            file("two/pkg/__init__.py"),
            file("two/pkg/a.py"),
        ],
        [],
    )
    assert not graph.edges
    assert graph.unresolved[0].reason == "ambiguous_local_module"


def test_javascript_relative_directory_reexport_and_type_extension():
    graph = build_graph(
        "repo",
        [
            file(
                "web/a.ts", "import './b.js'; export * from './folder'; import React from 'react';"
            ),
            file("web/b.ts"),
            file("web/folder/index.ts"),
        ],
        [],
    )
    assert pairs(graph) == {("web/a.ts", "web/b.ts"), ("web/a.ts", "web/folder/index.ts")}
    assert graph.unresolved[0].specifier == "react"
    assert any(e.kind == "javascript_export" for edge in graph.edges for e in edge.evidence)


def test_alias_uses_nearest_config_not_similarly_named_app():
    configs = [
        ResolutionConfig(path="apps/web/tsconfig.json", paths={"@/*": ["src/*"]}),
        ResolutionConfig(path="apps/admin/tsconfig.json", paths={"@/*": ["src/*"]}),
    ]
    graph = build_graph(
        "repo",
        [
            file("apps/web/src/page.ts", "import '@/lib/auth';"),
            file("apps/web/src/lib/auth.ts"),
            file("apps/admin/src/lib/auth.ts"),
        ],
        configs,
    )
    assert pairs(graph) == {("apps/web/src/page.ts", "apps/web/src/lib/auth.ts")}
    assert graph.edges[0].evidence[0].resolution == "typescript_paths"


def test_exact_alias_beats_wildcard_and_fallback_targets():
    config = ResolutionConfig(
        path="tsconfig.json", paths={"@/*": ["src/*"], "@/auth": ["missing", "special/auth"]}
    )
    graph = build_graph(
        "repo",
        [file("main.ts", "import '@/auth';"), file("src/auth.ts"), file("special/auth.ts")],
        [config],
    )
    assert pairs(graph) == {("main.ts", "special/auth.ts")}


def test_base_url_and_alias_escape():
    config = ResolutionConfig(path="tsconfig.json", base_url="src", paths={"bad/*": ["../../*"]})
    graph = build_graph(
        "repo",
        [file("src/a.ts", "import 'lib/b'; import 'bad/secret';"), file("src/lib/b.ts")],
        [config],
    )
    assert pairs(graph) == {("src/a.ts", "src/lib/b.ts")}
    assert len(graph.unresolved) == 1


def test_ambiguous_js_and_missing_local_are_explicit():
    graph = build_graph(
        "repo", [file("a.ts", "import './b'; import './missing';"), file("b.js"), file("b.ts")], []
    )
    assert not graph.edges
    assert {issue.reason for issue in graph.unresolved} == {
        "ambiguous_local_module",
        "missing_local_module",
    }


def test_cycles_and_deduplication():
    graph = build_graph(
        "repo",
        [
            file("a.js", "import './b'; import './b';"),
            file("b.js", "import './a';"),
            file("alone.js"),
        ],
        [],
    )
    assert graph.cycles == [["a.js", "b.js"]]
    assert len(graph.edges) == 2
    assert all(edge.in_cycle for edge in graph.edges)
    assert len(graph.nodes) == 3
    # Same specifier and line are one observation; different lines remain distinct.
    assert len(next(e for e in graph.edges if e.source == "a.js").evidence) == 1


def test_long_cycles_are_not_recursive():
    ids = [str(i) for i in range(2000)]
    edges = [
        GraphEdge(id=str(i), source=ids[i], target=ids[(i + 1) % len(ids)]) for i in range(len(ids))
    ]
    assert len(find_cycles(ids, edges)[0]) == 2000


def test_legacy_graph_is_readable_without_claiming_full_coverage():
    graph = build_graph(
        "repo", [file("a.js", "import './b';", legacy=True), file("b.js", legacy=True)], None
    )
    assert pairs(graph) == {("a.js", "b.js")}
    assert graph.legacy_files == 2
    assert graph.edges[0].evidence[0].line is None
    assert any("Legacy" in note for note in graph.notes)


@pytest.mark.parametrize(
    "source",
    [
        '{"extends":"./other.json","compilerOptions":{"paths":{"@/*":["src/*"]}}}',
        "{/*comment*/}",
        "[]",
    ],
)
def test_config_unsupported_features_are_reported(source):
    assert read_resolution_config("tsconfig.json", source).warning


def test_config_never_follows_extends_or_reads_files(tmp_path):
    config = read_resolution_config(
        "tsconfig.json",
        '{"extends":"/etc/passwd","compilerOptions":{"baseUrl":".","paths":{"@/*":["src/*"]}}}',
    )
    assert config.paths == {"@/*": ["src/*"]}
    assert config.warning


def test_python_relative_escape_and_js_url_stay_unresolved():
    graph = build_graph(
        "repo",
        [
            file("pkg/a.py", "from ...private import secret"),
            file("a.ts", "import '../../outside'; import 'https://evil.example/code';"),
        ],
        [],
    )
    assert not graph.edges
    assert len(graph.unresolved) == 3


def test_empty_graph_and_self_cycle():
    assert build_graph("repo", [], []).nodes == []
    graph = build_graph("repo", [file("a.py", "import a")], [])
    assert graph.cycles == [["a.py"]]


def test_named_python_import_reference_keeps_actual_module_not_alias():
    refs = parse_python("from . import service as svc\nimport os.path as path").import_references
    assert refs[0] == ImportReference(specifier=".", kind="python_from", names=["service"], line=1)
    assert refs[1].specifier == "os.path"


def test_namespace_roots_without_init_files_and_unrelated_shadow_module():
    graph = build_graph(
        "repo",
        [
            file("backend/app/routes.py", "from app.service import login\nimport json"),
            file("backend/app/service.py", "def login(): pass"),
            file("other/tools/json.py"),
        ],
        [],
    )
    assert pairs(graph) == {("backend/app/routes.py", "backend/app/service.py")}
    assert graph.unresolved[0].specifier == "json"
