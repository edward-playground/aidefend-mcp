import asyncio
import json
from unittest.mock import AsyncMock

from app.core import (
    QueryEngine,
    decode_framework_record,
    framework_public_metadata,
)
from app.tools.comprehensive_search import compute_coverage_summary
from app.tools.implementation_plan import (
    _calculate_recommendation_score,
    _generate_reasoning,
)
from app.tools.technique_comparison import _extract_technique_info
from app.tools.technique_detail import _format_strategies
from app.sync import _build_threat_mappings
from app.framework_utils import resolve_control_ids


def _raw_record(**overrides):
    record = {
        "source_id": "AID-H-002.002-G001",
        "type": "strategy",
        "name": "Constrain retrieval - validate sources",
        "tactic": "Harden",
        "text": "Validate retrieved sources.",
        "pillar": json.dumps(["app", "data"]),
        "phase": json.dumps(["building", "validation"]),
        "defends_against": json.dumps([
            {"framework": "MITRE ATLAS", "items": ["AML.T0051"]}
        ]),
        "tools_opensource": "[]",
        "tools_source_available": json.dumps(["Open-weight scanner (source available)"]),
        "tools_commercial": json.dumps(["Commercial scanner"]),
        "parent_technique_id": "AID-H-002.002",
        "implementation_guidance": json.dumps([
            {
                "id": "AID-H-002.002-G001",
                "implementation": "Validate sources",
                "howTo": "<pre><code>validate(source)</code></pre>",
            }
        ]),
        "guidance_id": "AID-H-002.002-G001",
        "scope_boundary": json.dumps({
            "responsibility": "Retrieval-time source validation"
        }),
        "is_actionable": False,
        "is_parent_family": False,
        "has_code_snippets": True,
        "warnings": json.dumps([{"type": "operational", "message": "Tune thresholds"}]),
    }
    record.update(overrides)
    return record


def test_decoder_exposes_new_schema_types_and_canonical_guidance_id():
    decoded = decode_framework_record(_raw_record())

    assert decoded["pillar"] == ["app", "data"]
    assert decoded["phase"] == ["building", "validation"]
    assert decoded["tools_source_available"] == [
        "Open-weight scanner (source available)"
    ]
    assert decoded["scope_boundary"]["responsibility"].startswith("Retrieval")
    assert decoded["guidance_id"] == "AID-H-002.002-G001"
    assert decoded["is_actionable"] is False
    assert decoded["is_parent_family"] is False

    public = framework_public_metadata(decoded)
    assert public["pillar"] == ["app", "data"]
    assert public["phase"] == ["building", "validation"]
    assert public["guidance_id"] == "AID-H-002.002-G001"


def test_decoder_accepts_future_tactic_codes_without_weakening_id_shape():
    future_guidance_id = "AID-GOVERNANCE-001.001-G001"
    decoded = decode_framework_record(_raw_record(
        source_id=future_guidance_id,
        guidance_id=future_guidance_id,
    ))
    assert decoded["source_id"] == future_guidance_id
    assert decoded["guidance_id"] == future_guidance_id

    inferred = decode_framework_record(_raw_record(
        source_id=future_guidance_id,
        guidance_id="",
    ))
    assert inferred["guidance_id"] == future_guidance_id

    malformed = decode_framework_record(_raw_record(
        source_id="AID-1GV-001.001-G001",
        guidance_id="AID-GOVERNANCE-001.001-G001' OR '1'='1",
    ))
    assert malformed["guidance_id"] == ""


def test_decoder_supports_legacy_scalar_dimensions_and_parent_inference():
    decoded = decode_framework_record({
        "source_id": "AID-M-001",
        "type": "technique",
        "pillar": "",
        "phase": "",
        "implementation_guidance": "[]",
    })
    assert decoded["is_parent_family"] is True
    assert decoded["is_actionable"] is False

    legacy = decode_framework_record({"pillar": "model", "phase": "building"})
    assert legacy["pillar"] == ["model"]
    assert legacy["phase"] == ["building"]

    encoded_scalars = decode_framework_record({
        "pillar": json.dumps(""),
        "phase": json.dumps("validation"),
    })
    assert encoded_scalars["pillar"] == []
    assert encoded_scalars["phase"] == ["validation"]


