"""Regression tests for semantic-search relevance conversion."""

import pytest

import app.core as core_module
import app.tools.defenses_for_threat as defenses_module


class FakeVector(list):
    def tolist(self):
        return list(self)


class FakeEmbedding:
    def __init__(self, *, model_name):
        self.model_name = model_name

    def embed(self, texts):
        assert texts
        return iter([FakeVector([0.1, 0.2])])


class FakeQueryEngine:
    is_ready = True
    active_embedding_model = "test-embedding"

    def __init__(self, records):
        self.records = records

    async def read_table(self, operation):
        return [dict(record) for record in self.records]


@pytest.fixture
def semantic_search_records(monkeypatch):
    records = [
        {
            "source_id": "AID-H-001",
            "name": "Closest defense",
            "type": "technique",
            "tactic": "Harden",
            "text": "Closest semantic match",
            "pillar": '["app"]',
            "phase": '["validation"]',
            "is_actionable": True,
            "is_parent_family": False,
            "_distance": 0.0,
        },
        {
            "source_id": "AID-D-001",
            "name": "Middle defense",
            "type": "technique",
            "tactic": "Detect",
            "text": "Moderate semantic match",
            "pillar": '["app"]',
            "phase": '["operation"]',
            "is_actionable": True,
            "is_parent_family": False,
            "_distance": 1.0,
        },
        {
            "source_id": "AID-I-001",
            "name": "Distant defense",
            "type": "technique",
            "tactic": "Isolate",
            "text": "Distant semantic match",
            "pillar": '["infra"]',
            "phase": '["response"]',
            "is_actionable": True,
            "is_parent_family": False,
            "_distance": 3.0,
        },
    ]
    monkeypatch.setattr(core_module, "query_engine", FakeQueryEngine(records))
    monkeypatch.setattr(defenses_module, "TextEmbedding", FakeEmbedding)
    return records


@pytest.mark.asyncio
async def test_semantic_search_returns_nonzero_relevance(semantic_search_records):
    result = await defenses_module.get_defenses_for_threat(
        threat_keyword="prompt injection",
        top_k=10,
    )

    assert result["total_results"] == len(semantic_search_records)
    assert [item["relevance_score"] for item in result["defense_techniques"]] == [
        1.0,
        0.5,
        0.25,
    ]
    assert all(
        0.0 < item["relevance_score"] <= 1.0
        for item in result["defense_techniques"]
    )


@pytest.mark.parametrize(
    ("distance", "expected_score"),
    [(0.0, 1.0), (1.0, 0.5), (3.0, 0.25), (9.0, 0.1)],
)
def test_relevance_score_calculation_logic(distance, expected_score):
    assert 1.0 / (1.0 + distance) == pytest.approx(expected_score)


@pytest.mark.asyncio
async def test_results_sorted_by_relevance(semantic_search_records):
    result = await defenses_module.get_defenses_for_threat(
        threat_keyword="adversarial attacks",
        top_k=10,
    )

    scores = [item["relevance_score"] for item in result["defense_techniques"]]
    assert scores == sorted(scores, reverse=True)
