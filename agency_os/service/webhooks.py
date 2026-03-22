"""Webhook notification dispatcher for customer event notifications."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Standard event type constants
# ---------------------------------------------------------------------------

TASK_ASSIGNED = "task.assigned"
TASK_COMPLETED = "task.completed"
BUDGET_ALERT = "budget.alert"
CIRCUIT_BREAKER_TRIPPED = "circuit_breaker.tripped"
ORG_STARTED = "org.started"
ORG_STOPPED = "org.stopped"
_RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class WebhookEvent:
    """Represents a single event to be dispatched to subscribers."""

    event_type: str
    org_id: str
    payload: dict[str, Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class WebhookSubscription:
    """A registered webhook endpoint for an organisation."""

    url: str
    events: list[str]
    secret: str  # HMAC-SHA256 signing secret
    webhook_id: str | None = None


# ---------------------------------------------------------------------------
# Delivery log entry
# ---------------------------------------------------------------------------


@dataclass
class DeliveryAttempt:
    """Record of a single dispatch attempt stored in _delivery_log."""

    delivery_id: str | None
    webhook_id: str | None
    url: str
    event_type: str
    org_id: str
    payload: dict[str, Any]
    signature: str
    success: bool
    status_code: int | None = None
    error: str | None = None
    attempt_number: int = 1
    max_attempts: int = 1
    retryable: bool = False
    next_retry_at: str | None = None


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


class WebhookDispatcher:
    """Dispatches webhook events to matching registered subscribers.

    Parameters
    ----------
    live_mode:
        When ``True`` the dispatcher performs actual HTTP POST requests via
        ``httpx``.  When ``False`` (default) all delivery attempts are only
        recorded in ``_delivery_log`` — no network traffic is produced,
        making the class fully testable without any external dependencies.
    """

    def __init__(self, *, live_mode: bool = False) -> None:
        self.live_mode = live_mode
        self.max_attempts = 5
        self.retry_backoff_sec = 1.0
        self.request_timeout_sec = 10.0
        self.circuit_breaker_threshold = 5
        self.circuit_breaker_reset_sec = 300
        self.retry_poll_sec = 1.0
        # { org_id: [WebhookSubscription, ...] }
        self._subscriptions: dict[str, list[WebhookSubscription]] = {}
        self._delivery_log: list[DeliveryAttempt] = []
        self._delivery_repository: Any | None = None
        self._endpoint_failures: dict[str, int] = {}
        self._endpoint_open_until: dict[str, float] = {}
        self._state_lock = threading.Lock()
        self._retry_thread: threading.Thread | None = None
        self._retry_stop = threading.Event()
        self._health_tracker: Any | None = None

    @property
    def max_retries(self) -> int:
        """Backward-compatible alias for max_attempts used by tests/callers."""
        return self.max_attempts

    @max_retries.setter
    def max_retries(self, value: int) -> None:
        self.max_attempts = value

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def subscribe(
        self,
        org_id: str,
        url: str,
        events: list[str],
        secret: str,
        webhook_id: str | None = None,
    ) -> WebhookSubscription:
        """Register a webhook subscription for *org_id*.

        If a subscription for the same *url* already exists for the
        organisation it is replaced.
        """
        subscription = WebhookSubscription(
            webhook_id=webhook_id,
            url=url,
            events=list(events),
            secret=secret,
        )
        subs = self._subscriptions.setdefault(org_id, [])
        # Replace existing registration for same URL
        self._subscriptions[org_id] = [s for s in subs if s.url != url]
        self._subscriptions[org_id].append(subscription)
        return subscription

    def unsubscribe(self, org_id: str, url: str) -> bool:
        """Remove the webhook subscription identified by *org_id* + *url*.

        Returns ``True`` if a subscription was found and removed, ``False``
        if no matching subscription existed.
        """
        subs = self._subscriptions.get(org_id, [])
        filtered = [s for s in subs if s.url != url]
        if len(filtered) == len(subs):
            return False
        self._subscriptions[org_id] = filtered
        return True

    def dispatch(self, event: WebhookEvent) -> list[DeliveryAttempt]:
        """Send *event* to all matching subscribers.

        A subscriber matches when its ``org_id`` equals ``event.org_id`` and
        ``event.event_type`` is present in its ``events`` list.

        Returns the list of ``DeliveryAttempt`` objects recorded during this
        call.
        """
        attempts: list[DeliveryAttempt] = []
        subs = self._subscriptions.get(event.org_id, [])

        for sub in subs:
            if event.event_type not in sub.events:
                continue

            payload_bytes = self._serialise(event)
            signature = self._sign_payload(payload_bytes, sub.secret)
            attempt = self._send(
                sub=sub,
                event=event,
                payload_bytes=payload_bytes,
                signature=signature,
            )
            attempts.append(attempt)
            self._delivery_log.append(attempt)

        return attempts

    def set_delivery_repository(self, repository: Any) -> None:
        """Attach persistence backend used for delivery status and retries."""
        self._delivery_repository = repository

    def set_health_tracker(self, tracker: Any) -> None:
        """Attach a WebhookHealthTracker for delivery metrics."""
        self._health_tracker = tracker

    def start_retry_worker(self) -> None:
        """Start retry worker thread (live mode only)."""
        if not self.live_mode or self._delivery_repository is None:
            return
        if self._retry_thread is not None and self._retry_thread.is_alive():
            return
        if self._retry_thread is not None and not self._retry_thread.is_alive():
            self._retry_thread = None
        self._retry_stop.clear()
        self._retry_thread = threading.Thread(
            target=self._retry_loop,
            name="webhook-retry-worker",
            daemon=True,
        )
        self._retry_thread.start()

    def stop_retry_worker(self, *, timeout_sec: float = 5.0) -> None:
        """Stop retry worker thread and wait briefly for a clean exit."""
        thread = self._retry_thread
        if thread is None:
            return
        self._retry_stop.set()
        if thread.is_alive():
            thread.join(timeout=timeout_sec)
        if thread.is_alive():
            logger.warning(
                "Webhook retry worker did not stop within %.1fs", timeout_sec
            )
            return
        self._retry_thread = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _serialise(event: WebhookEvent) -> bytes:
        """Serialise an event to a canonical JSON byte string."""
        body: dict[str, Any] = {
            "event_type": event.event_type,
            "org_id": event.org_id,
            "timestamp": event.timestamp.isoformat(),
            "payload": event.payload,
        }
        return json.dumps(body, separators=(",", ":"), sort_keys=True).encode()

    @staticmethod
    def _sign_payload(payload_bytes: bytes, secret: str) -> str:
        """Return an HMAC-SHA256 hex digest for *payload_bytes*.

        The signature is formatted as ``sha256=<hex_digest>`` to follow the
        convention used by GitHub and Stripe webhooks.
        """
        digest = hmac.new(
            secret.encode(),
            msg=payload_bytes,
            digestmod=hashlib.sha256,
        ).hexdigest()
        return f"sha256={digest}"

    def _send(
        self,
        *args: Any,
        sub: WebhookSubscription | None = None,
        event: WebhookEvent | None = None,
        payload_bytes: bytes | None = None,
        signature: str | None = None,
        delivery_id: str | None = None,
        attempt_number: int = 1,
        event_timestamp_header: str | None = None,
    ) -> DeliveryAttempt:
        """Deliver one webhook attempt and schedule retry if needed."""
        legacy_inline_retry = bool(args)
        if args:
            # Backward-compatible call style:
            # _send(url, event, signature)
            if len(args) != 3:
                raise TypeError(
                    "_send() positional usage requires (url, event, signature)"
                )
            url, positional_event, positional_signature = args
            if not isinstance(url, str) or not isinstance(
                positional_event, WebhookEvent
            ):
                raise TypeError(
                    "_send() positional usage requires (str, WebhookEvent, str)"
                )
            sub = WebhookSubscription(
                webhook_id=None,
                url=url,
                events=[positional_event.event_type],
                secret="",
            )
            event = positional_event
            signature = positional_signature
            payload_bytes = payload_bytes or self._serialise(event)

        if sub is None or event is None or payload_bytes is None or signature is None:
            raise TypeError(
                "_send() requires either positional (url, event, signature) or "
                "keyword args: sub=..., event=..., payload_bytes=..., signature=..."
            )

        timestamp_header = event_timestamp_header or str(
            int(event.timestamp.timestamp())
        )
        status_code: int | None = None
        error: str | None = None
        retryable = False

        if self._is_circuit_open(sub.url):
            error = "Circuit breaker open for endpoint"
            retryable = True
            if self._health_tracker is not None:
                self._health_tracker.record(success=False, latency_ms=0.0)
        else:
            t0 = time.monotonic()
            success, status_code, error, retryable = self._send_once(
                sub.url,
                payload_bytes,
                signature,
                event.event_type,
                timestamp_header,
            )
            latency_ms = (time.monotonic() - t0) * 1000.0
            if self._health_tracker is not None:
                self._health_tracker.record(success=success, latency_ms=latency_ms)
            if success:
                self._record_endpoint_success(sub.url)
            else:
                self._record_endpoint_failure(sub.url)

            if success:
                attempt = DeliveryAttempt(
                    delivery_id=delivery_id,
                    webhook_id=sub.webhook_id,
                    url=sub.url,
                    event_type=event.event_type,
                    org_id=event.org_id,
                    payload=event.payload,
                    signature=signature,
                    success=True,
                    status_code=status_code,
                    attempt_number=attempt_number,
                    max_attempts=self.max_attempts,
                    retryable=False,
                )
                self._persist_attempt(
                    delivery_id=delivery_id,
                    event=event,
                    payload_bytes=payload_bytes,
                    attempt=attempt,
                )
                return attempt

        next_retry_at: str | None = None
        if retryable and attempt_number < self.max_attempts:
            delay = self.retry_backoff_sec * (2 ** (attempt_number - 1))
            next_retry_at = datetime.fromtimestamp(
                time.time() + delay, tz=timezone.utc
            ).isoformat()

        attempt = DeliveryAttempt(
            delivery_id=delivery_id,
            webhook_id=sub.webhook_id,
            url=sub.url,
            event_type=event.event_type,
            org_id=event.org_id,
            payload=event.payload,
            signature=signature,
            success=False,
            status_code=status_code,
            error=error,
            attempt_number=attempt_number,
            max_attempts=self.max_attempts,
            retryable=retryable,
            next_retry_at=next_retry_at,
        )
        self._persist_attempt(
            delivery_id=delivery_id,
            event=event,
            payload_bytes=payload_bytes,
            attempt=attempt,
        )
        if legacy_inline_retry and retryable and attempt_number < self.max_attempts:
            delay = self.retry_backoff_sec * (2 ** (attempt_number - 1))
            if delay > 0:
                time.sleep(delay)
            return self._send(
                sub=sub,
                event=event,
                payload_bytes=payload_bytes,
                signature=signature,
                delivery_id=delivery_id,
                attempt_number=attempt_number + 1,
                event_timestamp_header=event_timestamp_header,
            )
        return attempt

    def _persist_attempt(
        self,
        *,
        delivery_id: str | None,
        event: WebhookEvent,
        payload_bytes: bytes,
        attempt: DeliveryAttempt,
    ) -> None:
        if self._delivery_repository is None:
            return
        if delivery_id is None:
            delivery_id = self._delivery_repository.create_delivery_record(
                webhook_id=attempt.webhook_id,
                tenant_id=event.org_id,
                url=attempt.url,
                event_type=event.event_type,
                org_id=event.org_id,
                payload_json=payload_bytes.decode(),
                signature=attempt.signature,
                event_timestamp=int(event.timestamp.timestamp()),
                max_attempts=self.max_attempts,
            )
            attempt.delivery_id = delivery_id

        self._delivery_repository.record_delivery_attempt(
            delivery_id=delivery_id,
            attempt_number=attempt.attempt_number,
            success=attempt.success,
            status_code=attempt.status_code,
            error=attempt.error,
            retryable=attempt.retryable,
            next_retry_at=attempt.next_retry_at,
        )

    def _retry_loop(self) -> None:
        while not self._retry_stop.wait(self.retry_poll_sec):
            if self._delivery_repository is None:
                continue
            try:
                due = self._delivery_repository.list_due_retries(limit=20)
            except Exception:  # noqa: BLE001
                logger.exception("Failed to load due webhook retries")
                continue
            for row in due:
                try:
                    payload = row.get("payload_json", "{}")
                    payload_bytes = payload.encode()
                    event_ts = row.get("event_timestamp")
                    if event_ts is None:
                        event_ts = int(time.time())

                    payload_doc = json.loads(payload)
                    event = WebhookEvent(
                        event_type=row["event_type"],
                        org_id=row["org_id"],
                        payload=payload_doc.get("payload", {}),
                        timestamp=datetime.fromtimestamp(event_ts, tz=timezone.utc),
                    )
                    sub = WebhookSubscription(
                        webhook_id=row.get("webhook_id"),
                        url=row["url"],
                        events=[row["event_type"]],
                        secret="",
                    )
                    self._send(
                        sub=sub,
                        event=event,
                        payload_bytes=payload_bytes,
                        signature=row["signature"],
                        delivery_id=row["id"],
                        attempt_number=int(row["attempt_count"]) + 1,
                        event_timestamp_header=str(event_ts),
                    )
                except json.JSONDecodeError:
                    logger.exception(
                        "Skipping malformed webhook retry payload for delivery %s",
                        row.get("id"),
                    )
                    self._delivery_repository.record_delivery_attempt(
                        delivery_id=row["id"],
                        attempt_number=int(row.get("attempt_count", 0)) + 1,
                        success=False,
                        status_code=None,
                        error="Malformed payload_json in retry record",
                        retryable=False,
                        next_retry_at=None,
                    )
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "Webhook retry worker failed for delivery %s", row.get("id")
                    )

    def _is_circuit_open(self, url: str) -> bool:
        with self._state_lock:
            opened_until = self._endpoint_open_until.get(url)
            if opened_until is None:
                return False
            if opened_until <= time.time():
                self._endpoint_open_until.pop(url, None)
                self._endpoint_failures[url] = 0
                return False
            return True

    def _record_endpoint_failure(self, url: str) -> None:
        with self._state_lock:
            failures = self._endpoint_failures.get(url, 0) + 1
            self._endpoint_failures[url] = failures
            if failures >= self.circuit_breaker_threshold:
                self._endpoint_open_until[url] = (
                    time.time() + self.circuit_breaker_reset_sec
                )
                self._endpoint_failures[url] = 0

    def _record_endpoint_success(self, url: str) -> None:
        with self._state_lock:
            self._endpoint_failures[url] = 0
            self._endpoint_open_until.pop(url, None)

    def _send_once(
        self,
        url: str,
        payload_bytes: bytes,
        signature: str,
        event_type: str,
        event_timestamp_header: str,
    ) -> tuple[bool, int | None, str | None, bool]:
        if not self.live_mode:
            return (True, None, None, False)
        try:
            import ipaddress
            import socket
            from urllib.parse import urlparse

            import httpx

            parsed = urlparse(url)
            if parsed.hostname:
                try:
                    resolved = socket.getaddrinfo(parsed.hostname, None)
                    for _fam, _typ, _prot, _cname, sockaddr in resolved:
                        ip = ipaddress.ip_address(sockaddr[0])
                        if (
                            ip.is_private
                            or ip.is_loopback
                            or ip.is_link_local
                            or ip.is_reserved
                        ):
                            return (
                                False,
                                None,
                                "URL resolves to private/internal address (blocked)",
                                False,
                            )
                except socket.gaierror:
                    return (False, None, "Cannot resolve hostname", True)

            headers = {
                "Content-Type": "application/json",
                "X-AgencyOS-Signature": signature,
                "X-AgencyOS-Event": event_type,
                "X-AgencyOS-Timestamp": event_timestamp_header,
            }
            response = httpx.post(
                url,
                content=payload_bytes,
                headers=headers,
                timeout=self.request_timeout_sec,
            )
            if response.is_success:
                return (True, response.status_code, None, False)
            return (
                False,
                response.status_code,
                f"HTTP {response.status_code}",
                response.status_code in _RETRYABLE_STATUS_CODES,
            )
        except Exception as exc:  # noqa: BLE001
            return (False, None, str(exc), True)