def test_control_id_resolution_expands_families_and_reports_shifted_ids():
    records = [
        {
            "source_id": "AID-H-001",
            "type": "technique",
            "is_actionable": False,
            "parent_technique_id": "",
        },
        {
            "source_id": "AID-H-001.002",
            "type": "subtechnique",
            "is_actionable": True,
            "parent_technique_id": "AID-H-001",
        },
        {
            "source_id": "AID-H-001.001",
            "type": "subtechnique",
            "is_actionable": True,
            "parent_technique_id": "AID-H-001",
        },
        {
            "source_id": "AID-D-001",
            "type": "technique",
            "is_actionable": True,
            "parent_technique_id": "",
        },
    ]

    resolved = resolve_control_ids(
        [" aid-h-001 ", "AID-D-001", "AID-D-001", "AID-H-OLD"],
        records,
    )

    assert resolved["normalized_ids"] == [
        "AID-H-001",
        "AID-D-001",
        "AID-H-OLD",
    ]
    assert resolved["valid_input_ids"] == ["AID-H-001", "AID-D-001"]
    assert resolved["actionable_ids"] == [
        "AID-H-001.001",
        "AID-H-001.002",
        "AID-D-001",
    ]
    assert resolved["expanded_parent_families"] == {
        "AID-H-001": ["AID-H-001.001", "AID-H-001.002"]
    }
    assert resolved["unrecognized_ids"] == ["AID-H-OLD"]


def test_comprehensive_coverage_counts_each_array_member():
    summary = compute_coverage_summary([
        {
            "type": "subtechnique",
            "tactic": "Harden",
            "pillar": ["app", "data"],
            "phase": ["building", "validation"],
        },
        {
            "type": "technique",
            "tactic": "Detect",
            "pillar": "app",
            "phase": "operation",
        },
    ])

    assert summary["by_pillar"] == {"app": 2, "data": 1}
    assert summary["by_phase"] == {
        "building": 1,
        "validation": 1,
        "operation": 1,
    }


def test_detail_and_comparison_preserve_guidance_and_new_metadata():
    raw = _raw_record(type="subtechnique", is_actionable=True)
    comparison = _extract_technique_info(raw)
    assert comparison["pillar"] == ["app", "data"]
    assert comparison["phase"] == ["building", "validation"]
    assert comparison["tools_source_available"]
    assert comparison["scope_boundary"]
    assert comparison["guidance_ids"] == ["AID-H-002.002-G001"]

    strategies = _format_strategies(
        decode_framework_record(raw)["implementation_guidance"]
    )
    assert strategies[0]["guidance_id"] == "AID-H-002.002-G001"


def test_implementation_plan_distinguishes_source_available_from_open_source():
    raw = _raw_record(
        source_id="AID-M-001.006",
        type="subtechnique",
        is_actionable=True,
        tools_commercial="[]",
        defends_against="[]",
        pillar=json.dumps([]),
        phase=json.dumps([]),
    )
    score, breakdown = _calculate_recommendation_score(raw)

    assert score == 1.0
    assert breakdown["ease_of_implementation"] == 1.0
    assert "source-available or open-weight" in _generate_reasoning(
        raw, breakdown
    )


def test_health_check_is_side_effect_free_when_uninitialized():
    engine = QueryEngine()
    engine.initialize = AsyncMock(side_effect=AssertionError("must not initialize"))

    assert asyncio.run(engine.health_check()) is False
    engine.initialize.assert_not_awaited()


def test_locked_reset_drops_db_handles_but_keeps_embedding_model():
    engine = QueryEngine()
    model = object()
    engine._initialized = True
    engine._db = object()
    engine._table = object()
    engine._id_cache = [{"source_id": "AID-H-001"}]
    engine._model = model

    engine._reset_database_handles_locked()

    assert engine.is_ready is False
    assert engine._db is None
    assert engine._table is None
    assert engine._id_cache is None
    assert engine._model is model


