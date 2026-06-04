"""Model queue policy error attributes."""

from agent_factory.infra.model_queue import ModelQueuePolicyError


def test_model_queue_policy_error_fields():
    e = ModelQueuePolicyError("busy", http_status=429, retry_after=7)
    assert e.http_status == 429
    assert e.retry_after == 7
