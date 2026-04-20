from __future__ import annotations

from db.demo_bootstrap import (
    BOOTSTRAP_MODE_RESET_IF_CHANGED,
    DEFAULT_BOOTSTRAP_MODE,
    determine_bootstrap_decision,
)


def test_disabled_mode_never_resets():
    decision = determine_bootstrap_decision(DEFAULT_BOOTSTRAP_MODE, "abc", None)

    assert decision.should_reset is False
    assert decision.reason == "bootstrap_disabled"
    assert decision.schema_signature == "abc"
    assert decision.previous_signature is None


def test_untracked_database_resets():
    decision = determine_bootstrap_decision(BOOTSTRAP_MODE_RESET_IF_CHANGED, "abc", None)

    assert decision.should_reset is True
    assert decision.reason == "bootstrap_untracked_database"


def test_matching_schema_skips_reset():
    decision = determine_bootstrap_decision(BOOTSTRAP_MODE_RESET_IF_CHANGED, "abc", "abc")

    assert decision.should_reset is False
    assert decision.reason == "bootstrap_schema_unchanged"


def test_changed_schema_resets():
    decision = determine_bootstrap_decision(BOOTSTRAP_MODE_RESET_IF_CHANGED, "new", "old")

    assert decision.should_reset is True
    assert decision.reason == "bootstrap_schema_changed"
