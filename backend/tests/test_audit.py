"""Tests for the M5 audit trail."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

from app.audit.models import AuditEventType
from app.audit.service import AuditService


# ----------------------------------------------------------------------
# 17-21: Event creation for each stage, duplicate auditable, version recorded
# ----------------------------------------------------------------------
def test_policy_evaluation_creates_audit_event():
    audit = AuditService()
    event = audit.record(
        AuditEventType.POLICY_EVALUATED, cluster_id="cc-test", decision_id="dec-1",
        new_state="HOLD_FOR_REVIEW", policy_version="v1",
    )
    assert event.event_type == AuditEventType.POLICY_EVALUATED
    assert event in audit.get_for_cluster("cc-test")


def test_action_execution_creates_audit_event():
    audit = AuditService()
    event = audit.record(
        AuditEventType.ACTION_EXECUTED, cluster_id="cc-test", action_id="act-1", new_state="SIMULATED",
    )
    assert event.event_type == AuditEventType.ACTION_EXECUTED
    assert event.action_id == "act-1"


def test_action_rejection_creates_audit_event():
    audit = AuditService()
    event = audit.record(AuditEventType.ACTION_REJECTED, cluster_id="cc-test", new_state="REJECTED")
    assert event.event_type == AuditEventType.ACTION_REJECTED


def test_duplicate_action_is_auditable():
    audit = AuditService()
    event = audit.record(
        AuditEventType.ACTION_DUPLICATE, cluster_id="cc-test", action_id="act-2", new_state="DUPLICATE",
    )
    assert event.event_type == AuditEventType.ACTION_DUPLICATE
    found = audit.get_by_id(event.audit_id)
    assert found is not None
    assert found.action_id == "act-2"


def test_policy_version_is_recorded_in_audit():
    audit = AuditService()
    event = audit.record(
        AuditEventType.DECISION_CREATED, cluster_id="cc-test", decision_id="dec-1", policy_version="v1",
    )
    assert event.policy_version == "v1"


# ----------------------------------------------------------------------
# 22: No secrets in audit records
# ----------------------------------------------------------------------
def test_audit_event_schema_has_no_secret_shaped_fields():
    """Structural guarantee: AuditEvent has no field that could hold an
    API key, password, or raw credential -- verified via the schema
    itself, not by hoping nobody passes one in."""
    fields = set(__import__("app.audit.models", fromlist=["AuditEvent"]).AuditEvent.model_fields.keys())
    for forbidden in ("api_key", "password", "secret", "token", "credential", "authorization"):
        assert forbidden not in fields


def test_audit_never_stores_full_evidence_or_pii():
    """previous_state/new_state are short enum-shaped strings -- audit
    records a DECISION value like "ESCALATE", never a dump of the full
    evidence/summary text."""
    audit = AuditService()
    event = audit.record(
        AuditEventType.POLICY_EVALUATED, cluster_id="cc-test", decision_id="dec-1",
        new_state="ESCALATE", policy_version="v1",
    )
    assert len(event.new_state) < 50  # a decision value, not a prose dump
    assert "@" not in (event.new_state or "")  # no email-shaped content


# ----------------------------------------------------------------------
# Retrieval / isolation
# ----------------------------------------------------------------------
def test_get_for_cluster_only_returns_matching_events():
    audit = AuditService()
    audit.record(AuditEventType.POLICY_EVALUATED, cluster_id="cc-a", new_state="MONITOR")
    audit.record(AuditEventType.POLICY_EVALUATED, cluster_id="cc-b", new_state="ESCALATE")
    events_a = audit.get_for_cluster("cc-a")
    assert len(events_a) == 1
    assert events_a[0].cluster_id == "cc-a"


def test_clear_removes_all_events():
    audit = AuditService()
    audit.record(AuditEventType.POLICY_EVALUATED, cluster_id="cc-test", new_state="MONITOR")
    audit.clear()
    assert audit.get_for_cluster("cc-test") == []


def test_get_by_id_returns_none_for_unknown_id():
    audit = AuditService()
    assert audit.get_by_id("nonexistent") is None
