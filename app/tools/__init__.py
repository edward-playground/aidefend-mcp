"""
AIDEFEND MCP Service - Tools Module

This package contains implementation of all P0 tools for AIDEFEND MCP Service.

Each tool module provides:
- Core business logic for the tool
- Input validation and sanitization
- Error handling
- Audit logging integration
"""

from app.tools.statistics import get_statistics
from app.tools.validation import validate_technique_id
from app.tools.technique_detail import get_technique_detail
from app.tools.defenses_for_threat import get_defenses_for_threat
from app.tools.code_snippets import get_secure_code_snippet
from app.tools.coverage_analysis import analyze_coverage
from app.tools.compliance_mapping import map_to_compliance_framework
from app.tools.quick_reference import get_quick_reference

__all__ = [
    "get_statistics",
    "validate_technique_id",
    "get_technique_detail",
    "get_defenses_for_threat",
    "get_secure_code_snippet",
    "analyze_coverage",
    "map_to_compliance_framework",
    "get_quick_reference",
]
