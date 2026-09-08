import tree_sitter_javascript
import tree_sitter_typescript
from tree_sitter import Language, Node, Parser

from codeatlas.parsers.types import ParsedSource, Symbol


def parse_javascript(source: str, *, typescript: bool = False, tsx: bool = False) -> ParsedSource:
    grammar = tree_sitter_javascript.language()
    if typescript:
        grammar = (
            tree_sitter_typescript.language_tsx()
            if tsx
            else tree_sitter_typescript.language_typescript()
        )
    raw = source.encode("utf-8")
    tree = Parser(Language(grammar)).parse(raw)
    result = ParsedSource(
        warning=(
            "Syntax errors detected; extracted symbols may be incomplete."
            if tree.root_node.has_error
            else None
        )
    )

    def text(node: Node | None) -> str:
        return raw[node.start_byte : node.end_byte].decode("utf-8") if node else ""

    stack: list[tuple[Node, Symbol | None]] = [(tree.root_node, None)]
    kinds = {
        "function_declaration": "function",
        "generator_function_declaration": "function",
        "class_declaration": "class",
        "abstract_class_declaration": "class",
        "method_definition": "method",
        "method_signature": "method",
        "abstract_method_signature": "method",
        "interface_declaration": "interface",
        "type_alias_declaration": "type",
    }
    while stack:
        node, parent = stack.pop()
        current = parent
        name = node.child_by_field_name("name")
        kind = kinds.get(node.type)
        body = node
        if node.type in {
            "variable_declarator",
            "public_field_definition",
            "field_definition",
            "pair",
        }:
            value = node.child_by_field_name("value")
            name = name or node.child_by_field_name("property") or node.child_by_field_name("key")
            if value and value.type in {
                "arrow_function",
                "function_expression",
                "generator_function",
                "class",
            }:
                body = value
                kind = (
                    "class"
                    if value.type == "class"
                    else ("method" if parent and parent.kind == "class" else "function")
                )
        if kind and name:
            params = body.child_by_field_name("parameters")
            single = body.child_by_field_name("parameter")
            current = Symbol(
                name=text(name),
                kind=kind,
                start_line=node.start_point.row + 1,
                end_line=node.end_point.row + 1,
                parameters=[text(child) for child in params.named_children]
                if params
                else ([text(single)] if single else []),
                parent_id=parent.id if parent else None,
            )
            result.symbols.append(current)
        if node.type in {"import_statement", "export_statement"}:
            imported = node.child_by_field_name("source")
            if imported:
                result.imports.append(text(imported)[1:-1])
        stack.extend((child, current) for child in reversed(node.named_children))
    result.imports = sorted(set(result.imports))
    return result
