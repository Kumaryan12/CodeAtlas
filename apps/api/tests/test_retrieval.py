from dataclasses import replace
from uuid import uuid4

from sqlalchemy.orm import Session
from test_qa import FixtureProvider, imported

from codeatlas.api.qa import provider_dependency
from codeatlas.models.repository import CodeSymbol, Repository, RepositoryFile
from codeatlas.retrieval.chunks import Chunk
from codeatlas.retrieval.hybrid import bm25, retrieve, tokens


def chunk(name, file=None, source=None):
    path = file or name + ".py"
    return Chunk(
        name, path, path, "python", name, "function", 1, 2, source or f"def {name}():\n    pass"
    )


def test_identifier_tokenization_and_keyword_ranking():
    assert {"verifypassword", "verify", "password", "verify_password"} <= set(
        tokens("verifyPassword verify_password")
    )
    docs = [
        chunk("login", source="validate credentials password"),
        chunk("catalog", source="search stock inventory"),
    ]
    scores = bm25("password credentials", docs)
    assert scores[0] > scores[1] == 0
    assert bm25("how does the", docs) == [0, 0]


def test_exact_symbol_overrides_misleading_semantics_without_substring_matches():
    docs = [chunk("login"), chunk("login_extra"), chunk("catalog")]
    vectors = {"login": [0, 1], "login_extra": [1, 0], "catalog": [0.8, 0.2]}
    baseline = retrieve("Explain login()", docs, [1, 0], vectors, [], strategy="semantic")
    hybrid = retrieve("Explain login()", docs, [1, 0], vectors, [])
    assert baseline[0].chunk.id == "login_extra"
    assert hybrid[0].chunk.id == "login"
    assert hybrid[0].symbol_score == 2
    assert next(r for r in hybrid if r.chunk.id == "login_extra").symbol_score == 0


def test_exact_path_disambiguates_duplicate_symbols_and_ties_are_stable():
    docs = [
        replace(chunk("login", file="routes/auth.py"), id="route"),
        replace(chunk("login", file="services/auth.py"), id="service"),
    ]
    vectors = {"route": [1, 0], "service": [1, 0]}
    assert retrieve("services/auth.py login", docs, [1, 0], vectors, [])[0].chunk.id == "service"
    forward = retrieve("unrelated", docs, [1, 0], vectors, [])
    backward = retrieve("unrelated", docs[::-1], [1, 0], vectors, [])
    assert [r.chunk.id for r in forward] == [r.chunk.id for r in backward]


def test_graph_expands_one_hop_at_most_two_new_files_without_duplicates():
    docs = [chunk(f"seed{i}", file="route.py") for i in range(6)] + [
        chunk("auth"),
        chunk("db"),
        chunk("remote"),
    ]
    vectors = {c.id: [1, 0] if c.path == "route.py" else [0, 1] for c in docs}
    edges = [
        ("route.py", "auth.py"),
        ("db.py", "route.py"),
        ("auth.py", "remote.py"),
        ("route.py", "route.py"),
    ]
    result = retrieve("seed0", docs, [1, 0], vectors, edges)
    assert len(result) == len({r.chunk.id for r in result}) == 6
    expanded = [r for r in result if r.reason == "dependency"]
    assert {r.chunk.path for r in expanded} == {"auth.py", "db.py"}
    assert all(r.via_file_id == "route.py" for r in expanded)
    assert all(r.chunk.path != "remote.py" for r in result)
    assert len(retrieve("seed0", docs, [1, 0], vectors, edges, k=1)) == 1


def test_expansion_can_reach_neighbor_outside_top_fifty_channels():
    docs = [chunk(f"seed{i:02d}", file="route.py") for i in range(60)] + [chunk("zzz")]
    vectors = {c.id: [1, 0] if c.path == "route.py" else [0, 1] for c in docs}
    result = retrieve("seed00", docs, [1, 0], vectors, [("route.py", "zzz.py")])
    assert any(r.chunk.id == "zzz" and r.reason == "dependency" for r in result)


