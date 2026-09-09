from collections import defaultdict
from pathlib import PurePosixPath

from codeatlas.core.errors import DomainError
from codeatlas.dependencies.resolver import ImportResolver
from codeatlas.parsers.types import ImportReference, ResolutionConfig
from codeatlas.schemas.graph import (
    DependencyGraph,
    EdgeEvidence,
    GraphEdge,
    GraphFile,
    GraphNode,
    UnresolvedImport,
)


def find_cycles(node_ids: list[str], edges: list[GraphEdge]) -> list[list[str]]:
    """Iterative Kosaraju avoids recursion failures for long chains and large cycles."""
    outgoing: dict[str, list[str]] = defaultdict(list)
    incoming: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        outgoing[edge.source].append(edge.target)
        incoming[edge.target].append(edge.source)
    seen: set[str] = set()
    order = []
    for start in node_ids:
        if start in seen:
            continue
        stack = [(start, False)]
        while stack:
            node, expanded = stack.pop()
            if expanded:
                order.append(node)
            elif node not in seen:
                seen.add(node)
                stack.append((node, True))
                stack.extend((target, False) for target in outgoing[node] if target not in seen)
    seen.clear()
    cycles = []
    for start in reversed(order):
        if start in seen:
            continue
        component = []
        stack = [start]
        seen.add(start)
        while stack:
            node = stack.pop()
            component.append(node)
            for target in incoming[node]:
                if target not in seen:
                    seen.add(target)
                    stack.append(target)
        if len(component) > 1 or start in outgoing[start]:
            cycles.append(sorted(component))
    return sorted(cycles)


def build_graph(
    repository_id: str, files: list[GraphFile], configs: list[ResolutionConfig] | None
) -> DependencyGraph:
    files = sorted(files, key=lambda file: file.path)
    resolver = ImportResolver(files, configs or [])
    edges: dict[tuple[str, str], GraphEdge] = {}
    unresolved = []
    evidence_keys: dict[tuple[str, str], set[tuple]] = defaultdict(set)
    legacy_files = 0
    observations = 0
    notes = [f"{config.path}: {config.warning}" for config in configs or [] if config.warning]
    for file in files:
        refs = file.import_references
        if refs is None:
            legacy_files += 1
            refs = [ImportReference(specifier=value, kind="legacy") for value in file.imports]
        for ref in refs:
            observations += 1
            if observations > 50_000:
                raise DomainError(
                    "graph_too_large", "Graph exceeds 50,000 import observations.", 413
                )
            targets, method, candidates = resolver.resolve(file, ref)
            if not targets:
                unresolved.append(
                    UnresolvedImport(
                        source=file.id,
                        specifier=ref.specifier,
                        line=ref.line,
                        reason=method,
                        candidates=candidates[:20],
                    )
                )
            for target_path in targets:
                target = resolver.files[target_path]
                key = (file.id, target.id)
                edge = edges.setdefault(
                    key, GraphEdge(id=f"{file.id}:{target.id}", source=file.id, target=target.id)
                )
                evidence = EdgeEvidence(
                    specifier=ref.specifier, line=ref.line, kind=ref.kind, resolution=method
                )
                evidence_key = (ref.specifier, ref.line, ref.kind, method)
                if evidence_key not in evidence_keys[key]:
                    evidence_keys[key].add(evidence_key)
                    edge.evidence.append(evidence)
                if len(edges) > 50_000:
                    raise DomainError("graph_too_large", "Graph exceeds 50,000 local edges.", 413)
    edge_list = sorted(edges.values(), key=lambda edge: (edge.source, edge.target))
    cycles = find_cycles([file.id for file in files], edge_list)
    components = {node: index for index, component in enumerate(cycles) for node in component}
    for edge in edge_list:
        edge.in_cycle = edge.source in components and components.get(edge.source) == components.get(
            edge.target
        )
    if legacy_files:
        notes.append(
            "Legacy imports lack names/locations and alias configs. Reimport for full coverage."
        )
    notes.append(
        "Static imports only. Python roots are inferred; external dependencies are not downloaded."
    )
    return DependencyGraph(
        repository_id=repository_id,
        nodes=[
            GraphNode(
                id=file.id,
                label=PurePosixPath(file.path).name,
                file=file.path,
                language=file.language,
                symbol_count=file.symbol_count,
                warning=file.warning,
            )
            for file in files
        ],
        edges=edge_list,
        unresolved=unresolved,
        cycles=cycles,
        notes=notes,
        legacy_files=legacy_files,
    )