def test_threat_reverse_index_has_no_case_insensitive_duplicate_json_keys():
    records = [
        {
            "source_id": "AID-H-001",
            "type": "technique",
            "is_actionable": True,
            "defends_against": json.dumps(
                [
                    {
                        "framework": "MAESTRO",
                        "items": [
                            "Governance 4.1: Lack of traceability and transparency of model assets"
                        ],
                    }
                ]
            ),
        },
        {
            "source_id": "AID-D-001",
            "type": "technique",
            "is_actionable": True,
            "defends_against": json.dumps(
                [
                    {
                        "framework": "MAESTRO",
                        "items": [
                            "GOVERNANCE 4.1: LACK OF TRACEABILITY AND TRANSPARENCY OF MODEL ASSETS"
                        ],
                    }
                ]
            ),
        },
    ]

    mappings = _build_threat_mappings(records)
    folded_keys = [key.casefold() for key in mappings]

    assert len(folded_keys) == len(set(folded_keys))
    assert sorted(next(iter(mappings.values()))) == ["AID-D-001", "AID-H-001"]


def test_statistics_fast_and_fallback_contracts_match(monkeypatch):
    from app import utils
    from app.core import query_engine
    from app.sync import _calculate_statistics_from_records
    from app.tools.statistics import get_statistics

    base = {
        "text": "control",
        "name": "Control",
        "tactic": "Harden",
        "pillar": json.dumps(["app"]),
        "phase": json.dumps(["building"]),
        "defends_against": json.dumps([
            {"framework": "OWASP LLM Top 10 2025", "items": ["LLM01:2025"]}
        ]),
        "tools_opensource": "[]",
        "tools_source_available": json.dumps(["Open-weight tool"]),
        "tools_commercial": "[]",
        "implementation_guidance": "[]",
        "guidance_id": "",
        "scope_boundary": "{}",
        "has_code_snippets": False,
        "warnings": "[]",
    }
    records = [
        {
            **base,
            "source_id": "AID-H-001",
            "type": "technique",
            "parent_technique_id": "",
            "pillar": "[]",
            "phase": "[]",
            "is_actionable": False,
            "is_parent_family": True,
        },
        {
            **base,
            "source_id": "AID-H-001.001",
            "type": "subtechnique",
            "parent_technique_id": "AID-H-001",
            "scope_boundary": json.dumps({"responsibility": "child scope"}),
            "is_actionable": True,
            "is_parent_family": False,
        },
        {
            **base,
            "source_id": "AID-H-002",
            "type": "technique",
            "parent_technique_id": "",
            "is_actionable": True,
            "is_parent_family": False,
        },
        {
            **base,
            "source_id": "AID-H-002-G001",
            "type": "strategy",
            "parent_technique_id": "AID-H-002",
            "guidance_id": "AID-H-002-G001",
            "has_code_snippets": True,
            "is_actionable": False,
            "is_parent_family": False,
        },
    ]

    fast = _calculate_statistics_from_records(records)
    monkeypatch.setattr(utils, "load_version_info", lambda: None)
    monkeypatch.setattr(query_engine, "_initialized", True)
    monkeypatch.setattr(query_engine, "_table", object())
    monkeypatch.setattr(
        query_engine,
        "read_table_snapshot",
        AsyncMock(return_value=(records, None)),
    )
    fallback = asyncio.run(get_statistics())

    for key in (
        "by_tactic",
        "actionable_by_tactic",
        "by_pillar",
        "by_phase",
        "threat_framework_coverage",
        "tools_availability",
        "implementation_resources",
    ):
        assert fallback[key] == fast[key]

    for key in (
        "total_documents",
        "total_techniques",
        "total_subtechniques",
        "total_strategies",
        "total_parent_families",
        "total_standalone_techniques",
        "total_actionable_items",
        "database_path",
    ):
        assert fallback["overview"][key] == fast["overview"][key]
