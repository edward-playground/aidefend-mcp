"""Regression tests for the query-validation fix (P1 false-positive blacklist removal).

Background: validate_query_text() previously rejected any query containing security terms
like eval/exec/${...}/{{...}}/../ or HTML fragments. Because the query text is only embedded
for vector search (never executed, and never interpolated into a LanceDB where() filter,
shell, template, file path, or SQL), that blacklist blocked exactly the queries this
AI-security knowledge base exists to answer while providing no real injection protection.

These tests lock in the corrected behavior:
  * legitimate security queries are ACCEPTED by validate_query_text and QueryRequest,
  * structural validation (empty / too-long / control chars) is still enforced,
  * output safety is provided by escape_markdown() (render-time encoding),
  * the technique-ID whitelist (the one input that DOES reach a DB filter) still rejects
    injection.
"""

import pytest

from app.security import (
    validate_query_text,
    validate_chunked_query,
    sanitize_technique_id,
    InputValidationError,
)
from app.utils import escape_markdown

# The exact cases reported by the audit — all must now be accepted.
REPORTED_QUERIES = [
    "how to prevent eval() code injection in LLM plugins",
    "defend against exec() calls in AI agents",
    "mitigate template injection like {{7*7}} in prompts",
    "protect against path traversal ../../etc/passwd in RAG file access",
    "prevent ${jndi:ldap} log4shell style injection",
    "how do I stop __import__ abuse in sandboxed code execution",
]


class TestLegitimateSecurityQueriesAccepted:
    @pytest.mark.parametrize("query", REPORTED_QUERIES)
    def test_validate_query_text_accepts(self, query):
        result = validate_query_text(query)
        assert isinstance(result, str)
        assert result  # non-empty

    @pytest.mark.parametrize("query", REPORTED_QUERIES)
    def test_query_request_accepts(self, query):
        from app.schemas import QueryRequest
        req = QueryRequest(query_text=query, top_k=5)
        assert req.query_text  # passed the field validator without raising

    @pytest.mark.parametrize("query", REPORTED_QUERIES)
    def test_no_longer_flagged_malicious(self, query):
        # The old code raised "Query contains potentially malicious content".
        try:
            validate_query_text(query)
        except InputValidationError as exc:  # pragma: no cover - should not happen
            assert "malicious" not in str(exc).lower()


class TestStructuralValidationStillEnforced:
    def test_empty_rejected(self):
        with pytest.raises(InputValidationError):
            validate_query_text("")
        with pytest.raises(InputValidationError):
            validate_query_text("   ")

    def test_too_long_rejected(self):
        with pytest.raises(InputValidationError):
            validate_query_text("a" * 100000)

    def test_control_characters_rejected(self):
        with pytest.raises(InputValidationError):
            validate_query_text("legit query\x00with NUL")
        with pytest.raises(InputValidationError):
            validate_query_text("bell\x07char")

    def test_tab_and_newline_allowed_and_normalized(self):
        # Tab/newline are whitespace and must be collapsed, not rejected.
        result = validate_query_text("prompt\tinjection\n defenses")
        assert result == "prompt injection defenses"


class TestOutputEncoding:
    def test_html_is_neutralized(self):
        out = escape_markdown("<script>alert('x')</script>")
        assert "<script>" not in out
        assert "&lt;script&gt;" in out

    def test_ampersand_encoded_first(self):
        assert escape_markdown("a & <b>") == "a &amp; &lt;b&gt;"

    def test_backtick_escaped(self):
        assert escape_markdown("run `rm -rf`") == "run \\`rm -rf\\`"

    def test_readable_security_terms_preserved(self):
        # The whole point of the fix: these display verbatim (no over-escaping).
        assert escape_markdown("eval() and ${jndi} and ../etc") == "eval() and ${jndi} and ../etc"

    def test_non_string_is_safe(self):
        assert escape_markdown(None) == ""
        assert escape_markdown(123) == "123"


class TestTechniqueIdWhitelistStillProtects:
    """The technique ID DOES reach a LanceDB where() filter, so its whitelist must remain."""

    @pytest.mark.parametrize("bad_id", [
        "AID-H-001'; DROP TABLE",
        "AID-H-001<script>",
        "AID-H-001' OR '1'='1",
        "../../etc/passwd",
    ])
    def test_injection_ids_rejected(self, bad_id):
        with pytest.raises(Exception):
            sanitize_technique_id(bad_id)
