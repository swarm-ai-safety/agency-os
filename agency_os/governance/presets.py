"""Map named governance presets to SWARM GovernanceConfig parameters."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from agency_os.packages.schema import GovernanceConfig as PackageGovernanceConfig
from swarm.governance.config import GovernanceConfig as SwarmGovernanceConfig

_PROFILES_DIR = Path(__file__).resolve().parent / "profiles"


def resolve_governance(config: PackageGovernanceConfig) -> SwarmGovernanceConfig:
    """
    Resolve a package governance config into a SWARM GovernanceConfig.

    1. Load the named preset profile YAML
    2. Apply any overrides from the package config
    3. Return a valid SwarmGovernanceConfig

    Args:
        config: Package governance config with preset name and overrides.

    Returns:
        Fully resolved SWARM GovernanceConfig.
    """
    # Load base profile
    profile = load_profile(config.preset)

    # Apply package-level overrides
    overrides = config.overrides
    if overrides.audit_frequency is not None:
        profile["audit_probability"] = overrides.audit_frequency
        profile["audit_enabled"] = True
    if overrides.circuit_breaker is not None:
        profile["circuit_breaker_enabled"] = overrides.circuit_breaker.enabled
        profile["freeze_threshold_violations"] = overrides.circuit_breaker.threshold
    if overrides.tax_rate is not None:
        profile["transaction_tax_rate"] = overrides.tax_rate

    return SwarmGovernanceConfig(**profile)


def load_profile(name: str) -> dict[str, Any]:
    """Load a governance profile YAML by name."""
    path = _PROFILES_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"Governance profile '{name}' not found. Available: {list_profiles()}"
        )
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Profile must be a YAML mapping: {path}")
    return data


def list_profiles() -> list[str]:
    """List available governance profile names."""
    if not _PROFILES_DIR.is_dir():
        return []
    return sorted(p.stem for p in _PROFILES_DIR.glob("*.yaml"))
