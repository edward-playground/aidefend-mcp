"""Small, self-contained framework migration fixtures for MCP contract tests."""

from __future__ import annotations


ACTIVE_NAMES = {
    1: "Prompt Injection",
    2: "Sensitive Information Disclosure",
    3: "Excessive Agency",
    4: "Supply Chain",
    5: "Data and Model Poisoning",
    6: "Unbounded Consumption",
    7: "Misinformation",
    8: "Hidden Context Exposure",
    9: "Vector and Embedding Weaknesses",
    10: "Improper Output Handling",
}

LEGACY_NAMES = {
    1: "Prompt Injection",
    2: "Sensitive Information Disclosure",
    3: "Supply Chain",
    4: "Data and Model Poisoning",
    5: "Improper Output Handling",
    6: "Excessive Agency",
    7: "System Prompt Leakage",
    8: "Vector and Embedding Weaknesses",
    9: "Misinformation",
    10: "Unbounded Consumption",
}

LEGACY_TO_CURRENT_RANK = {
    1: 1,
    2: 2,
    3: 4,
    4: 5,
    5: 10,
    6: 3,
    7: 8,
    8: 9,
    9: 7,
    10: 6,
}


def owasp_llm_2026_registry() -> dict:
    active_items = [
        {
            "id": f"LLM{rank:02d}:2026",
            "rank": rank,
            "name": ACTIVE_NAMES[rank],
            "description": f"Current risk definition for {ACTIVE_NAMES[rank]}.",
        }
        for rank in range(1, 11)
    ]
    migrations = []
    for legacy_rank in range(1, 11):
        current_rank = LEGACY_TO_CURRENT_RANK[legacy_rank]
        migrations.append(
            {
                "from": {
                    "edition": "2025",
                    "id": f"LLM{legacy_rank:02d}:2025",
                    "name": LEGACY_NAMES[legacy_rank],
                },
                "to": {
                    "edition": "2026",
                    "id": f"LLM{current_rank:02d}:2026",
                    "name": ACTIVE_NAMES[current_rank],
                },
                "relation": "semantic-successor",
                "changeTypes": ["reviewed"],
                "note": (
                    f"LLM{legacy_rank:02d}:2025 resolves by concept to "
                    f"LLM{current_rank:02d}:2026."
                ),
                "mappingCarryForward": "requires-semantic-review",
            }
        )

    return {
        "schemaVersion": "1.0",
        "registryVersion": "2026-08-05",
        "contract": "AIDEFEND framework edition and semantic migration registry",
        "frameworks": {
            "owasp_llm": {
                "stableKey": "owasp_llm",
                "activeEdition": "2026",
                "activeLabel": "OWASP LLM Top 10 2026",
                "officialTitle": "OWASP Top 10 for LLM Applications 2026",
                "sourceUrl": "https://genai.owasp.org/resource/owasp-genai-llm-top-10-2026/",
                "sourceArtifact": {
                    "release": "v1.0",
                    "downloadUrl": "https://genai.owasp.org/download/56791/",
                    "fileName": "OWASP-GenAI-LLM-Top-10-2026-v1.0.pdf",
                    "mediaType": "application/pdf",
                    "bytes": 2402520,
                    "pageCount": 122,
                    "sha256": "EF87993A4E50AE9D83B41FF7A3D3E6320A82DFA8D4EC6BF98D0CE264B2E6108E",
                    "publicationDate": None,
                    "publicationDateStatus": "not set in the v1.0 PDF",
                },
                "sourceLicense": {
                    "spdxExpression": "CC-BY-SA-4.0",
                    "licenseUrl": "https://creativecommons.org/licenses/by-sa/4.0/legalcode",
                    "attribution": "OWASP Top 10 for LLM Applications 2026",
                    "scope": "OWASP-derived identifiers and risk summaries",
                    "changesMade": "Risk summaries are paraphrased and mappings are independently authored.",
                },
                "editions": {
                    "2025": {
                        "label": "OWASP LLM Top 10 2025",
                        "status": "superseded",
                        "successorEdition": "2026",
                    },
                    "2026": {
                        "label": "OWASP LLM Top 10 2026",
                        "status": "current",
                        "artifactRelease": "v1.0",
                    },
                },
                "resolutionPolicy": {
                    "omittedEdition": "resolve current",
                    "latestEdition": "resolve current",
                    "explicitCurrentId": "return current",
                    "explicitSupersededId": "resolve declared semantic successor",
                    "legacyName": "resolve named concept",
                    "bareId": "treat rank as current",
                    "nonPaddedRank": "normalize rank",
                    "editionContext": "honor explicit context",
                    "malformedOrUnsupportedEdition": "return invalid",
                    "multipleConcepts": "return ambiguity",
                    "unversionedIdNameConflict": "resolve by name",
                    "versionedIdNameConflict": "resolve by name",
                    "mappingCarryForward": "requires semantic review",
                },
                "responseContract": {
                    "canonicalEdition": "2026",
                    "canonicalIdFormat": "LLMdd:2026",
                    "metadataField": "resolution",
                    "metadataValues": [
                        "canonical",
                        "migrated",
                        "normalized",
                        "fallback_latest",
                        "ambiguous",
                        "invalid",
                    ],
                },
                "activeItems": active_items,
                "migrations": migrations,
            }
        },
    }
