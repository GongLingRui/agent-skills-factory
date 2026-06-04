"""Defaults for plan §12 / docs/31 stay aligned with Settings."""

from agent_factory.config.settings import Settings


def test_doc_parse_async_threshold_default():
    """DOC_PARSE_ASYNC_MIN_BYTES matches docs/31 (10 MiB)."""
    field = Settings.model_fields["DOC_PARSE_ASYNC_MIN_BYTES"]
    assert field.default == 10 * 1024 * 1024


def test_session_chat_lock_defaults():
    w = Settings.model_fields["SESSION_CHAT_LOCK_MAX_WAITERS"]
    ms = Settings.model_fields["SESSION_CHAT_LOCK_WAIT_MS"]
    assert w.default == 8
    assert ms.default == 45000


def test_degradation_auto_defaults_align_prd():
    """plan §13.1 / prd §9.5 error-rate and latency escalate thresholds."""
    er = Settings.model_fields["DEGRADATION_AUTO_ESCALATE_ERROR_RATE"]
    lat = Settings.model_fields["DEGRADATION_AUTO_LATENCY_ESCALATE_MS"]
    rec = Settings.model_fields["DEGRADATION_AUTO_RECOVER_MAX_ERROR_RATE"]
    assert er.default == 0.05
    assert lat.default == 30_000.0
    assert rec.default == 0.01


def test_mau_retention_gate_defaults():
    """MAU gate off by default; window and archive knobs (plan §13.1)."""
    en = Settings.model_fields["MAU_RETENTION_GATE_ENABLED"]
    win = Settings.model_fields["MAU_RETENTION_WINDOW_DAYS"]
    th = Settings.model_fields["MAU_RETENTION_DEFAULT_THRESHOLD"]
    cold = Settings.model_fields["MAU_COLD_ARCHIVE_AFTER_DAYS"]
    assert en.default is False
    assert win.default == 30
    assert th.default == 5
    assert cold.default == 90
