"""Tests for agency_os.observability."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone

from agency_os.observability import (
    METRIC_BID_PLACED,
    METRIC_BUDGET_DEPLETED,
    METRIC_CIRCUIT_BREAKER_TRIPPED,
    METRIC_TASK_COMPLETED,
    METRIC_TASK_SUBMITTED,
    EventTracker,
    HealthCheck,
    bind_request_id,
    configure_logging,
    get_logger,
    reset_request_id,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fresh_agency_logger() -> logging.Logger:
    """Return the agency_os root logger with all handlers stripped."""
    logger = logging.getLogger("agency_os")
    logger.handlers.clear()
    return logger


# ---------------------------------------------------------------------------
# Metric constants
# ---------------------------------------------------------------------------


class TestMetricConstants:
    def test_task_submitted(self):
        assert METRIC_TASK_SUBMITTED == "task.submitted"

    def test_task_completed(self):
        assert METRIC_TASK_COMPLETED == "task.completed"

    def test_bid_placed(self):
        assert METRIC_BID_PLACED == "bid.placed"

    def test_budget_depleted(self):
        assert METRIC_BUDGET_DEPLETED == "budget.depleted"

    def test_circuit_breaker_tripped(self):
        assert METRIC_CIRCUIT_BREAKER_TRIPPED == "circuit_breaker.tripped"


# ---------------------------------------------------------------------------
# configure_logging
# ---------------------------------------------------------------------------


class TestConfigureLogging:
    def setup_method(self):
        _fresh_agency_logger()

    def test_default_level_is_info(self, capsys):
        configure_logging()
        logger = get_logger("test_default")
        logger.info("hello info")
        logger.debug("should not appear")
        captured = capsys.readouterr()
        assert "hello info" in captured.err
        assert "should not appear" not in captured.err

    def test_debug_level_shows_debug_messages(self, capsys):
        configure_logging(level="DEBUG")
        logger = get_logger("test_debug")
        logger.debug("debug line")
        captured = capsys.readouterr()
        assert "debug line" in captured.err

    def test_warning_level_hides_info(self, capsys):
        configure_logging(level="WARNING")
        logger = get_logger("test_warning")
        logger.info("should be hidden")
        logger.warning("visible warning")
        captured = capsys.readouterr()
        assert "should be hidden" not in captured.err
        assert "visible warning" in captured.err

    def test_plain_format_contains_level(self, capsys):
        configure_logging(json_format=False)
        logger = get_logger("test_plain")
        logger.info("plain message")
        captured = capsys.readouterr()
        assert "INFO" in captured.err
        assert "plain message" in captured.err

    def test_json_format_outputs_valid_json(self, capsys):
        configure_logging(json_format=True)
        logger = get_logger("test_json")
        logger.info("json message")
        captured = capsys.readouterr()
        line = captured.err.strip().splitlines()[-1]
        payload = json.loads(line)
        assert payload["message"] == "json message"
        assert payload["level"] == "INFO"
        assert "timestamp" in payload
        assert "logger" in payload

    def test_json_format_logger_name(self, capsys):
        configure_logging(json_format=True)
        logger = get_logger("my_module")
        logger.warning("w")
        captured = capsys.readouterr()
        line = captured.err.strip().splitlines()[-1]
        payload = json.loads(line)
        assert payload["logger"] == "agency_os.my_module"

    def test_repeated_configure_does_not_duplicate_handlers(self, capsys):
        configure_logging()
        configure_logging()
        root = logging.getLogger("agency_os")
        assert len(root.handlers) == 1

    def test_level_is_case_insensitive(self, capsys):
        configure_logging(level="debug")
        logger = get_logger("case_test")
        logger.debug("lower case level")
        captured = capsys.readouterr()
        assert "lower case level" in captured.err

    def test_plain_format_includes_request_id(self, capsys):
        configure_logging(json_format=False)
        token = bind_request_id("req-123")
        logger = get_logger("request_plain")
        logger.info("plain request")
        reset_request_id(token)
        captured = capsys.readouterr()
        assert "request_id=req-123" in captured.err

    def test_json_format_includes_request_id(self, capsys):
        configure_logging(json_format=True)
        token = bind_request_id("req-456")
        logger = get_logger("request_json")
        logger.info("json request")
        reset_request_id(token)
        captured = capsys.readouterr()
        line = captured.err.strip().splitlines()[-1]
        payload = json.loads(line)
        assert payload["request_id"] == "req-456"


# ---------------------------------------------------------------------------
# get_logger
# ---------------------------------------------------------------------------


class TestGetLogger:
    def test_returns_logger_instance(self):
        logger = get_logger("foo")
        assert isinstance(logger, logging.Logger)

    def test_name_has_prefix(self):
        logger = get_logger("bar.baz")
        assert logger.name == "agency_os.bar.baz"

    def test_different_names_are_different_loggers(self):
        a = get_logger("alpha")
        b = get_logger("beta")
        assert a is not b

    def test_same_name_returns_same_logger(self):
        a = get_logger("same")
        b = get_logger("same")
        assert a is b


# ---------------------------------------------------------------------------
# EventTracker
# ---------------------------------------------------------------------------


class TestEventTrackerTrack:
    def test_track_single_event(self):
        tracker = EventTracker()
        tracker.track(METRIC_TASK_SUBMITTED)
        events = tracker.get_events()
        assert len(events) == 1
        assert events[0]["name"] == METRIC_TASK_SUBMITTED

    def test_track_with_metadata(self):
        tracker = EventTracker()
        tracker.track(METRIC_BID_PLACED, agent="dev", amount=50)
        events = tracker.get_events()
        assert events[0]["metadata"] == {"agent": "dev", "amount": 50}

    def test_track_multiple_different_events(self):
        tracker = EventTracker()
        tracker.track(METRIC_TASK_SUBMITTED)
        tracker.track(METRIC_TASK_COMPLETED)
        tracker.track(METRIC_BID_PLACED)
        assert len(tracker.get_events()) == 3

    def test_timestamp_is_iso8601(self):
        tracker = EventTracker()
        tracker.track(METRIC_TASK_SUBMITTED)
        ts = tracker.get_events()[0]["timestamp"]
        # Should parse without error
        parsed = datetime.fromisoformat(ts)
        assert parsed.tzinfo is not None

    def test_metadata_is_copied(self):
        tracker = EventTracker()
        meta = {"key": "value"}
        tracker.track(METRIC_TASK_SUBMITTED, **meta)
        meta["key"] = "mutated"
        assert tracker.get_events()[0]["metadata"]["key"] == "value"


class TestEventTrackerGetEvents:
    def setup_method(self):
        self.tracker = EventTracker()
        self.tracker.track(METRIC_TASK_SUBMITTED, task_id="t1")
        self.tracker.track(METRIC_TASK_SUBMITTED, task_id="t2")
        self.tracker.track(METRIC_TASK_COMPLETED, task_id="t1")
        self.tracker.track(METRIC_BID_PLACED, agent="dev")

    def test_no_filter_returns_all(self):
        assert len(self.tracker.get_events()) == 4

    def test_filter_by_event_name(self):
        submitted = self.tracker.get_events(event_name=METRIC_TASK_SUBMITTED)
        assert len(submitted) == 2
        assert all(e["name"] == METRIC_TASK_SUBMITTED for e in submitted)

    def test_filter_by_event_name_no_match(self):
        depleted = self.tracker.get_events(event_name=METRIC_BUDGET_DEPLETED)
        assert depleted == []

    def test_filter_by_since_excludes_earlier(self):
        future = datetime.now(tz=timezone.utc) + timedelta(hours=1)
        assert self.tracker.get_events(since=future) == []

    def test_filter_by_since_includes_recent(self):
        past = datetime.now(tz=timezone.utc) - timedelta(hours=1)
        events = self.tracker.get_events(since=past)
        assert len(events) == 4

    def test_combined_filter(self):
        past = datetime.now(tz=timezone.utc) - timedelta(hours=1)
        events = self.tracker.get_events(event_name=METRIC_TASK_SUBMITTED, since=past)
        assert len(events) == 2

    def test_empty_tracker_returns_empty_list(self):
        tracker = EventTracker()
        assert tracker.get_events() == []
        assert tracker.get_events(event_name=METRIC_TASK_SUBMITTED) == []


class TestEventTrackerSummary:
    def test_summary_counts_correctly(self):
        tracker = EventTracker()
        tracker.track(METRIC_TASK_SUBMITTED)
        tracker.track(METRIC_TASK_SUBMITTED)
        tracker.track(METRIC_TASK_COMPLETED)
        summary = tracker.summary()
        assert summary[METRIC_TASK_SUBMITTED] == 2
        assert summary[METRIC_TASK_COMPLETED] == 1

    def test_summary_empty_tracker(self):
        tracker = EventTracker()
        assert tracker.summary() == {}

    def test_summary_includes_all_event_types(self):
        tracker = EventTracker()
        for metric in (
            METRIC_TASK_SUBMITTED,
            METRIC_TASK_COMPLETED,
            METRIC_BID_PLACED,
            METRIC_BUDGET_DEPLETED,
            METRIC_CIRCUIT_BREAKER_TRIPPED,
        ):
            tracker.track(metric)
        summary = tracker.summary()
        assert len(summary) == 5
        assert all(v == 1 for v in summary.values())

    def test_summary_returns_dict(self):
        tracker = EventTracker()
        tracker.track(METRIC_BID_PLACED)
        assert isinstance(tracker.summary(), dict)

    def test_summary_does_not_mutate_tracker(self):
        tracker = EventTracker()
        tracker.track(METRIC_TASK_SUBMITTED)
        tracker.summary()
        tracker.summary()
        assert len(tracker.get_events()) == 1


# ---------------------------------------------------------------------------
# HealthCheck
# ---------------------------------------------------------------------------


class TestHealthCheckRunAll:
    def test_single_passing_check(self):
        hc = HealthCheck()
        hc.register_check("ok", lambda: True)
        results = hc.run_all()
        assert results["ok"]["healthy"] is True
        assert results["ok"]["latency_ms"] >= 0.0

    def test_single_failing_check(self):
        hc = HealthCheck()
        hc.register_check("bad", lambda: False)
        results = hc.run_all()
        assert results["bad"]["healthy"] is False

    def test_multiple_checks(self):
        hc = HealthCheck()
        hc.register_check("a", lambda: True)
        hc.register_check("b", lambda: True)
        hc.register_check("c", lambda: False)
        results = hc.run_all()
        assert results["a"]["healthy"] is True
        assert results["b"]["healthy"] is True
        assert results["c"]["healthy"] is False

    def test_latency_ms_is_float(self):
        hc = HealthCheck()
        hc.register_check("timed", lambda: True)
        results = hc.run_all()
        assert isinstance(results["timed"]["latency_ms"], float)

    def test_exception_in_check_is_captured(self):
        hc = HealthCheck()

        def broken() -> bool:
            raise RuntimeError("connection refused")

        hc.register_check("broken", broken)
        results = hc.run_all()
        assert results["broken"]["healthy"] is False
        assert "connection refused" in results["broken"]["error"]

    def test_no_checks_returns_empty_dict(self):
        hc = HealthCheck()
        assert hc.run_all() == {}

    def test_overwrite_check_with_same_name(self):
        hc = HealthCheck()
        hc.register_check("svc", lambda: False)
        hc.register_check("svc", lambda: True)
        results = hc.run_all()
        assert results["svc"]["healthy"] is True

    def test_check_timeout_marks_result_unhealthy(self):
        hc = HealthCheck(check_timeout_seconds=0.01)
        hc.register_check("slow", lambda: (time.sleep(0.05), True)[1])
        results = hc.run_all()
        assert results["slow"]["healthy"] is False
        assert results["slow"]["timed_out"] is True


class TestHealthCheckIsHealthy:
    def test_all_passing_is_healthy(self):
        hc = HealthCheck()
        hc.register_check("x", lambda: True)
        hc.register_check("y", lambda: True)
        assert hc.is_healthy() is True

    def test_one_failing_is_not_healthy(self):
        hc = HealthCheck()
        hc.register_check("x", lambda: True)
        hc.register_check("y", lambda: False)
        assert hc.is_healthy() is False

    def test_no_checks_is_healthy(self):
        hc = HealthCheck()
        assert hc.is_healthy() is True

    def test_exception_makes_unhealthy(self):
        hc = HealthCheck()
        hc.register_check("bad", lambda: 1 / 0)
        assert hc.is_healthy() is False
