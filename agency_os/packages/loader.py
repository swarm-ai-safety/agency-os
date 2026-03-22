"""Load, validate, and resolve package YAML files."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

import yaml  # type: ignore[import-untyped]

from agency_os.packages.schema import PackageSpec

# Built-in package library directory
_LIBRARY_DIR = Path(__file__).resolve().parent / "library"

# Maximum extends recursion depth to prevent cycles
_MAX_EXTENDS_DEPTH = 10

# Safe name pattern: alphanumeric, hyphens, underscores only
_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _validate_safe_name(name: str) -> None:
    """Reject names that could cause path traversal."""
    if not _SAFE_NAME_RE.match(name):
        raise ValueError(
            f"Invalid name {name!r}: must contain only alphanumeric characters, "
            f"hyphens, and underscores"
        )


def _validate_path_within(path: Path, allowed_dir: Path) -> None:
    """Ensure a resolved path is inside the allowed directory."""
    try:
        path.resolve().relative_to(allowed_dir.resolve())
    except ValueError:
        raise ValueError(f"Path escapes allowed directory: {path}") from None


def load_package(path: str | Path) -> PackageSpec:
    """
    Load and validate a package YAML file.

    Resolves `extends` references by merging base package configs.

    Args:
        path: Path to the package YAML file.

    Returns:
        Fully resolved PackageSpec.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        ValueError: If validation fails.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Package file not found: {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Package file must contain a YAML mapping: {path}")

    # Resolve extends chain
    raw = _resolve_extends(raw, path.parent, depth=0)

    return PackageSpec(**raw)


def load_package_from_name(name: str) -> PackageSpec:
    """
    Load a built-in package by name.

    Args:
        name: Package name (e.g. "saas_dev_studio"). Searches the library dir.

    Returns:
        Fully resolved PackageSpec.
    """
    _validate_safe_name(name)

    # Accept both external hyphenated names (e.g. "saas-dev-studio")
    # and internal underscore filenames (e.g. "saas_dev_studio").
    alias_names: list[str] = [name]
    normalized_alias = name.replace("-", "_")
    if normalized_alias not in alias_names:
        alias_names.append(normalized_alias)

    candidates = [
        candidate
        for alias in alias_names
        for candidate in (_LIBRARY_DIR / f"{alias}.yaml", _LIBRARY_DIR / f"{alias}.yml")
    ]
    for candidate in candidates:
        _validate_path_within(candidate, _LIBRARY_DIR)
        if candidate.exists():
            return load_package(candidate)

    raise FileNotFoundError(
        f"Built-in package '{name}' not found. Available: {list_builtin_packages()}"
    )


def list_builtin_packages() -> list[str]:
    """List names of all built-in packages (excluding _base)."""
    if not _LIBRARY_DIR.is_dir():
        return []
    return sorted(
        p.stem for p in _LIBRARY_DIR.glob("*.yaml") if not p.stem.startswith("_")
    )


def validate_package(path: str | Path) -> list[str]:
    """
    Validate a package file and return a list of errors (empty = valid).

    Args:
        path: Path to the package YAML file.

    Returns:
        List of validation error messages.
    """
    errors: list[str] = []
    try:
        spec = load_package(path)

        if not spec.metadata.name:
            errors.append("metadata.name is required")

        if not spec.agents:
            errors.append("At least one agent is required")

        for i, agent in enumerate(spec.agents):
            if not agent.ref:
                errors.append(f"agents[{i}].ref is required")

    except FileNotFoundError as e:
        errors.append(str(e))
    except Exception as e:
        errors.append(f"Validation error: {e}")

    return errors


def _resolve_extends(
    raw: dict[str, Any],
    search_dir: Path,
    depth: int,
) -> dict[str, Any]:
    """
    Resolve the `extends` field by loading and merging the base package.

    Supports single-level extends. The base is loaded, then the child
    overrides any fields it defines.
    """
    extends = raw.get("extends")
    if not extends:
        return raw

    if depth >= _MAX_EXTENDS_DEPTH:
        raise ValueError(
            f"Maximum extends depth ({_MAX_EXTENDS_DEPTH}) exceeded — "
            f"possible circular reference"
        )

    # Validate the name to prevent path traversal
    _validate_safe_name(extends)

    # Find the base file
    base_path = _find_base_file(extends, search_dir)
    if base_path is None:
        raise FileNotFoundError(f"Base package not found: {extends}")

    base_raw = yaml.safe_load(base_path.read_text(encoding="utf-8"))
    if not isinstance(base_raw, dict):
        raise ValueError(f"Base package must be a YAML mapping: {base_path}")

    # Recursively resolve the base's own extends
    base_raw = _resolve_extends(base_raw, base_path.parent, depth + 1)

    # Merge: child overrides base
    merged = _deep_merge(base_raw, raw)
    merged.pop("extends", None)
    return merged


def _find_base_file(name: str, search_dir: Path) -> Optional[Path]:
    """Find a base package file by name."""
    _validate_safe_name(name)

    candidates = [
        search_dir / f"{name}.yaml",
        search_dir / f"{name}.yml",
        _LIBRARY_DIR / f"{name}.yaml",
        _LIBRARY_DIR / f"{name}.yml",
    ]
    for candidate in candidates:
        # Ensure candidate stays within expected directory
        resolved = candidate.resolve()
        if not (
            _is_within(resolved, search_dir.resolve())
            or _is_within(resolved, _LIBRARY_DIR.resolve())
        ):
            continue
        if candidate.exists():
            return candidate
    return None


def _is_within(path: Path, directory: Path) -> bool:
    """Check if path is within directory."""
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False


def _deep_merge(base: dict, override: dict) -> dict:
    """
    Deep merge two dicts. Override values take precedence.
    Lists are replaced, not appended.
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
