import json

from codeatlas.parsers.types import ResolutionConfig


def read_resolution_config(path: str, source: str) -> ResolutionConfig:
    """Read a deliberately small, strict-JSON subset. Never follow extends or load plugins."""
    config = ResolutionConfig(path=path)
    try:
        data = json.loads(source)
        options = data.get("compilerOptions", {})
        if not isinstance(options, dict):
            raise ValueError
        if "extends" in data or "references" in data:
            config.warning = (
                "Config inheritance/project references are not followed; only local options apply."
            )
        base = options.get("baseUrl")
        if base is not None and (not isinstance(base, str) or len(base) > 1000):
            raise ValueError
        config.base_url = base
        paths = options.get("paths", {})
        if not isinstance(paths, dict) or len(paths) > 64:
            raise ValueError
        for pattern, targets in paths.items():
            if (
                len(pattern) > 1000
                or pattern.count("*") > 1
                or not isinstance(targets, list)
                or len(targets) > 16
                or any(not isinstance(t, str) or len(t) > 1000 or t.count("*") > 1 for t in targets)
            ):
                raise ValueError
            config.paths[pattern] = targets
    except (ValueError, TypeError, AttributeError, RecursionError):
        return ResolutionConfig(
            path=path,
            warning="Unsupported JSON/config limits; aliases remain unresolved.",
        )
    return config
