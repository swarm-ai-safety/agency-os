"""Unit tests for agency_os.service.webhooks."""

from __future__ import annotations

import hashlib
import hmac
import time
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from agency_os.service.webhooks import (
    BUDGET_ALERT,
    CIRCUIT_BREAKER_TRIPPED,
    ORG_STARTED,
    ORG_STOPPED,
    TASK_ASSIGNED,
    TASK_COMPLETED,
    DeliveryAttempt,
    WebhookDispatcher,
    WebhookEvent,
    WebhookSubscription,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def dispatcher() -> WebhookDispatcher:
    """Return a fresh dispatcher in test (non-live) mode."""
    return WebhookDispatcher(live_mode=False)


@pytest.fixture()
def fixed_ts() -> datetime:
    return datetime(2026, 3, 3, 12, 0, 0, tzinfo=timezone.utc)


def make_event(
    event_type: str = TASK_COMPLETED,
    org_id: str = "org-1",
    payload: dict | None = None,
    timestamp: datetime | None = None,
) -> WebhookEvent:
    return WebhookEvent(
        event_type=event_type,
        org_id=org_id,
        payload=payload or {"task_id": "t-99"},
        timestamp=timestamp or datetime(2026, 3, 3, 12, 0, 0, tzinfo=timezone.utc),
    )


# ---------------------------------------------------------------------------
# WebhookEvent / WebhookSubscription dataclass tests
# ---------------------------------------------------------------------------


class TestDataclasses:
    def test_webhook_event_fields(self, fixed_ts):
        event = WebhookEvent(
            event_type=TASK_ASSIGNED,
            org_id="org-abc",
            payload={"task_id": "t-1"},
            timestamp=fixed_ts,
        )
        assert event.event_type == TASK_ASSIGNED
        assert event.org_id == "org-abc"
        assert event.payload == {"task_id": "t-1"}
        assert event.timestamp == fixed_ts

    def test_webhook_event_default_timestamp(self):
        event = WebhookEvent(event_type=TASK_COMPLETED, org_id="org-x", payload={})
        assert event.timestamp is not None
        assert event.timestamp.tzinfo is not None  # timezone-aware

    def test_webhook_subscription_fields(self):
        sub = WebhookSubscription(
            url="https://example.com/hook",
            events=[TASK_COMPLETED, BUDGET_ALERT],
            secret="s3cr3t",
        )
        assert sub.url == "https://example.com/hook"
        assert TASK_COMPLETED in sub.events
        assert sub.secret == "s3cr3t"


# ---------------------------------------------------------------------------
# Event type constants
# ---------------------------------------------------------------------------


class TestEventTypeConstants:
    def test_constants_are_strings(self):
        for constant in (
            TASK_ASSIGNED,
            TASK_COMPLETED,
            BUDGET_ALERT,
            CIRCUIT_BREAKER_TRIPPED,
            ORG_STARTED,
            ORG_STOPPED,
        ):
            assert isinstance(constant, str)
            assert len(constant) > 0

    def test_constants_are_unique(self):
        constants = [
            TASK_ASSIGNED,
            TASK_COMPLETED,
            BUDGET_ALERT,
            CIRCUIT_BREAKER_TRIPPED,
            ORG_STARTED,
            ORG_STOPPED,
        ]
        assert len(constants) == len(set(constants))


# ---------------------------------------------------------------------------
# Subscribe tests
# ---------------------------------------------------------------------------


class TestSubscribe:
    def test_subscribe_returns_subscription(self, dispatcher):
        sub = dispatcher.subscribe(
            "org-1", "https://example.com/hook", [TASK_COMPLETED], "secret"
        )
        assert isinstance(sub, WebhookSubscription)
        assert sub.url == "https://example.com/hook"
        assert sub.events == [TASK_COMPLETED]
        assert sub.secret == "secret"

    def test_subscribe_stores_subscription(self, dispatcher):
        dispatcher.subscribe("org-1", "https://a.example.com", [TASK_COMPLETED], "s1")
        assert "org-1" in dispatcher._subscriptions
        assert len(dispatcher._subscriptions["org-1"]) == 1

    def test_subscribe_multiple_orgs(self, dispatcher):
        dispatcher.subscribe("org-1", "https://a.example.com", [TASK_COMPLETED], "s1")
        dispatcher.subscribe("org-2", "https://b.example.com", [BUDGET_ALERT], "s2")
        assert len(dispatcher._subscriptions["org-1"]) == 1
        assert len(dispatcher._subscriptions["org-2"]) == 1

    def test_subscribe_multiple_urls_same_org(self, dispatcher):
        dispatcher.subscribe("org-1", "https://a.example.com", [TASK_COMPLETED], "s1")
        dispatcher.subscribe("org-1", "https://b.example.com", [BUDGET_ALERT], "s2")
        assert len(dispatcher._subscriptions["org-1"]) == 2

    def test_subscribe_replaces_existing_url(self, dispatcher):
        dispatcher.subscribe("org-1", "https://a.example.com", [TASK_COMPLETED], "old")
        dispatcher.subscribe("org-1", "https://a.example.com", [BUDGET_ALERT], "new")
        subs = dispatcher._subscriptions["org-1"]
        assert len(subs) == 1
        assert subs[0].secret == "new"
        assert subs[0].events == [BUDGET_ALERT]

    def test_subscribe_multiple_events(self, dispatcher):
        events = [TASK_COMPLETED, BUDGET_ALERT, ORG_STOPPED]
        dispatcher.subscribe("org-1", "https://a.example.com", events, "s")
        subs = dispatcher._subscriptions["org-1"]
        assert subs[0].events == events


# ---------------------------------------------------------------------------
# Unsubscribe tests
# ---------------------------------------------------------------------------


class TestUnsubscribe:
    def test_unsubscribe_returns_true_when_found(self, dispatcher):
        dispatcher.subscribe("org-1", "https://a.example.com", [TASK_COMPLETED], "s")
        result = dispatcher.unsubscribe("org-1", "https://a.example.com")
        assert result is True

    def test_unsubscribe_removes_subscription(self, dispatcher):
        dispatcher.subscribe("org-1", "https://a.example.com", [TASK_COMPLETED], "s")
        dispatcher.unsubscribe("org-1", "https://a.example.com")
        assert dispatcher._subscriptions["org-1"] == []

    def test_unsubscribe_returns_false_when_not_found(self, dispatcher):
        result = dispatcher.unsubscribe("org-1", "https://nonexistent.example.com")
        assert result is False

    def test_unsubscribe_only_removes_target_url(self, dispatcher):
        dispatcher.subscribe("org-1", "https://a.example.com", [TASK_COMPLETED], "s1")
        dispatcher.subscribe("org-1", "https://b.example.com", [BUDGET_ALERT], "s2")
        dispatcher.unsubscribe("org-1", "https://a.example.com")
        subs = dispatcher._subscriptions["org-1"]
        assert len(subs) == 1
        assert subs[0].url == "https://b.example.com"

    def test_unsubscribe_unknown_org_returns_false(self, dispatcher):
        result = dispatcher.unsubscribe("ghost-org", "https://a.example.com")
        assert result is False


# ---------------------------------------------------------------------------
# Signature verification tests
# ---------------------------------------------------------------------------


class TestSignPayload:
    def test_signature_format(self, dispatcher):
        sig = dispatcher._sign_payload(b"hello world", "mysecret")
        assert sig.startswith("sha256=")

    def test_signature_is_deterministic(self, dispatcher):
        sig1 = dispatcher._sign_payload(b"data", "secret")
        sig2 = dispatcher._sign_payload(b"data", "secret")
        assert sig1 == sig2

    def test_signature_differs_for_different_payloads(self, dispatcher):
        sig1 = dispatcher._sign_payload(b"payload-A", "secret")
        sig2 = dispatcher._sign_payload(b"payload-B", "secret")
        assert sig1 != sig2

    def test_signature_differs_for_different_secrets(self, dispatcher):
        sig1 = dispatcher._sign_payload(b"data", "secret-1")
        sig2 = dispatcher._sign_payload(b"data", "secret-2")
        assert sig1 != sig2

    def test_signature_matches_manual_hmac(self, dispatcher):
        payload = b"test payload"
        secret = "supersecret"
        expected = (
            "sha256="
            + hmac.new(
                secret.encode(), msg=payload, digestmod=hashlib.sha256
            ).hexdigest()
        )
        assert dispatcher._sign_payload(payload, secret) == expected

    def test_constant_time_comparison(self, dispatcher):
        """Ensure signatures can be compared with hmac.compare_digest."""
        payload = b"important data"
        secret = "key"
        sig = dispatcher._sign_payload(payload, secret)
        assert hmac.compare_digest(sig, sig)


# ---------------------------------------------------------------------------
# Dispatch tests
# ---------------------------------------------------------------------------


class TestDispatch:
    def test_dispatch_returns_delivery_attempts(self, dispatcher):
        dispatcher.subscribe("org-1", "https://hook.example.com", [TASK_COMPLETED], "s")
        event = make_event(TASK_COMPLETED, "org-1")
        attempts = dispatcher.dispatch(event)
        assert len(attempts) == 1
        assert isinstance(attempts[0], DeliveryAttempt)

    def test_dispatch_records_in_delivery_log(self, dispatcher):
        dispatcher.subscribe("org-1", "https://hook.example.com", [TASK_COMPLETED], "s")
        event = make_event(TASK_COMPLETED, "org-1")
        dispatcher.dispatch(event)
        assert len(dispatcher._delivery_log) == 1

    def test_dispatch_delivery_attempt_fields(self, dispatcher):
        dispatcher.subscribe("org-1", "https://hook.example.com", [TASK_COMPLETED], "s")
        event = make_event(TASK_COMPLETED, "org-1", payload={"task_id": "t-5"})
        attempts = dispatcher.dispatch(event)
        attempt = attempts[0]
        assert attempt.url == "https://hook.example.com"
        assert attempt.event_type == TASK_COMPLETED
        assert attempt.org_id == "org-1"
        assert attempt.payload == {"task_id": "t-5"}
        assert attempt.signature.startswith("sha256=")
        assert attempt.success is True

    def test_dispatch_no_subscribers_returns_empty(self, dispatcher):
        event = make_event(TASK_COMPLETED, "org-with-no-subs")
        attempts = dispatcher.dispatch(event)
        assert attempts == []
        assert dispatcher._delivery_log == []

    def test_dispatch_sends_to_all_matching_subscribers(self, dispatcher):
        dispatcher.subscribe("org-1", "https://a.example.com", [TASK_COMPLETED], "s1")
        dispatcher.subscribe("org-1", "https://b.example.com", [TASK_COMPLETED], "s2")
        event = make_event(TASK_COMPLETED, "org-1")
        attempts = dispatcher.dispatch(event)
        assert len(attempts) == 2
        urls = {a.url for a in attempts}
        assert urls == {"https://a.example.com", "https://b.example.com"}

    def test_dispatch_accumulates_log_across_calls(self, dispatcher):
        dispatcher.subscribe(
            "org-1", "https://hook.example.com", [TASK_COMPLETED, BUDGET_ALERT], "s"
        )
        dispatcher.dispatch(make_event(TASK_COMPLETED, "org-1"))
        dispatcher.dispatch(make_event(BUDGET_ALERT, "org-1"))
        assert len(dispatcher._delivery_log) == 2


# ---------------------------------------------------------------------------
# Event filtering tests
# ---------------------------------------------------------------------------


class TestEventFiltering:
    def test_dispatch_skips_non_subscribed_event_type(self, dispatcher):
        dispatcher.subscribe("org-1", "https://hook.example.com", [TASK_COMPLETED], "s")
        event = make_event(BUDGET_ALERT, "org-1")
        attempts = dispatcher.dispatch(event)
        assert attempts == []

    def test_dispatch_skips_different_org(self, dispatcher):
        dispatcher.subscribe("org-1", "https://hook.example.com", [TASK_COMPLETED], "s")
        event = make_event(TASK_COMPLETED, "org-2")
        attempts = dispatcher.dispatch(event)
        assert attempts == []

    def test_dispatch_matches_only_correct_org_and_event(self, dispatcher):
        dispatcher.subscribe("org-1", "https://a.example.com", [TASK_COMPLETED], "s1")
        dispatcher.subscribe("org-2", "https://b.example.com", [TASK_COMPLETED], "s2")
        event = make_event(TASK_COMPLETED, "org-1")
        attempts = dispatcher.dispatch(event)
        assert len(attempts) == 1
        assert attempts[0].url == "https://a.example.com"

    def test_subscriber_with_multiple_events_only_fires_once_per_dispatch(
        self, dispatcher
    ):
        events = [TASK_COMPLETED, BUDGET_ALERT, ORG_STOPPED]
        dispatcher.subscribe("org-1", "https://hook.example.com", events, "s")
        attempts = dispatcher.dispatch(make_event(TASK_COMPLETED, "org-1"))
        assert len(attempts) == 1

    def test_dispatch_circuit_breaker_event(self, dispatcher):
        dispatcher.subscribe(
            "org-1", "https://hook.example.com", [CIRCUIT_BREAKER_TRIPPED], "s"
        )
        event = make_event(
            CIRCUIT_BREAKER_TRIPPED, "org-1", payload={"service": "billing"}
        )
        attempts = dispatcher.dispatch(event)
        assert len(attempts) == 1
        assert attempts[0].event_type == CIRCUIT_BREAKER_TRIPPED

    def test_dispatch_org_lifecycle_events(self, dispatcher):
        dispatcher.subscribe(
            "org-1", "https://hook.example.com", [ORG_STARTED, ORG_STOPPED], "s"
        )
        start_attempts = dispatcher.dispatch(make_event(ORG_STARTED, "org-1"))
        stop_attempts = dispatcher.dispatch(make_event(ORG_STOPPED, "org-1"))
        assert len(start_attempts) == 1
        assert len(stop_attempts) == 1
        assert start_attempts[0].event_type == ORG_STARTED
        assert stop_attempts[0].event_type == ORG_STOPPED

    def test_dispatch_does_not_fire_for_unrelated_event_in_multi_event_subscription(
        self, dispatcher
    ):
        dispatcher.subscribe(
            "org-1", "https://hook.example.com", [TASK_ASSIGNED, ORG_STARTED], "s"
        )
        attempts = dispatcher.dispatch(make_event(TASK_COMPLETED, "org-1"))
        assert attempts == []


# ---------------------------------------------------------------------------
# Signature consistency in delivery log
# ---------------------------------------------------------------------------


class TestSignatureInDeliveryLog:
    def test_signature_in_log_matches_computed(self, dispatcher):
        secret = "webhook-secret"
        dispatcher.subscribe(
            "org-1", "https://hook.example.com", [TASK_COMPLETED], secret
        )
        event = make_event(TASK_COMPLETED, "org-1")
        dispatcher.dispatch(event)

        attempt = dispatcher._delivery_log[0]
        payload_bytes = dispatcher._serialise(event)
        expected_sig = dispatcher._sign_payload(payload_bytes, secret)
        assert attempt.signature == expected_sig

    def test_different_secrets_produce_different_signatures(self, dispatcher):
        dispatcher.subscribe(
            "org-1", "https://a.example.com", [TASK_COMPLETED], "secret-A"
        )
        dispatcher.subscribe(
            "org-1", "https://b.example.com", [TASK_COMPLETED], "secret-B"
        )
        event = make_event(TASK_COMPLETED, "org-1")
        attempts = dispatcher.dispatch(event)
        assert len(attempts) == 2
        sigs = {a.signature for a in attempts}
        assert len(sigs) == 2  # both signatures must be distinct


class TestLiveModeRetry:
    def test_retries_retryable_status_then_succeeds(self, monkeypatch):
        dispatcher = WebhookDispatcher(live_mode=True)
        dispatcher.max_retries = 2
        dispatcher.retry_backoff_sec = 0.0

        import socket

        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda *_args, **_kwargs: [(None, None, None, None, ("8.8.8.8", 0))],
        )

        import httpx

        calls = {"n": 0}

        class FakeResponse:
            def __init__(self, status_code: int):
                self.status_code = status_code
                self.is_success = 200 <= status_code < 300

        def fake_post(*_args, **_kwargs):
            calls["n"] += 1
            return FakeResponse(503 if calls["n"] == 1 else 200)

        monkeypatch.setattr(httpx, "post", fake_post)

        event = make_event(TASK_COMPLETED, "org-1")
        attempt = dispatcher._send("https://example.com/hook", event, "sha256=test")

        assert calls["n"] == 2
        assert attempt.success is True
        assert attempt.status_code == 200

    def test_does_not_retry_non_retryable_status(self, monkeypatch):
        dispatcher = WebhookDispatcher(live_mode=True)
        dispatcher.max_retries = 2
        dispatcher.retry_backoff_sec = 0.0

        import socket

        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda *_args, **_kwargs: [(None, None, None, None, ("8.8.8.8", 0))],
        )

        import httpx

        calls = {"n": 0}

        class FakeResponse:
            def __init__(self, status_code: int):
                self.status_code = status_code
                self.is_success = 200 <= status_code < 300

        def fake_post(*_args, **_kwargs):
            calls["n"] += 1
            return FakeResponse(400)

        monkeypatch.setattr(httpx, "post", fake_post)

        event = make_event(TASK_COMPLETED, "org-1")
        attempt = dispatcher._send("https://example.com/hook", event, "sha256=test")

        assert calls["n"] == 1
        assert attempt.success is False
        assert attempt.status_code == 400


