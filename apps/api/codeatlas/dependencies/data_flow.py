"""Bounded Python return-to-argument analysis; never executes repository source."""

import ast
import time

from codeatlas.core.errors import DomainError
from codeatlas.dependencies.graph import find_cycles
from codeatlas.dependencies.resolver import ImportResolver
from codeatlas.parsers.types import ImportReference
from codeatlas.schemas.graph import EdgeEvidence, GraphEdge, GraphFile


class PythonFlow:
    def __init__(self, files, graph):
        self.graph = graph
        self.files = {file.id: file for file in files}
        self.resolver = ImportResolver(
            [GraphFile.model_validate(file, from_attributes=True) for file in files], []
        )
        self.trees = {}
        self.functions = {}
        self.bindings = {}
        self.summaries = {}
        self.edges = {}
        self.deadline = time.monotonic() + 5
        self.steps = 0
        total = 0
        for file in files:
            if file.language != "python":
                continue
            total += len(file.source.encode())
            if total > 2_000_000 or len(self.trees) >= 100:
                graph.notes.append(
                    "Python analysis capped at 100 files / 2 MB; remaining files omitted."
                )
                break
            try:
                tree = ast.parse(file.source)
                if sum(1 for _ in ast.walk(tree)) > 30_000:
                    graph.notes.append(f"{file.path}: AST size limit; omitted.")
                    continue
            except (SyntaxError, RecursionError, ValueError):
                graph.notes.append(f"{file.path}: Python parsing failed; omitted.")
                continue
            self.trees[file.id] = tree
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.functions[file.id, node.name] = node
        for file_id, tree in self.trees.items():
            bindings = {}
            file = self.files[file_id]
            for node in tree.body:
                if isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        ref = ImportReference(
                            specifier="." * node.level + (node.module or ""),
                            kind="python_from",
                            names=[alias.name],
                            line=node.lineno,
                        )
                        paths, _, _ = self.resolver.resolve(
                            GraphFile.model_validate(file, from_attributes=True), ref
                        )
                        if len(paths) == 1:
                            target = self.resolver.files[paths[0]].id
                            if (target, alias.name) in self.functions:
                                bindings[alias.asname or alias.name] = (target, alias.name)
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        ref = ImportReference(
                            specifier=alias.name, kind="python_import", line=node.lineno
                        )
                        paths, _, _ = self.resolver.resolve(
                            GraphFile.model_validate(file, from_attributes=True), ref
                        )
                        if len(paths) == 1:
                            bindings[alias.asname or alias.name] = (
                                self.resolver.files[paths[0]].id,
                                None,
                            )
            self.bindings[file_id] = bindings

    def tick(self):
        self.steps += 1
        if self.steps > 300_000 or time.monotonic() > self.deadline:
            raise DomainError("data_flow_limit", "Data-flow analysis exceeded its work limit.", 413)

    def analyze(self, file_id, body, shadowed, emit=False):
        env = {}
        returned = set()

        def expression(node, values):
            self.tick()
            if node is None:
                return set()
            if isinstance(
                node,
                (
                    ast.Lambda,
                    ast.ListComp,
                    ast.SetComp,
                    ast.DictComp,
                    ast.GeneratorExp,
                    ast.NamedExpr,
                ),
            ):
                return set()
            if isinstance(node, ast.Name):
                return values.get(node.id, set())
            if isinstance(node, ast.Call):
                args = [expression(arg, values) for arg in node.args]
                args += [expression(kw.value, values) for kw in node.keywords]
                target = None
                if isinstance(node.func, ast.Name) and node.func.id not in shadowed:
                    target = self.bindings[file_id].get(node.func.id)
                    if target is None and (file_id, node.func.id) in self.functions:
                        target = (file_id, node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    name = ast.unparse(node.func.value)
                    if name.split(".")[0] not in shadowed:
                        module = self.bindings[file_id].get(name)
                        if module and module[1] is None:
                            target = (module[0], node.func.attr)
                if target not in self.functions:
                    return set()  # Unknown calls/methods never imply identity or passthrough.
                if emit:
                    for origin in set().union(*args):
                        if origin == target[0]:
                            continue
                        key = (origin, target[0])
                        edge = self.edges.setdefault(
                            key,
                            GraphEdge(
                                id=f"flow:{origin}:{target[0]}",
                                source=origin,
                                target=target[0],
                                relationship="data_flow",
                            ),
                        )
                        evidence = EdgeEvidence(
                            specifier=ast.unparse(node.func),
                            line=node.lineno,
                            kind="return_to_argument",
                            resolution="python_static_value_flow",
                            context_file_id=file_id,
                            context_file_path=self.files[file_id].path,
                        )
                        if evidence not in edge.evidence and len(edge.evidence) < 20:
                            edge.evidence.append(evidence)
                return self.summaries.get(target, set())
            if isinstance(node, (ast.Attribute, ast.Subscript)):
                return expression(node.value, values)
            if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
                return set().union(*(expression(item, values) for item in node.elts))
            if isinstance(node, ast.Dict):
                return set().union(*(expression(item, values) for item in node.values))
            # Inspect nested calls without assuming unknown expressions preserve values.
            for child in ast.iter_child_nodes(node):
                expression(child, values)
            return set()

        def statements(nodes, values):
            for node in nodes:
                self.tick()
                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    origins = expression(node.value, values)
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    for target in targets:
                        if isinstance(target, ast.Name):
                            values[target.id] = origins
                        else:
                            for child in ast.walk(target):
                                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                                    values.pop(child.id, None)
                elif isinstance(node, ast.Expr):
                    expression(node.value, values)
                elif isinstance(node, ast.Return):
                    if node.value is not None:
                        returned.update(expression(node.value, values) or {file_id})
                    break
                elif isinstance(node, ast.If):
                    expression(node.test, values)
                    left, right = dict(values), dict(values)
                    statements(node.body, left)
                    statements(node.orelse, right)
                    values.clear()
                    values.update(
                        {
                            key: left[key]
                            for key in left.keys() & right.keys()
                            if left[key] == right[key]
                        }
                    )
                elif isinstance(
                    node,
                    (
                        ast.For,
                        ast.While,
                        ast.Try,
                        ast.With,
                        ast.AsyncWith,
                        ast.AsyncFor,
                        ast.Match,
                        ast.AugAssign,
                        ast.Delete,
                    ),
                ):
                    # Skip complex control flow and invalidate its writes.
                    for child in ast.walk(node):
                        if isinstance(child, ast.Name) and isinstance(
                            child.ctx, (ast.Store, ast.Del)
                        ):
                            values.pop(child.id, None)

        statements(body, env)
        return returned

    def build(self):
        scopes = {}
        module_writes = {
            file_id: {
                child.id
                for node in tree.body
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                for child in ast.walk(node)
                if isinstance(child, ast.Name) and isinstance(child.ctx, (ast.Store, ast.Del))
            }
            for file_id, tree in self.trees.items()
        }
        for key, node in self.functions.items():
            shadowed = {arg.arg for arg in ast.walk(node.args) if isinstance(arg, ast.arg)}
            shadowed.update(
                n.id
                for n in ast.walk(node)
                if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del))
            )
            shadowed.update(module_writes[key[0]])
            shadowed.update(
                n.name
                for n in ast.walk(node)
                if n is not node
                and isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            )
            scopes[key] = shadowed
        for _ in range(8):
            summaries = {
                key: self.analyze(key[0], node.body, scopes[key])
                for key, node in self.functions.items()
            }
            if summaries == self.summaries:
                break
            self.summaries = summaries
        else:
            self.graph.notes.append("Function-return summaries reached the eight-pass limit.")
        for key, node in self.functions.items():
            self.analyze(key[0], node.body, scopes[key], emit=True)
        for file_id, tree in self.trees.items():
            shadowed = {
                n.id
                for node in tree.body
                if isinstance(node, (ast.Assign, ast.AnnAssign))
                for n in ast.walk(node)
                if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)
            }
            self.analyze(file_id, tree.body, shadowed, emit=True)
        edges = sorted(self.edges.values(), key=lambda edge: (edge.source, edge.target))
        cycles = find_cycles([node.id for node in self.graph.nodes], edges)
        groups = {node: i for i, group in enumerate(cycles) for node in group}
        for edge in edges:
            edge.in_cycle = edge.source in groups and groups.get(edge.source) == groups.get(
                edge.target
            )
        self.graph.edges = edges
        self.graph.cycles = cycles
        self.graph.notes.insert(
            0,
            f"Analyzed {len(self.trees)} Python files. "
            "JavaScript/TypeScript data flow is not analyzed.",
        )
        return self.graph


def build_data_flow(files, dependency_graph):
    graph = dependency_graph.model_copy(deep=True)
    graph.edges = []
    graph.unresolved = []
    graph.notes = [
        "Potential Python value flow: a function return is passed as an argument "
        "to another local function.",
        "Not a runtime trace. Branches may not execute. No LLM calls or repository execution.",
        "Tracks explicit assignments, nested calls and local helper returns; does not track "
        "parameter forwarding, class methods, mutation, external calls, loops, try blocks "
        "or dynamic dispatch.",
        "Files without arrows may have unsupported flow; "
        "absence of an arrow does not prove isolation.",
    ]
    try:
        return PythonFlow(files, graph).build()
    except RecursionError as exc:
        raise DomainError(
            "data_flow_limit", "Python syntax nesting exceeds the analysis limit.", 413
        ) from exc
