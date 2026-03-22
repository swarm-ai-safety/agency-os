"""Tests for shadow git and state manager."""

import json
import subprocess

import pytest

from agency_os.observability.shadow_git import ShadowGit
from agency_os.observability.state import StateManager


def _git_available() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True, timeout=5, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


needs_git = pytest.mark.skipif(not _git_available(), reason="git not available")


@pytest.fixture
def work_dir(tmp_path):
    """Create a working directory with some initial files."""
    d = tmp_path / "workspace"
    d.mkdir()
    (d / "main.py").write_text("print('hello')\n")
    (d / "config.yaml").write_text("key: value\n")
    return d


@pytest.fixture
def shadow(work_dir, tmp_path):
    """Create and initialize a ShadowGit instance."""
    git_dir = tmp_path / ".shadow_git"
    sg = ShadowGit(work_dir, git_dir)
    sg.init()
    sg.commit_baseline()
    return sg


@needs_git
class TestShadowGit:
    def test_init_creates_git_dir(self, tmp_path):
        git_dir = tmp_path / ".shadow"
        work_dir = tmp_path / "work"
        work_dir.mkdir()

        sg = ShadowGit(work_dir, git_dir)
        sg.init()
        assert git_dir.exists()
        assert (git_dir / "info" / "exclude").exists()

    def test_commit_baseline(self, shadow, work_dir):
        # Baseline should have captured initial files
        diff = shadow.diff_from_ref("baseline")
        assert diff == ""  # no changes since baseline

    def test_detect_new_file(self, shadow, work_dir):
        (work_dir / "new_file.txt").write_text("new content\n")
        changed = shadow.diff_working_names()
        assert "new_file.txt" in changed

    def test_detect_modified_file(self, shadow, work_dir):
        (work_dir / "main.py").write_text("print('modified')\n")
        changed = shadow.diff_working_names()
        assert "main.py" in changed

    def test_commit_snapshot_and_diff(self, shadow, work_dir):
        (work_dir / "main.py").write_text("print('v2')\n")
        shadow.commit_snapshot("step_1", "first change")

        diff = shadow.diff_from_ref("baseline")
        assert "+print('v2')" in diff
        assert "-print('hello')" in diff

    def test_show_file_at_ref(self, shadow, work_dir):
        content = shadow.show_file("baseline", "main.py")
        assert content == "print('hello')\n"

    def test_show_file_returns_none_for_missing(self, shadow):
        assert shadow.show_file("baseline", "nonexistent.py") is None

    def test_snapshot_no_changes_still_tags(self, shadow, work_dir):
        # No changes — should not error, should still create tag
        shadow.commit_snapshot("empty_tag")
        diff = shadow.diff_from_ref("empty_tag")
        assert diff == ""

    def test_sequential_snapshots(self, shadow, work_dir):
        (work_dir / "main.py").write_text("v2\n")
        shadow.commit_snapshot("step_1")

        (work_dir / "main.py").write_text("v3\n")
        shadow.commit_snapshot("step_2")

        # Diff from step_1 should only show v2 -> v3
        diff = shadow.diff_from_ref("step_1")
        assert "+v3" in diff
        assert "-v2" in diff


@needs_git
class TestStateManager:
    def test_no_changes_returns_empty(self, shadow, work_dir):
        sm = StateManager(work_dir, shadow)
        events = sm.check_for_writes(step_id=1)
        assert events == []

    def test_detects_new_file(self, shadow, work_dir):
        sm = StateManager(work_dir, shadow)
        (work_dir / "output.txt").write_text("result\n")

        events = sm.check_for_writes(step_id=1)
        assert len(events) == 1
        assert events[0].file_path == "output.txt"
        assert events[0].step_id == 1
        assert events[0].diff_stats["added"] == 1
        assert events[0].diff_stats["removed"] == 0

    def test_detects_modification(self, shadow, work_dir):
        sm = StateManager(work_dir, shadow)
        (work_dir / "main.py").write_text("print('new')\nprint('lines')\n")

        events = sm.check_for_writes(step_id=2)
        assert len(events) == 1
        assert events[0].file_path == "main.py"
        assert events[0].diff_stats["added"] == 2
        assert events[0].diff_stats["removed"] == 1

    def test_second_check_only_sees_new_changes(self, shadow, work_dir):
        sm = StateManager(work_dir, shadow)

        (work_dir / "a.txt").write_text("first\n")
        events1 = sm.check_for_writes(step_id=1)
        assert len(events1) == 1

        (work_dir / "b.txt").write_text("second\n")
        events2 = sm.check_for_writes(step_id=2)
        assert len(events2) == 1
        assert events2[0].file_path == "b.txt"

    def test_write_log_accumulates(self, shadow, work_dir):
        sm = StateManager(work_dir, shadow)

        (work_dir / "a.txt").write_text("1\n")
        sm.check_for_writes(step_id=1)

        (work_dir / "b.txt").write_text("2\n")
        sm.check_for_writes(step_id=2)

        assert len(sm.write_log) == 2
        assert sm.write_log[0].step_id == 1
        assert sm.write_log[1].step_id == 2

    def test_to_changelog(self, shadow, work_dir):
        sm = StateManager(work_dir, shadow)
        (work_dir / "out.txt").write_text("data\n")
        sm.check_for_writes(step_id=1)

        changelog = sm.to_changelog()
        assert len(changelog) == 1
        assert changelog[0]["file_path"] == "out.txt"
        assert changelog[0]["step_id"] == 1
        # Must be JSON-serializable
        json.dumps(changelog)

    def test_save_changelog(self, shadow, work_dir, tmp_path):
        sm = StateManager(work_dir, shadow)
        (work_dir / "out.txt").write_text("data\n")
        sm.check_for_writes(step_id=1)

        dest = tmp_path / "changelog.jsonl"
        sm.save_changelog(dest)

        assert dest.exists()
        lines = dest.read_text().strip().splitlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["file_path"] == "out.txt"

    def test_deleted_file_detected(self, shadow, work_dir):
        sm = StateManager(work_dir, shadow)
        (work_dir / "config.yaml").unlink()

        events = sm.check_for_writes(step_id=1)
        assert len(events) == 1
        assert events[0].file_path == "config.yaml"
        assert events[0].diff_stats["removed"] > 0
