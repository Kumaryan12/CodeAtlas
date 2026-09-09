import posixpath
from collections import defaultdict
from pathlib import PurePosixPath

from codeatlas.parsers.types import ImportReference, ResolutionConfig
from codeatlas.schemas.graph import GraphFile


def safe_join(base: str, target: str) -> str | None:
    if target.startswith("/") or "\\" in target or ":" in target or "\x00" in target:
        return None
    normalized = posixpath.normpath(posixpath.join(base, target))
    return None if normalized == ".." or normalized.startswith("../") else normalized


def within(path: str, directory: str) -> bool:
    return directory in {"", "."} or path == directory or path.startswith(directory + "/")


class ImportResolver:
    def __init__(self, files: list[GraphFile], configs: list[ResolutionConfig]):
        self.files = {file.path: file for file in files}
        self.configs = sorted(
            configs, key=lambda config: (-len(PurePosixPath(config.path).parts), config.path)
        )
        self.python_modules: dict[str, list[tuple[str, str]]] = defaultdict(list)
        python_paths = {file.path for file in files if file.language == "python"}
        for file in files:
            if file.language != "python":
                continue
            path = PurePosixPath(file.path)
            roots = {""}
            # Namespace packages need not contain __init__.py. Index bounded suffix roots;
            # resolution only chooses roots containing the importer, avoiding unrelated apps.
            # Do not infer each file's own directory as a sys.path root: a nested
            # logging.py importing stdlib logging would otherwise create a false self-cycle.
            for index in range(max(0, len(path.parts) - 32), len(path.parts) - 1):
                roots.add("/".join(path.parts[:index]))
            directory = path.parent
            package_found = False
            while str(directory / "__init__.py") in python_paths:
                package_found = True
                directory = directory.parent
                if str(directory) == ".":
                    break
            if package_found:
                roots.add("" if str(directory) == "." else str(directory))
            # Conventional src roots are explicitly reported as inferred, not runtime sys.path.
            for index, part in enumerate(path.parts[:-1]):
                if part == "src":
                    roots.add("/".join(path.parts[: index + 1]))
            for root in roots:
                relative = path.relative_to(root or ".").with_suffix("")
                parts = list(relative.parts)
                if parts[-1] == "__init__":
                    parts.pop()
                if parts and all(part.isidentifier() for part in parts):
                    self.python_modules[".".join(parts)].append((file.path, root))

    def python_candidates(self, importer: GraphFile, module: str) -> list[str]:
        entries = self.python_modules.get(module, [])
        local = [(path, root) for path, root in entries if within(importer.path, root)]
        if local:
            depth = max(len(root.split("/")) if root else 0 for _, root in local)
            entries = [
                (path, root)
                for path, root in local
                if (len(root.split("/")) if root else 0) == depth
            ]
        elif len({path for path, _ in entries}) == 1:
            return []
        return sorted({path for path, _ in entries})

    def python(self, importer: GraphFile, ref: ImportReference) -> tuple[list[str], str, list[str]]:
        module = ref.specifier
        if module.startswith("."):
            level = len(module) - len(module.lstrip("."))
            parts = list(PurePosixPath(importer.path).parent.parts)
            if parts == ["."]:
                parts = []
            if level > len(parts):
                return [], "relative_import_outside_package", []
            base = "/".join(parts[: len(parts) - level + 1])
            tail = module[level:].replace(".", "/")
            target_base = safe_join(base, tail)
            if target_base is None:
                return [], "invalid_specifier", []

            def lookup(name: str) -> list[str]:
                return [
                    p
                    for p in (name + ".py", name + "/__init__.py")
                    if p in self.files and self.files[p].language == "python"
                ]

            candidates = lookup(target_base)
            child_candidates = [
                lookup(target_base + "/" + name) for name in ref.names if name != "*"
            ]
            method = "python_relative"
        else:
            candidates = self.python_candidates(importer, module)
            child_candidates = (
                [
                    self.python_candidates(importer, module + "." + name)
                    for name in ref.names
                    if name != "*"
                ]
                if ref.kind == "python_from"
                else []
            )
            method = "python_inferred_root"
        ambiguous = candidates if len(candidates) > 1 else []
        ambiguous += [path for group in child_candidates if len(group) > 1 for path in group]
        if ambiguous:
            return [], "ambiguous_local_module", sorted(set(ambiguous))
        targets = sorted(
            set(candidates + [group[0] for group in child_candidates if len(group) == 1])
        )
        if targets:
            return targets, method, []
        return (
            [],
            "missing_local_module" if module.startswith(".") else "external_or_unresolved",
            [],
        )

    def js_candidates(self, base: str) -> list[str]:
        suffix = PurePosixPath(base).suffix
        substitutions = {
            ".js": [".ts", ".tsx", ".js", ".jsx"],
            ".jsx": [".tsx", ".jsx"],
            ".mjs": [".mts", ".mjs"],
            ".cjs": [".cts", ".cjs"],
        }
        if suffix in substitutions:
            choices = [base[: -len(suffix)] + extension for extension in substitutions[suffix]]
        elif suffix:
            choices = [base]
        else:
            extensions = [".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"]
            choices = [base + extension for extension in extensions]
            choices += [base + "/index" + extension for extension in extensions]
        # Multiple valid candidates are shown as ambiguous; do not invent a bundler mode.
        return [
            path for path in choices if path in self.files and self.files[path].language != "python"
        ]

    def javascript(
        self, importer: GraphFile, ref: ImportReference
    ) -> tuple[list[str], str, list[str]]:
        specifier = ref.specifier
        if (
            "\\" in specifier
            or ":" in specifier
            or "\x00" in specifier
            or specifier.startswith("/")
        ):
            return [], "external_or_unsupported_specifier", []
        bases: list[str] = []
        method = "javascript_relative"
        if specifier.startswith(("./", "../")):
            base = safe_join(str(PurePosixPath(importer.path).parent), specifier)
            if base is None:
                return [], "path_outside_snapshot", []
            bases.append(base)
        else:
            config = next(
                (
                    item
                    for item in self.configs
                    if within(importer.path, str(PurePosixPath(item.path).parent))
                ),
                None,
            )
            if config:
                config_directory = str(PurePosixPath(config.path).parent)
                base_directory = safe_join(config_directory, config.base_url or ".")
                if base_directory is None:
                    return [], "invalid_alias_base", []
                patterns = []
                for pattern in config.paths:
                    prefix, _, suffix = pattern.partition("*")
                    if pattern == specifier or (
                        "*" in pattern
                        and specifier.startswith(prefix)
                        and specifier.endswith(suffix)
                        and len(specifier) >= len(prefix) + len(suffix)
                    ):
                        patterns.append(pattern)
                if patterns:
                    pattern = max(
                        patterns, key=lambda p: (p == specifier, len(p.split("*")[0]), len(p))
                    )
                    prefix, _, suffix = pattern.partition("*")
                    capture = specifier[
                        len(prefix) : len(specifier) - len(suffix) if suffix else None
                    ]
                    for target in config.paths[pattern]:
                        base = safe_join(base_directory, target.replace("*", capture))
                        if base is not None:
                            bases.append(base)
                    method = "typescript_paths"
                elif config.base_url is not None:
                    base = safe_join(base_directory, specifier)
                    if base is not None:
                        bases.append(base)
                    method = "typescript_base_url"
            if not bases:
                return [], "external_or_unresolved", []
        for base in bases:
            candidates = self.js_candidates(base)
            if len(candidates) > 1:
                return [], "ambiguous_local_module", candidates
            if candidates:
                return candidates, method, []
        return (
            [],
            "missing_local_module" if method != "typescript_base_url" else "external_or_unresolved",
            [],
        )

    def resolve(
        self, importer: GraphFile, ref: ImportReference
    ) -> tuple[list[str], str, list[str]]:
        if importer.language == "python":
            return self.python(importer, ref)
        return self.javascript(importer, ref)