class _OnePassStop:
    """Stop-event test double that allows exactly one retry-loop pass."""

    def __init__(self) -> None:
        self.calls = 0

    def wait(self, _timeout: float) -> bool:
        self.calls += 1
        return self.calls > 1


class TestRetryWorkerRobustness:
    def test_retry_worker_start_and_stop(self):
        dispatcher = WebhookDispatcher(live_mode=True)
        dispatcher.retry_poll_sec = 0.01

        class FakeRepo:
            def list_due_retries(self, *, limit: int):
                assert limit == 20
                return []

        dispatcher.set_delivery_repository(FakeRepo())
        dispatcher.start_retry_worker()
        time.sleep(0.02)
        dispatcher.stop_retry_worker(timeout_sec=1.0)

        assert dispatcher._retry_thread is None

    def test_retry_loop_marks_malformed_payload_non_retryable(self):
        dispatcher = WebhookDispatcher(live_mode=True)
        repo_calls: list[dict] = []

        class FakeRepo:
            def list_due_retries(self, *, limit: int):
                assert limit == 20
                return [
                    {
                        "id": "del-1",
                        "payload_json": "{not-json",
                        "event_timestamp": 1700000000,
                        "event_type": TASK_COMPLETED,
                        "org_id": "org-1",
                        "url": "https://example.com/hook",
                        "signature": "sha256=test",
                        "attempt_count": 1,
                    }
                ]

            def record_delivery_attempt(self, **kwargs):
                repo_calls.append(kwargs)

        dispatcher.set_delivery_repository(FakeRepo())
        dispatcher._retry_stop = _OnePassStop()

        dispatcher._retry_loop()

        assert len(repo_calls) == 1
        assert repo_calls[0]["delivery_id"] == "del-1"
        assert repo_calls[0]["attempt_number"] == 2
        assert repo_calls[0]["success"] is False
        assert repo_calls[0]["retryable"] is False
        assert repo_calls[0]["next_retry_at"] is None

    def test_retry_loop_continues_when_loading_due_retries_fails(self):
        dispatcher = WebhookDispatcher(live_mode=True)
        calls = {"n": 0}

        class FailingRepo:
            def list_due_retries(self, *, limit: int):
                calls["n"] += 1
                assert limit == 20
                raise RuntimeError("db unavailable")

        dispatcher.set_delivery_repository(FailingRepo())
        dispatcher._retry_stop = _OnePassStop()

        with patch("agency_os.service.webhooks.logger.exception") as mock_exception:
            dispatcher._retry_loop()

        assert calls["n"] == 1
        mock_exception.assert_called_once_with("Failed to load due webhook retries")
