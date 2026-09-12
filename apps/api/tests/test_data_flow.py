from types import SimpleNamespace

from codeatlas.dependencies.data_flow import build_data_flow
from codeatlas.dependencies.graph import build_graph
from codeatlas.parsers.python import parse_python
from codeatlas.schemas.graph import GraphFile


def analyze(sources):
    files = []
    for path, source in sources.items():
        parsed = parse_python(source)
        files.append(
            SimpleNamespace(
                id=path,
                path=path,
                source=source,
                language="python",
                symbol_count=len(parsed.symbols),
                warning=None,
                imports=parsed.imports,
                import_references=parsed.import_references,
            )
        )
    graph = build_graph(
        "fixture", [GraphFile.model_validate(f, from_attributes=True) for f in files], []
    )
    return graph, build_data_flow(files, graph)


BASE = {
    "__init__.py": "",
    "data.py": "def load():\n    return [1, 2]\n",
    "model.py": "def train(values):\n    return values\n",
}


def test_return_argument_flow_has_caller_evidence_and_does_not_reverse_imports():
    dependency, flow = analyze(
        {
            **BASE,
            "main.py": (
                "from .data import load as read\nfrom .model import train\n"
                "def pipeline():\n    rows = read()\n    train(rows)\n"
            ),
        }
    )
    assert {(e.source, e.target) for e in dependency.edges} == {
        ("main.py", "data.py"),
        ("main.py", "model.py"),
    }
    assert [(e.source, e.target) for e in flow.edges] == [("data.py", "model.py")]
    evidence = flow.edges[0].evidence[0]
    assert evidence.context_file_path == "main.py"
    assert evidence.line == 5
    assert evidence.specifier == "train"
    assert flow.edges[0].relationship == "data_flow"


def test_local_helper_return_nested_call_and_keyword_argument():
    _, flow = analyze(
        {
            **BASE,
            "main.py": (
                "from .data import load\nfrom .model import train\n"
                "def prepare():\n    return load()\n"
                "def pipeline():\n    train(values=prepare())\n"
            ),
        }
    )
    assert [(e.source, e.target) for e in flow.edges] == [("data.py", "model.py")]


def test_imports_alone_do_not_imply_flow_and_overwrites_clear_provenance():
    for body in [
        "pass",
        "rows = load()\n    rows = 3\n    train(rows)",
        "rows = load()\n    rows = unknown(rows)\n    train(rows)",
        "f = lambda: train(load())",
        "train = unknown\n    train(load())",
    ]:
        _, flow = analyze(
            {
                **BASE,
                "main.py": "from .data import load\nfrom .model import train\ndef pipeline():\n    "
                + body,
            }
        )
        assert not flow.edges


def test_module_alias_and_branch_local_flow_without_joining_different_values():
    _, flow = analyze(
        {
            **BASE,
            "main.py": (
                "import data as source\nimport model as sink\n"
                "def pipeline(flag):\n    rows = source.load()\n"
                "    if flag:\n        sink.train(rows)\n        rows = 3\n"
                "    sink.train(rows)\n"
            ),
        }
    )
    assert len(flow.edges) == 1
    assert [e.line for e in flow.edges[0].evidence] == [6]


def test_analysis_never_executes_source_and_reports_parse_failure():
    _, flow = analyze({**BASE, "main.py": "raise RuntimeError('never run')", "broken.py": "def :"})
    assert not flow.edges
    assert any("broken.py" in note for note in flow.notes)


def test_global_rebinding_and_nested_function_shadowing_do_not_invent_calls():
    for source in [
        "from .data import load\nfrom .model import train\n"
        "train = other\ndef run():\n    train(load())",
        "from .data import load\nfrom .model import train\n"
        "def run():\n    def train(x): pass\n    train(load())",
    ]:
        _, flow = analyze({**BASE, "main.py": source})
        assert not flow.edges
