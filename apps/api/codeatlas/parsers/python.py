import ast

from codeatlas.parsers.types import ParsedSource, Symbol


def parse_python(source: str) -> ParsedSource:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return ParsedSource(warning="Python source could not be parsed; symbols are unavailable.")
    result = ParsedSource()
    stack: list[tuple[ast.AST, Symbol | None]] = [(tree, None)]
    while stack:
        node, parent = stack.pop()
        current = parent
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            kind = (
                "class"
                if isinstance(node, ast.ClassDef)
                else ("method" if parent and parent.kind == "class" else "function")
            )
            parameters = []
            if not isinstance(node, ast.ClassDef):
                args = node.args
                parameters = [arg.arg for arg in args.posonlyargs + args.args]
                if args.vararg:
                    parameters.append(f"*{args.vararg.arg}")
                parameters.extend(arg.arg for arg in args.kwonlyargs)
                if args.kwarg:
                    parameters.append(f"**{args.kwarg.arg}")
            current = Symbol(
                name=node.name,
                kind=kind,
                start_line=node.lineno,
                end_line=node.end_lineno or node.lineno,
                parameters=parameters,
                parent_id=parent.id if parent else None,
            )
            result.symbols.append(current)
        elif isinstance(node, ast.Import):
            result.imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            result.imports.append("." * node.level + (node.module or ""))
        stack.extend((child, current) for child in reversed(list(ast.iter_child_nodes(node))))
    result.imports = sorted(set(result.imports))
    return result
