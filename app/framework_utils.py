"""
Framework normalization helpers for AIDEFEND threat mappings.

These helpers convert framework-specific item strings into stable canonical IDs
so analytics can stay correct even when AIDEFEND adds annotations or expands
the number of referenced frameworks.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Optional, Set

FRAMEWORK_LABELS: Dict[str, str] = {
    "owasp_llm": "OWASP LLM Top 10 2025",
    "owasp_ml": "OWASP ML Top 10 2023",
    "owasp_agentic": "OWASP Agentic AI Top 10 2026",
    "atlas": "MITRE ATLAS",
    "maestro": "MAESTRO",
    "nist_aml": "NIST Adversarial Machine Learning 2025",
    "cisco": "Cisco Integrated AI Security and Safety Framework",
    "google_saif": "Google Secure AI Framework 2.0 - Risks",
    "databricks": "Databricks AI Security Framework 3.0",
}

TOP_LEVEL_TOTALS: Dict[str, int] = {
    "owasp_llm": 10,
    "owasp_ml": 10,
    "owasp_agentic": 10,
}

FRAMEWORK_ORDER: List[str] = list(FRAMEWORK_LABELS.keys())


def framework_key(framework_name: str) -> Optional[str]:
    """Map AIDEFEND framework labels to stable internal keys."""
    name = framework_name.upper().strip()

    if "OWASP" in name and "LLM" in name:
        return "owasp_llm"
    if "OWASP" in name and "ML" in name:
        return "owasp_ml"
    if "OWASP" in name and "AGENTIC" in name:
        return "owasp_agentic"
    if "ATLAS" in name or "MITRE ATLAS" in name:
        return "atlas"
    if "MAESTRO" in name:
        return "maestro"
    if "NIST ADVERSARIAL MACHINE LEARNING" in name:
        return "nist_aml"
    if "CISCO INTEGRATED AI SECURITY AND SAFETY FRAMEWORK" in name:
        return "cisco"
    if "GOOGLE SECURE AI FRAMEWORK" in name:
        return "google_saif"
    if "DATABRICKS AI SECURITY FRAMEWORK" in name:
        return "databricks"

    return None


def parse_json_list(value: Any) -> List[Any]:
    """Safely parse a JSON list field stored in LanceDB."""
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def is_actionable_record(record: Dict[str, Any]) -> bool:
    """
    Determine whether a record is directly implementable.

    Parent techniques that only group sub-techniques are not actionable.
    Standalone techniques and sub-techniques are actionable.
    """
    doc_type = record.get("type")
    if doc_type == "subtechnique":
        return True
    if doc_type != "technique":
        return False

    if parse_json_list(record.get("pillar")) or parse_json_list(record.get("phase")):
        return True

    guidance = parse_json_list(record.get("implementation_guidance"))
    return bool(guidance)


def iter_framework_keys(include_union: bool = False) -> List[str]:
    keys = ["owasp"] + FRAMEWORK_ORDER if include_union else FRAMEWORK_ORDER[:]
    return keys


def empty_framework_sets(include_union: bool = False) -> Dict[str, Set[str]]:
    return {key: set() for key in iter_framework_keys(include_union=include_union)}


def coverage_lists_from_sets(coverage: Dict[str, Set[str]]) -> Dict[str, List[str]]:
    return {key: sorted(list(values)) for key, values in coverage.items()}


def normalize_framework_item(framework_name: str, item: str) -> Optional[str]:
    """Normalize a framework mapping item into a stable canonical identifier."""
    if not item or not isinstance(item, str):
        return None

    item = item.strip()
    if not item or item.upper().startswith("N/A"):
        return None

    key = framework_key(framework_name)
    item_upper = item.upper()

    if key == "owasp_llm":
        match = re.search(r"LLM\d{2}", item_upper)
        return match.group(0) if match else None

    if key == "owasp_ml":
        match = re.search(r"ML\d{2}:2023", item_upper)
        return match.group(0) if match else None

    if key == "owasp_agentic":
        match = re.search(r"ASI\d{2}:2026", item_upper)
        return match.group(0) if match else None

    if key == "atlas":
        match = re.search(r"AML\.T\d{4}(?:\.\d{3})?", item_upper)
        if match:
            return match.group(0)
        fallback = re.search(r"T\d{4}(?:\.\d{3})?", item_upper)
        return f"AML.{fallback.group(0)}" if fallback else None

    if key == "nist_aml":
        match = re.search(r"NISTAML\.\d{3}", item_upper)
        return match.group(0) if match else None

    if key == "cisco":
        match = re.search(r"AI(?:SUBTECH|TECH)-[\d\.]+", item_upper)
        return match.group(0) if match else None

    if key == "google_saif":
        return item.split(":", 1)[0].strip().upper()

    if key == "databricks":
        return re.sub(r"\s+\([^()]*\)$", "", item).strip()

    if key == "maestro":
        layered_match = re.match(r"^(.+?\(L\d\))(?:\s+\([^()]*\))+$", item)
        if layered_match:
            return layered_match.group(1).strip()
        if item.count("(") > 1:
            return re.sub(r"\s+\([^()]*\)$", "", item).strip()
        return item

    return item


def extract_framework_coverage(defends_against: Iterable[Dict[str, Any]]) -> Dict[str, Set[str]]:
    """Extract normalized framework coverage sets from a defendsAgainst list."""
    coverage = empty_framework_sets()

    for mapping in defends_against or []:
        framework_name = mapping.get("framework", "")
        key = framework_key(framework_name)
        if not key:
            continue

        for item in mapping.get("items", []):
            normalized = normalize_framework_item(framework_name, item)
            if normalized:
                coverage[key].add(normalized)

    return coverage


def merge_framework_coverage_sets(*coverage_sets: Dict[str, Set[str]]) -> Dict[str, Set[str]]:
    """Merge multiple framework coverage dictionaries into one."""
    merged = empty_framework_sets(include_union=True)

    for coverage in coverage_sets:
        for key in FRAMEWORK_ORDER:
            merged[key].update(coverage.get(key, set()))

    merged["owasp"].update(merged["owasp_llm"])
    merged["owasp"].update(merged["owasp_ml"])
    merged["owasp"].update(merged["owasp_agentic"])

    return merged


def build_framework_metrics(
    covered_sets: Dict[str, Set[str]],
    total_sets: Dict[str, Set[str]],
) -> Dict[str, Any]:
    """Build a consistent metrics payload for framework coverage."""
    metrics: Dict[str, Any] = {
        "by_framework": {},
    }

    for key in FRAMEWORK_ORDER:
        covered_count = len(covered_sets.get(key, set()))
        dynamic_total = len(total_sets.get(key, set()))
        top_level_total = TOP_LEVEL_TOTALS.get(key)
        total = top_level_total if top_level_total is not None else dynamic_total
        percentage = round((covered_count / total) * 100, 1) if total else 0.0

        metrics["by_framework"][key] = {
            "label": FRAMEWORK_LABELS[key],
            "items_covered": covered_count,
            "total_items": total,
            "coverage_percentage": percentage,
        }

    metrics["owasp_llm_items_covered"] = metrics["by_framework"]["owasp_llm"]["items_covered"]
    metrics["owasp_llm_total_items"] = metrics["by_framework"]["owasp_llm"]["total_items"]
    metrics["owasp_llm_coverage_percentage"] = metrics["by_framework"]["owasp_llm"]["coverage_percentage"]
    metrics["owasp_ml_items_covered"] = metrics["by_framework"]["owasp_ml"]["items_covered"]
    metrics["owasp_agentic_items_covered"] = metrics["by_framework"]["owasp_agentic"]["items_covered"]
    metrics["mitre_atlas_items_covered"] = metrics["by_framework"]["atlas"]["items_covered"]
    metrics["maestro_items_covered"] = metrics["by_framework"]["maestro"]["items_covered"]
    metrics["nist_aml_items_covered"] = metrics["by_framework"]["nist_aml"]["items_covered"]
    metrics["cisco_items_covered"] = metrics["by_framework"]["cisco"]["items_covered"]
    metrics["google_saif_items_covered"] = metrics["by_framework"]["google_saif"]["items_covered"]
    metrics["databricks_items_covered"] = metrics["by_framework"]["databricks"]["items_covered"]

    return metrics
