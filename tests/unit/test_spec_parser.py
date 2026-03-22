"""Tests for agency_os.agents.spec_parser."""

import pytest

from agency_os.agents.spec_parser import (
    _derive_slug,
    _split_frontmatter,
    parse_spec,
)


class TestSplitFrontmatter:
    def test_valid_frontmatter(self):
        text = "---\nname: Test\n---\n\n# Body"
        fm, body = _split_frontmatter(text)
        assert fm == "name: Test"
        assert "# Body" in body

    def test_no_frontmatter(self):
        text = "# Just markdown"
        fm, body = _split_frontmatter(text)
        assert fm is None
        assert body == text


class TestDeriveSlug:
    def test_with_prefix(self):
        assert (
            _derive_slug("engineering", "engineering-senior-developer")
            == "engineering/senior-developer"
        )

    def test_without_prefix(self):
        assert (
            _derive_slug("testing", "evidence-collector")
            == "testing/evidence-collector"
        )


class TestParseSpec:
    def test_parse_real_spec_shape_without_vendor_dependency(self, tmp_path):
        engineering_dir = tmp_path / "engineering"
        engineering_dir.mkdir()
        path = engineering_dir / "engineering-senior-developer.md"
        path.write_text(
            "---\n"
            "name: Senior Developer\n"
            "description: Delivers robust backend features.\n"
            "color: green\n"
            "---\n\n"
            "# Role\n"
            "Lead delivery across backend services.\n\n"
            "# Personality\n"
            "Pragmatic, direct, and quality-focused.\n\n"
            "# Tools\n"
            "- Python\n"
            "- FastAPI\n\n"
            "# Success Criteria\n"
            "- Passes fullstack checks\n"
            "- Includes regression tests\n",
            encoding="utf-8",
        )
        spec = parse_spec(path)
        assert spec.name == "Senior Developer"
        assert spec.slug == "engineering/senior-developer"
        assert spec.division == "engineering"
        assert spec.color == "green"
        assert "Lead delivery" in spec.identity
        assert spec.description == "Delivers robust backend features."
        assert spec.role == "Lead delivery across backend services."
        assert spec.personality == "Pragmatic, direct, and quality-focused."
        assert spec.tools == ["Python", "FastAPI"]
        assert spec.success_criteria == [
            "Passes fullstack checks",
            "Includes regression tests",
        ]

    def test_parse_missing_frontmatter(self, tmp_path):
        md = tmp_path / "bad.md"
        md.write_text("# No frontmatter here")
        with pytest.raises(ValueError, match="No YAML frontmatter"):
            parse_spec(md)

    def test_parse_minimal_frontmatter(self, tmp_path):
        md = tmp_path / "test-agent.md"
        md.write_text(
            "---\nname: Minimal\ndescription: A test agent\ncolor: blue\n---\n\n# Agent\nDoes things."
        )
        spec = parse_spec(md)
        assert spec.name == "Minimal"
        assert spec.color == "blue"
        assert spec.division == str(tmp_path.name)

    def test_immutable_spec(self, tmp_path):
        md = tmp_path / "agent.md"
        md.write_text("---\nname: Test\ndescription: test\ncolor: red\n---\n\n# Body")
        spec = parse_spec(md)
        with pytest.raises(AttributeError):
            spec.name = "Changed"
