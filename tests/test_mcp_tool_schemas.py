"""Every MCP tool input schema must reject unknown arguments at the protocol layer.

LLM clients occasionally invent argument names. Without ``additionalProperties: false``
the MCP SDK forwards the unknown key and handlers that splat ``**arguments`` leak a raw
Python ``TypeError`` instead of a schema validation message.
"""

import ast
from pathlib import Path
from typing import Dict, List

import pytest
from mcp.server import Server
from mcp.types import CallToolRequest, CallToolRequestParams, Tool

import mcp_server

_SERVER_SOURCE = Path(mcp_server.__file__).resolve()
_EXPECTED_TOOL_COUNT = 18

# A minimal valid payload per tool so the only schema violation is the unknown key.
_VALID_ARGUMENTS: Dict[str, dict] = {
    "query_aidefend": {"query": "prompt injection"},
    "get_aidefend_status": {},
    "sync_aidefend": {},
    "get_statistics": {},
    "validate_technique_id": {"technique_id": "AID-H-001"},
    "get_technique_detail": {"technique_id": "AID-H-001"},
    "get_defenses_for_threat": {"threat_id": "LLM01"},
    "get_secure_code_snippet": {"technique_id": "AID-H-001"},
    "analyze_coverage": {"implemented_techniques": ["AID-H-001"]},
    "map_to_compliance_framework": {"technique_ids": ["AID-H-001"]},
    "get_quick_reference": {"topic": "prompt injection"},
    "get_threat_coverage": {"implemented_techniques": ["AID-H-001"]},
    "get_implementation_plan": {"implemented_techniques": ["AID-H-001"]},
    "classify_threat": {"text": "prompt injection"},
    "comprehensive_search": {"topic": "prompt injection"},
    "analyze_security_posture": {"implemented_techniques": ["AID-H-001"]},
    "compare_techniques": {"technique_ids": ["AID-H-001", "AID-H-002"]},
    "generate_incident_playbook": {"incident_description": "prompt injection"},
}


def _declared_tools() -> List[Tool]:
    """Extract the static Tool(...) declarations without starting the stdio server."""
    tree = ast.parse(_SERVER_SOURCE.read_text(encoding="utf-8"))
    tools: List[Tool] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Tool"):
            continue
        keywords = {keyword.arg: keyword.value for keyword in node.keywords}
        tools.append(
            Tool(
                name=ast.literal_eval(keywords["name"]),
                description=ast.literal_eval(keywords["description"]),
                inputSchema=ast.literal_eval(keywords["inputSchema"]),
            )
        )
    return tools


def test_every_declared_tool_forbids_additional_properties():
    tools = _declared_tools()
    names = sorted(tool.name for tool in tools)

    assert len(tools) == _EXPECTED_TOOL_COUNT
    assert names == sorted(_VALID_ARGUMENTS)
    for tool in tools:
        assert tool.inputSchema.get("type") == "object", tool.name
        assert tool.inputSchema.get("additionalProperties") is False, tool.name
        declared = set(tool.inputSchema.get("properties", {}))
        assert set(_VALID_ARGUMENTS[tool.name]) <= declared, tool.name


@pytest.mark.asyncio
async def test_registered_dispatcher_rejects_unknown_arguments_with_schema_error(
    monkeypatch,
):
    tools = _declared_tools()
    server = Server("aidefend-mcp-schema-test")

    @server.list_tools()
    async def list_tools() -> List[Tool]:
        return tools

    mcp_server._register_call_tool_handler(server)

    async def unexpected_dispatch(name, arguments):  # pragma: no cover - guard
        raise AssertionError(f"{name} reached the handler with {arguments}")

    monkeypatch.setattr(mcp_server, "_dispatch_tool_call", unexpected_dispatch)

    for tool in tools:
        request = CallToolRequest(
            params=CallToolRequestParams(
                name=tool.name,
                arguments={**_VALID_ARGUMENTS[tool.name], "bogus_param": "x"},
            )
        )
        response = await server.request_handlers[CallToolRequest](request)

        assert response.root.isError is True, tool.name
        text = response.root.content[0].text
        assert text.startswith("Input validation error"), (tool.name, text)
        assert "bogus_param" in text, (tool.name, text)
        assert "unexpected keyword argument" not in text, (tool.name, text)
