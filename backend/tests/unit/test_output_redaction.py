"""Assistant output redaction."""

from agent_factory.core.output_redaction import redact_sensitive_snippets


def test_redacts_openai_style_key():
    s = "here is sk-123456789012345678901234567890"
    out = redact_sensitive_snippets(s)
    assert "sk-" not in out
    assert "REDACTED" in out


def test_redacts_bearer():
    s = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0"
    out = redact_sensitive_snippets(s)
    assert "REDACTED" in out


def test_redacts_aws_access_key():
    s = "key AKIAIOSFODNN7EXAMPLE in text"
    out = redact_sensitive_snippets(s)
    assert "REDACTED_AWS_KEY" in out
    assert "AKIAIOSFODNN7EXAMPLE" not in out
