"""Tests for nurture email sequence (day 1/3/7)."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from agency_os.service.email import (
    NURTURE_DAYS,
    NURTURE_EMAILS,
    generate_unsubscribe_token,
    send_nurture_email,
    verify_unsubscribe_token,
)
from agency_os.service.scheduled_jobs import ScheduledJobsManager


@pytest.fixture(autouse=True)
def _set_unsubscribe_secret(monkeypatch):
    """All tests in this module need UNSUBSCRIBE_SECRET set."""
    monkeypatch.setenv("UNSUBSCRIBE_SECRET", "test-secret-for-nurture-tests")


class _DummyRunFailureTracker:
    def record(self, *, failure: bool) -> None:
        pass

    def record_api_error(self, error: str) -> None:
        pass


# --- Unsubscribe token tests ---


class TestUnsubscribeToken:
    def test_generate_returns_hex_string(self):
        token = generate_unsubscribe_token("tenant-abc")
        assert isinstance(token, str)
        assert len(token) == 64  # SHA-256 hex

    def test_verify_valid_token(self):
        tid = "tenant-123"
        token = generate_unsubscribe_token(tid)
        assert verify_unsubscribe_token(tid, token) is True

    def test_verify_wrong_tenant(self):
        token = generate_unsubscribe_token("tenant-a")
        assert verify_unsubscribe_token("tenant-b", token) is False

    def test_verify_tampered_token(self):
        tid = "tenant-x"
        token = generate_unsubscribe_token(tid)
        assert verify_unsubscribe_token(tid, token[:-1] + "0") is False

    def test_missing_secret_raises(self, monkeypatch):
        monkeypatch.delenv("UNSUBSCRIBE_SECRET", raising=False)
        with pytest.raises(RuntimeError, match="UNSUBSCRIBE_SECRET"):
            generate_unsubscribe_token("tenant-any")


# --- Nurture email template tests ---


class TestNurtureEmails:
    def test_nurture_days_constant(self):
        assert NURTURE_DAYS == (1, 3, 7)

    def test_all_days_have_templates(self):
        for day in NURTURE_DAYS:
            assert day in NURTURE_EMAILS
            assert "subject" in NURTURE_EMAILS[day]
            assert "heading" in NURTURE_EMAILS[day]
            assert "body" in NURTURE_EMAILS[day]

    @patch("agency_os.service.email.send_email", return_value=True)
    def test_send_nurture_email_day1(self, mock_send):
        ok = send_nurture_email("a@b.com", "Alice", "tenant-1", 1)
        assert ok is True
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args
        assert "Getting started" in call_kwargs[1]["subject"]
        assert "Alice" in call_kwargs[1]["html"]
        assert "unsubscribe" in call_kwargs[1]["html"].lower()

    @patch("agency_os.service.email.send_email", return_value=True)
    def test_send_nurture_email_day3(self, mock_send):
        ok = send_nurture_email("a@b.com", "Bob", "tenant-2", 3)
        assert ok is True
        assert "teams are building" in mock_send.call_args[1]["subject"]

    @patch("agency_os.service.email.send_email", return_value=True)
    def test_send_nurture_email_day7(self, mock_send):
        ok = send_nurture_email("a@b.com", "Carol", "tenant-3", 7)
        assert ok is True
        assert "Need help" in mock_send.call_args[1]["subject"]

    def test_send_nurture_email_invalid_day(self):
        ok = send_nurture_email("a@b.com", "Test", "t-1", 99)
        assert ok is False

    @patch("agency_os.service.email.send_email", return_value=True)
    def test_html_escapes_tenant_name(self, mock_send):
        send_nurture_email("a@b.com", "<script>xss</script>", "t-1", 1)
        html = mock_send.call_args[1]["html"]
        assert "<script>" not in html
        assert "&lt;script&gt;" in html


# --- Scheduled job tests ---


class TestNurtureScheduledJob:
    def _make_manager(self, tenants: list[dict]) -> ScheduledJobsManager:
        db = MagicMock()
        db.list_tenants.return_value = tenants
        manager = ScheduledJobsManager(_DummyRunFailureTracker(), db)
        return manager

    def _tenant(self, tenant_id: str, email: str, days_ago: float, **meta_overrides):
        meta = {
            "email": email,
            "signed_up_at": time.time() - (days_ago * 86400),
            **meta_overrides,
        }
        return {
            "tenant_id": tenant_id,
            "name": "Test Tenant",
            "api_key_hash": "fake-hash",
            "active": True,
            "metadata": meta,
            "created_at": "2026-01-01T00:00:00Z",
        }

    @patch("agency_os.service.email.send_email", return_value=True)
    def test_sends_day1_email(self, mock_send):
        tenant = self._tenant("t-1", "a@b.com", days_ago=1.5)
        manager = self._make_manager([tenant])
        manager.process_nurture_emails()
        assert mock_send.called
        assert manager.db.save_tenant.called
        saved = manager.db.save_tenant.call_args[0][0]
        assert 1 in saved["metadata"]["nurture_emails_sent"]

    @patch("agency_os.service.email.send_email", return_value=True)
    def test_sends_day1_and_day3(self, mock_send):
        tenant = self._tenant("t-2", "b@c.com", days_ago=4)
        manager = self._make_manager([tenant])
        manager.process_nurture_emails()
        assert mock_send.call_count == 2
        saved = manager.db.save_tenant.call_args[0][0]
        assert 1 in saved["metadata"]["nurture_emails_sent"]
        assert 3 in saved["metadata"]["nurture_emails_sent"]

    @patch("agency_os.service.email.send_email", return_value=True)
    def test_sends_all_three(self, mock_send):
        tenant = self._tenant("t-3", "c@d.com", days_ago=8)
        manager = self._make_manager([tenant])
        manager.process_nurture_emails()
        assert mock_send.call_count == 3
        saved = manager.db.save_tenant.call_args[0][0]
        assert saved["metadata"]["nurture_emails_sent"] == [1, 3, 7]

    @patch("agency_os.service.email.send_email", return_value=True)
    def test_skips_already_sent(self, mock_send):
        tenant = self._tenant("t-4", "d@e.com", days_ago=8, nurture_emails_sent=[1, 3])
        manager = self._make_manager([tenant])
        manager.process_nurture_emails()
        assert mock_send.call_count == 1  # only day 7
        saved = manager.db.save_tenant.call_args[0][0]
        assert saved["metadata"]["nurture_emails_sent"] == [1, 3, 7]

    @patch("agency_os.service.email.send_email", return_value=True)
    def test_skips_opted_out_tenant(self, mock_send):
        tenant = self._tenant("t-5", "e@f.com", days_ago=2, email_opt_out=True)
        manager = self._make_manager([tenant])
        manager.process_nurture_emails()
        assert not mock_send.called

    @patch("agency_os.service.email.send_email", return_value=True)
    def test_skips_no_email(self, mock_send):
        tenant = {
            "tenant_id": "t-6",
            "name": "No Email",
            "api_key_hash": "fake",
            "active": True,
            "metadata": {"signed_up_at": time.time() - 200000},
            "created_at": "2026-01-01",
        }
        manager = self._make_manager([tenant])
        manager.process_nurture_emails()
        assert not mock_send.called

    @patch("agency_os.service.email.send_email", return_value=True)
    def test_skips_inactive_tenant(self, mock_send):
        tenant = self._tenant("t-7", "g@h.com", days_ago=2)
        tenant["active"] = False
        manager = self._make_manager([tenant])
        manager.process_nurture_emails()
        assert not mock_send.called

    @patch("agency_os.service.email.send_email", return_value=True)
    def test_too_early_for_any_email(self, mock_send):
        tenant = self._tenant("t-8", "h@i.com", days_ago=0.5)
        manager = self._make_manager([tenant])
        manager.process_nurture_emails()
        assert not mock_send.called

    @patch("agency_os.service.email.send_email", return_value=False)
    def test_failed_send_not_recorded(self, mock_send):
        """If send_email returns False, don't mark the day as sent."""
        tenant = self._tenant("t-9", "i@j.com", days_ago=2)
        manager = self._make_manager([tenant])
        manager.process_nurture_emails()
        assert mock_send.called
        # save_tenant should not be called because nothing was successfully sent
        assert not manager.db.save_tenant.called

    @patch("agency_os.service.email.send_email", return_value=True)
    def test_handles_db_list_error(self, mock_send):
        db = MagicMock()
        db.list_tenants.side_effect = RuntimeError("db down")
        manager = ScheduledJobsManager(_DummyRunFailureTracker(), db)
        # Should not raise
        manager.process_nurture_emails()
        assert not mock_send.called