def test_lexical_evaluation_has_no_fake_semantic_scores_or_unrelated_fill():
    docs = [chunk("login"), chunk("catalog")]
    result = retrieve("login", docs, None, {}, [])
    assert [r.chunk.id for r in result] == ["login"]
    assert result[0].semantic_score is None
    assert retrieve("nonexistentfeature", docs, None, {}, []) == []


def test_preview_and_ask_share_retrieval_and_only_ask_generates_answer(api, fake_download):
    prefix = imported(api)
    provider = FixtureProvider()
    api.app.dependency_overrides[provider_dependency] = lambda: provider
    assert api.post(prefix + "/retrieve", json={"question": "login"}).status_code == 409
    api.post(prefix + "/index", json={})
    result = api.post(prefix + "/retrieve", json={"question": "login"})
    assert result.status_code == 200, result.text
    preview = result.json()
    assert preview["strategy"] == "hybrid"
    assert len(preview["hits"]) <= 6
    assert not hasattr(provider, "excerpts")
    answer = api.post(prefix + "/ask", json={"question": "login"}).json()
    assert answer["retrieval"]["hits"] == preview["hits"]
    assert [c["id"] for c in provider.excerpts] == [h["id"] for h in preview["hits"]]
    assert all("fusion_score" not in c for c in provider.excerpts)
    assert (
        api.post(
            prefix + "/retrieve", json={"question": "login", "strategy": "unknown"}
        ).status_code
        == 422
    )
    baseline = api.post(
        prefix + "/retrieve", json={"question": "login", "strategy": "semantic"}
    ).json()
    assert all(h["reason"] == "semantic" for h in baseline["hits"])
    assert api.post(prefix + "/retrieve", content=b"x" * 4097).status_code == 413


def test_real_resolved_imports_expand_only_within_snapshot(api):
    repository_id = str(uuid4())
    with Session(api.app.state.database) as session:
        repo = Repository(
            id=repository_id,
            url="https://github.com/example/graph",
            full_name="example/graph",
            status="ready",
            resolution_configs=[],
        )
        session.add(repo)
        session.flush()
        for path, source, names, refs in [
            (
                "route.py",
                "import auth\n" + "\n".join(f"def seed{i}(): return {i}" for i in range(6)),
                [f"seed{i}" for i in range(6)],
                [{"specifier": "auth", "kind": "python_import", "names": [], "line": 1}],
            ),
            ("auth.py", "def verify(): return True", ["verify"], []),
        ]:
            file = RepositoryFile(
                id=str(uuid4()),
                repository_id=repository_id,
                path=path,
                language="python",
                source=source,
                size_bytes=len(source),
                symbol_count=len(names),
                imports=[r["specifier"] for r in refs],
                import_references=refs,
            )
            session.add(file)
            session.flush()
            for i, name in enumerate(names):
                line = i + 2 if path == "route.py" else 1
                session.add(
                    CodeSymbol(
                        id=str(uuid4()),
                        file_id=file.id,
                        name=name,
                        kind="function",
                        start_line=line,
                        end_line=line,
                        parameters=[],
                    )
                )
        session.commit()
    provider = FixtureProvider()
    provider.embed = lambda texts: [[1, 0] if "seed" in text else [0, 1] for text in texts]
    api.app.dependency_overrides[provider_dependency] = lambda: provider
    prefix = f"/api/repositories/{repository_id}"
    assert api.post(prefix + "/index", json={}).status_code == 200
    preview = api.post(prefix + "/retrieve", json={"question": "seed0"}).json()
    expanded = [hit for hit in preview["hits"] if hit["reason"] == "dependency"]
    assert any(
        hit["file_path"] == "auth.py" and hit["via_file_path"] == "route.py" for hit in expanded
    )
