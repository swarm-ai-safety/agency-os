"""Tests for agency_os.packages.loader."""

from pathlib import Path

import pytest

from agency_os.packages.loader import (
    list_builtin_packages,
    load_package,
    load_package_from_name,
    validate_package,
)

LIBRARY_DIR = (
    Path(__file__).resolve().parent.parent.parent / "agency_os" / "packages" / "library"
)


class TestLoadPackage:
    def test_load_saas_dev_studio(self):
        spec = load_package(LIBRARY_DIR / "saas_dev_studio.yaml")
        assert spec.metadata.name == "saas-dev-studio"
        assert len(spec.agents) == 6
        assert spec.governance.preset == "balanced"

    def test_load_missing_file(self):
        with pytest.raises(FileNotFoundError):
            load_package("/nonexistent/package.yaml")

    def test_extends_resolution(self):
        spec = load_package(LIBRARY_DIR / "saas_dev_studio.yaml")
        # Should inherit deployment config from _base
        assert spec.deployment.llm_provider == "anthropic"


class TestLoadFromName:
    def test_load_builtin(self):
        spec = load_package_from_name("saas_dev_studio")
        assert spec.metadata.name == "saas-dev-studio"

    def test_load_builtin_hyphenated_alias(self):
        spec = load_package_from_name("saas-dev-studio")
        assert spec.metadata.name == "saas-dev-studio"

    def test_missing_builtin(self):
        with pytest.raises(FileNotFoundError, match="not found"):
            load_package_from_name("nonexistent_package")


class TestListBuiltin:
    def test_lists_packages(self):
        packages = list_builtin_packages()
        assert "saas_dev_studio" in packages
        assert "_base" not in packages  # Base should be excluded


class TestValidate:
    def test_valid_package(self):
        errors = validate_package(LIBRARY_DIR / "saas_dev_studio.yaml")
        assert errors == []

    def test_missing_file(self):
        errors = validate_package("/nonexistent.yaml")
        assert len(errors) > 0
