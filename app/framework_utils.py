"""
Framework normalization helpers for AIDEFEND threat mappings.

These helpers convert framework-specific item strings into stable canonical IDs
so analytics can stay correct even when AIDEFEND adds annotations or expands
the number of referenced frameworks.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set, TypeVar

FRAMEWORK_LABELS: Dict[str, str] = {
    "owasp_llm": "OWASP LLM Top 10 2025",
    "owasp_ml": "OWASP ML Top 10 2023",
    "owasp_agentic": "OWASP Top 10 for Agentic Applications 2026",
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
UNKNOWN_FRAMEWORK_KEY_PREFIX = "framework:"
_CoverageValue = TypeVar("_CoverageValue")


class FrameworkLabelMap(dict[str, str]):
    """Active labels plus non-serialized aliases from prior registry editions.

    The object intentionally remains a normal ``dict`` for public response and
    Pydantic compatibility.  Edition aliases are runtime lookup metadata only;
    callers still see one active label per stable framework key.
    """

    def __init__(
        self,
        labels: Mapping[str, str],
        *,
        edition_aliases: Iterable[tuple[str, str]] = (),
    ) -> None:
        super().__init__(labels)
        self.edition_aliases = tuple(edition_aliases)


def framework_coverage_key(
    framework_name: str,
    *,
    framework_labels: Optional[Mapping[str, str]] = None,
) -> Optional[str]:
    """Return the stable coverage key for a framework label.

    Known AIDEFEND framework labels keep their long-standing internal keys.
    An additive framework that this MCP version does not know yet is retained
    under an explicit source-label key instead of being silently discarded.
    """
    if not isinstance(framework_name, str):
        return None

    known_key = framework_key(
        framework_name,
        framework_labels=framework_labels,
    )
    if known_key:
        return known_key

    exact_label = framework_name.strip()
    return f"{UNKNOWN_FRAMEWORK_KEY_PREFIX}{exact_label}" if exact_label else None


def framework_labels_from_registry(
    registry: Optional[Mapping[str, Any]],
) -> Dict[str, str]:
    """Return effective labels for one atomically activated framework registry.

    ``FRAMEWORK_LABELS`` deliberately remains the legacy/no-registry fallback.
    That lets a newly installed MCP package continue to describe an existing
    2025 index truthfully until a successful sync atomically activates the 2026
    corpus and its migration registry together.
    """
    labels = dict(FRAMEWORK_LABELS)
    if registry is None:
        return FrameworkLabelMap(labels)

    from app.framework_migrations import validate_framework_migration_registry

    # Absence means a supported legacy index. Presence plus invalid content is
    # corruption or an unsupported contract and must not be mislabeled as 2025.
    validated = validate_framework_migration_registry(registry)

    frameworks = validated.get("frameworks")
    if not isinstance(frameworks, Mapping):
        return labels

    edition_aliases: List[tuple[str, str]] = []
    for key in labels:
        entry = frameworks.get(key)
        if not isinstance(entry, Mapping) or entry.get("stableKey") != key:
            continue
        active_label = entry.get("activeLabel")
        if isinstance(active_label, str) and active_label.strip() == active_label:
            labels[key] = active_label
        editions = entry.get("editions")
        if isinstance(editions, Mapping):
            for edition_record in editions.values():
                if not isinstance(edition_record, Mapping):
                    continue
                edition_label = edition_record.get("label")
                if isinstance(edition_label, str):
                    edition_aliases.append((edition_label, key))
    effective = FrameworkLabelMap(
        labels,
        edition_aliases=edition_aliases,
    )
    _framework_label_index(effective)
    return effective


def framework_labels_from_version_info(
    version_info: Optional[Mapping[str, Any]],
) -> Dict[str, str]:
    """Resolve labels from the migration registry in atomic version metadata.

    A genuinely absent registry key identifies the supported legacy index.
    Once the key is present, its value is part of the activated atomic contract;
    malformed values must fail closed instead of being mistaken for absence.
    """
    if not isinstance(version_info, Mapping) or (
        "framework_migrations" not in version_info
    ):
        return framework_labels_from_registry(None)

    registry = version_info["framework_migrations"]
    if not isinstance(registry, Mapping):
        from app.framework_migrations import FrameworkMigrationRegistryError

        raise FrameworkMigrationRegistryError(
            "version_info.framework_migrations must be an object when present"
        )
    return framework_labels_from_registry(registry)


def framework_coverage_label(
    coverage_key: str,
    framework_labels: Optional[Mapping[str, str]] = None,
) -> str:
    """Return the source-facing label for a known or additive coverage key."""
    labels = _effective_framework_labels(framework_labels)
    if coverage_key in labels:
        return labels[coverage_key]
    return framework_public_coverage_key(coverage_key)


def framework_public_coverage_key(coverage_key: str) -> str:
    """Hide the collision-safe prefix used for additive framework keys."""
    if coverage_key.startswith(UNKNOWN_FRAMEWORK_KEY_PREFIX):
        return coverage_key[len(UNKNOWN_FRAMEWORK_KEY_PREFIX):]
    return coverage_key


def public_framework_coverage_mapping(
    coverage: Mapping[str, _CoverageValue],
) -> Dict[str, _CoverageValue]:
    """Expose internal framework keys without losing colliding source labels.

    Additive framework labels use a ``framework:`` prefix internally so a raw
    source label cannot collide with a known framework key. Public responses
    normally expose the original source label, but retain the internal prefix
    when stripping it would collide with a known/union key or another internal
    key in the same mapping.
    """
    internal_keys = set(coverage)
    reserved_public_keys = set(FRAMEWORK_ORDER) | {"owasp"}
    public: Dict[str, _CoverageValue] = {}

    for internal_key, value in coverage.items():
        public_key = framework_public_coverage_key(internal_key)
        if internal_key.startswith(UNKNOWN_FRAMEWORK_KEY_PREFIX) and (
            public_key in reserved_public_keys
            or (public_key in internal_keys and public_key != internal_key)
        ):
            public_key = internal_key

        # The original internal key is unique and is therefore the safest
        # fallback for unusual collision chains, including labels that begin
        # with the internal prefix themselves.
        if public_key in public and public_key != internal_key:
            public_key = internal_key
        public[public_key] = value

    return public


# Canonical MAESTRO labels present in AIDEFEND schema 2.3. MAESTRO does not
# expose stable machine IDs in the framework data, so callers must use these
# exact labels rather than legacy classifier slugs such as
# ``L7-Agent-Tool-Misuse``.
MAESTRO_CANONICAL_THREATS: Set[str] = {
    "Adversarial Examples (L1)",
    "Agent Goal Manipulation (L7)",
    "Agent Identity Attack (L7)",
    "Agent Impersonation (L7)",
    "Agent Pricing Model Manipulation (L7)",
    "Agent Tool Misuse (L7)",
    "Backdoor Attacks (L1)",
    "Backdoor Attacks (L3)",
    "Bias in Security AI Agents (L6)",
    "Compromised Agent Registry (L7)",
    "Compromised Agents (L7)",
    "Compromised Container Images (L4)",
    "Compromised Framework Components (L3)",
    "Compromised Observability Tools (L5)",
    "Compromised RAG Pipelines (L2)",
    "Compromised Security AI Agents (L6)",
    "Data Exfiltration (L2)",
    "Data Leakage (Cross-Layer)",
    "Data Leakage through Observability (L5)",
    "Data Poisoning (L2)",
    "Data Poisoning (Training Phase)",
    "Data Poisoning (Training Phase) (L1)",
    "Data Tampering (L2)",
    "Denial of Service (DoS) Attacks",
    "Denial of Service (DoS) Attacks (L1)",
    "Denial of Service (DoS) Attacks (L4)",
    "Denial of Service on Data Infrastructure (L2)",
    "Denial of Service on Framework APIs (L3)",
    "Evasion of Detection (L5)",
    "Evasion of Security AI Agents (L6)",
    "Framework Evasion (L3)",
    "Goal Misalignment Cascades (Cross-Layer)",
    "Inaccurate Agent Capability Description (L7)",
    "Infrastructure-as-Code (IaC) Manipulation",
    "Infrastructure-as-Code (IaC) Manipulation (L4)",
    "Input Validation Attacks (L3)",
    "Integration Risks (L7)",
    "Lack of Explainability in Security AI Agents (L6)",
    "Lateral Movement (Cross-Layer)",
    "Lateral Movement (L4)",
    "Malicious Agent Discovery (L7)",
    "Manipulation of Evaluation Metrics (L5)",
    "Membership Inference Attacks (L1)",
    "Model Extraction of AI Security Agents (L6)",
    "Model Stealing (L1)",
    "Orchestration Attacks (L4)",
    "Poisoning Observability Data (L5)",
    "Privilege Escalation (Cross-Layer)",
    "Regulatory Non-Compliance by AI Security Agents (L6)",
    "Reprogramming Attacks (L1)",
    "Repudiation (L7)",
    "Resource Hijacking (L4)",
    "Security Agent Data Poisoning (L6)",
    "Supply Chain Attacks (Cross-Layer)",
    "Supply Chain Attacks (L3)",
}

_MAESTRO_BY_CASEFOLD = {
    value.casefold(): value for value in MAESTRO_CANONICAL_THREATS
}

_MAESTRO_BY_UNIQUE_BASE: Dict[str, Optional[str]] = {}
for _maestro_value in MAESTRO_CANONICAL_THREATS:
    _maestro_base = re.sub(
        r"\s+\((?:L\d+|Cross-Layer)\)$",
        "",
        _maestro_value,
        flags=re.IGNORECASE,
    ).casefold()
    if _maestro_base in _MAESTRO_BY_UNIQUE_BASE:
        _MAESTRO_BY_UNIQUE_BASE[_maestro_base] = None
    else:
        _MAESTRO_BY_UNIQUE_BASE[_maestro_base] = _maestro_value

# Legacy spellings whose wording cannot be reconstructed by just moving the
# layer prefix to the end of the label.
_MAESTRO_LEGACY_OVERRIDES: Dict[str, str] = {
    "L1-Data-Poisoning-Training-Phase": "Data Poisoning (Training Phase) (L1)",
    "L1-DoS-On-Foundation-Model": "Denial of Service (DoS) Attacks (L1)",
    "L1-Membership-Inference": "Membership Inference Attacks (L1)",
    "L2-DoS-On-Data-Infrastructure": "Denial of Service on Data Infrastructure (L2)",
    "L3-DoS-On-Framework-APIs": "Denial of Service on Framework APIs (L3)",
    "L4-DoS-On-AI-Infrastructure": "Denial of Service (DoS) Attacks (L4)",
    "L4-IaC-Manipulation": "Infrastructure-as-Code (IaC) Manipulation (L4)",
}


def canonicalize_maestro_identifier(value: str) -> Optional[str]:
    """Resolve a current MAESTRO label or a legacy classifier slug.

    ``None`` means the value has no mapping in the current AIDEFEND corpus and
    must not be presented as a resolvable framework claim.
    """
    if not isinstance(value, str) or not value.strip():
        return None

    value = value.strip()
    exact = _MAESTRO_BY_CASEFOLD.get(value.casefold())
    if exact:
        return exact

    # Preserve the historical public API's layer-less examples when the label
    # resolves to exactly one current MAESTRO item. Ambiguous names such as
    # Backdoor Attacks intentionally fail closed.
    unique_base = _MAESTRO_BY_UNIQUE_BASE.get(value.casefold())
    if unique_base:
        return unique_base

    overridden = _MAESTRO_LEGACY_OVERRIDES.get(value)
    if overridden:
        return overridden

    match = re.fullmatch(r"(L\d+|Cross)-(.+)", value, flags=re.IGNORECASE)
    if not match:
        return None

    layer = match.group(1).upper()
    label = re.sub(r"[-_]+", " ", match.group(2)).strip()
    suffix = "Cross-Layer" if layer == "CROSS" else layer
    candidate = f"{label} ({suffix})"
    return _MAESTRO_BY_CASEFOLD.get(candidate.casefold())


def _legacy_framework_key(framework_name: str) -> Optional[str]:
    """Classify labels understood before the migration registry existed."""
    if not isinstance(framework_name, str):
        return None
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


def _framework_label_index(
    framework_labels: Mapping[str, str],
) -> Dict[str, str]:
    """Validate and index active plus superseded edition labels."""
    from app.framework_migrations import FrameworkMigrationRegistryError

    exact: Dict[str, str] = {}

    def register(key: str, label: str, *, label_kind: str) -> None:
        if key not in FRAMEWORK_LABELS:
            raise FrameworkMigrationRegistryError(
                f"unknown stable framework key in {label_kind}: {key!r}"
            )
        if (
            not isinstance(label, str)
            or not label
            or label != label.strip()
        ):
            raise FrameworkMigrationRegistryError(
                f"{label_kind} for {key!r} must be a non-empty non-padded string"
            )
        folded = label.casefold()
        prior_key = exact.get(folded)
        if prior_key is not None and prior_key != key:
            raise FrameworkMigrationRegistryError(
                "effective framework labels and edition aliases collide "
                "case-insensitively: "
                f"{prior_key!r} and {key!r} both use {label!r}"
            )
        legacy_key = _legacy_framework_key(label)
        if legacy_key is not None and legacy_key != key:
            raise FrameworkMigrationRegistryError(
                f"{label_kind} {label!r} for {key!r} is classified as "
                f"legacy stable key {legacy_key!r}"
            )
        exact[folded] = key

    for key, label in framework_labels.items():
        register(key, label, label_kind="active label")

    aliases = getattr(framework_labels, "edition_aliases", ())
    if not isinstance(aliases, tuple):
        raise FrameworkMigrationRegistryError(
            "framework edition aliases must be an immutable sequence"
        )
    for alias in aliases:
        if (
            not isinstance(alias, tuple)
            or len(alias) != 2
        ):
            raise FrameworkMigrationRegistryError(
                "framework edition aliases must contain label/key pairs"
            )
        label, key = alias
        register(key, label, label_kind="edition label")
    return exact


def _effective_framework_labels(
    framework_labels: Optional[Mapping[str, str]],
) -> Dict[str, str]:
    labels = dict(FRAMEWORK_LABELS)
    edition_aliases: Iterable[tuple[str, str]] = ()
    if framework_labels is not None:
        if not isinstance(framework_labels, Mapping):
            from app.framework_migrations import FrameworkMigrationRegistryError

            raise FrameworkMigrationRegistryError(
                "effective framework labels must be an object"
            )
        for key, label in framework_labels.items():
            if key not in FRAMEWORK_LABELS:
                from app.framework_migrations import FrameworkMigrationRegistryError

                raise FrameworkMigrationRegistryError(
                    f"unknown stable framework key in active labels: {key!r}"
                )
            labels[key] = label
        edition_aliases = getattr(framework_labels, "edition_aliases", ())
    effective = FrameworkLabelMap(
        labels,
        edition_aliases=edition_aliases,
    )
    _framework_label_index(effective)
    return effective


def framework_key(
    framework_name: str,
    *,
    framework_labels: Optional[Mapping[str, str]] = None,
) -> Optional[str]:
    """Map an active, legacy, or static framework label to a stable key."""
    if not isinstance(framework_name, str):
        return None

    if framework_labels is not None:
        labels = _effective_framework_labels(framework_labels)
        exact = _framework_label_index(labels)
        exact_key = exact.get(framework_name.strip().casefold())
        if exact_key is not None:
            return exact_key

    return _legacy_framework_key(framework_name)


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
    # Schema 3.x stores the framework's explicit control-unit decision. Keep
    # the legacy inference below so an older index remains readable long
    # enough for the normal schema-version check to trigger a clean rebuild.
    explicit = record.get("is_actionable")
    if isinstance(explicit, bool):
        return explicit

    doc_type = record.get("type")
    if doc_type == "subtechnique":
        return True
    if doc_type != "technique":
        return False

    if parse_json_list(record.get("pillar")) or parse_json_list(record.get("phase")):
        return True

    guidance = parse_json_list(record.get("implementation_guidance"))
    return bool(guidance)


def resolve_control_ids(
    requested_ids: Iterable[str],
    records: Iterable[Dict[str, Any]],
) -> Dict[str, Any]:
    """Resolve current control IDs and expand non-actionable parent families.

    The returned ``actionable_ids`` are safe to use for scoring and coverage.
    Unknown or shifted IDs stay visible in ``unrecognized_ids`` instead of
    being silently counted as implemented controls.
    """
    normalized_ids = list(dict.fromkeys(
        technique_id.strip().upper() for technique_id in requested_ids
    ))
    record_list = list(records)
    records_by_id = {
        record.get("source_id"): record
        for record in record_list
        if record.get("source_id")
    }
    actionable_by_id = {
        source_id: record
        for source_id, record in records_by_id.items()
        if is_actionable_record(record)
    }

    parent_to_children: Dict[str, List[str]] = {}
    for source_id, record in actionable_by_id.items():
        parent_id = record.get("parent_technique_id")
        if parent_id:
            parent_to_children.setdefault(parent_id, []).append(source_id)
    for child_ids in parent_to_children.values():
        child_ids.sort()

    valid_input_ids: List[str] = []
    actionable_ids: List[str] = []
    expanded_parent_families: Dict[str, List[str]] = {}
    unrecognized_ids: List[str] = []

    for technique_id in normalized_ids:
        if technique_id in actionable_by_id:
            valid_input_ids.append(technique_id)
            actionable_ids.append(technique_id)
            continue

        child_ids = parent_to_children.get(technique_id, [])
        if technique_id in records_by_id and child_ids:
            valid_input_ids.append(technique_id)
            expanded_parent_families[technique_id] = child_ids
            actionable_ids.extend(child_ids)
            continue

        unrecognized_ids.append(technique_id)

    return {
        "normalized_ids": normalized_ids,
        "valid_input_ids": valid_input_ids,
        "actionable_ids": list(dict.fromkeys(actionable_ids)),
        "expanded_parent_families": expanded_parent_families,
        "unrecognized_ids": unrecognized_ids,
    }


def iter_framework_keys(include_union: bool = False) -> List[str]:
    keys = ["owasp"] + FRAMEWORK_ORDER if include_union else FRAMEWORK_ORDER[:]
    return keys


def empty_framework_sets(include_union: bool = False) -> Dict[str, Set[str]]:
    return {key: set() for key in iter_framework_keys(include_union=include_union)}


def coverage_lists_from_sets(coverage: Dict[str, Set[str]]) -> Dict[str, List[str]]:
    return public_framework_coverage_mapping(
        {key: sorted(values) for key, values in coverage.items()}
    )


def _trailing_parenthetical_start(text: str, end: int) -> Optional[int]:
    """Offset where the trailing ``" (...)"`` group of ``text[:end]`` begins.

    ``None`` when ``text[:end]`` does not end with whitespace followed by a
    parenthetical that holds no nested parentheses. This is the linear-time
    equivalent of matching ``\\s+\\([^()]*\\)$``, which backtracks
    quadratically on labels carrying many parenthetical groups (CWE-1333).
    """
    if end <= 0 or text[end - 1] != ")":
        return None

    open_index = end - 2
    while open_index >= 0 and text[open_index] not in "()":
        open_index -= 1
    if open_index < 0 or text[open_index] != "(":
        return None

    start = open_index
    while start > 0 and text[start - 1].isspace():
        start -= 1
    return None if start == open_index else start


def _strip_trailing_parenthetical(item: str) -> str:
    """Drop one trailing ``" (...)"`` annotation from an already-stripped item."""
    start = _trailing_parenthetical_start(item, len(item))
    return item if start is None else item[:start].strip()


def _ends_with_maestro_layer(text: str, end: int) -> bool:
    """Whether ``text[:end]`` ends with a ``(L<digit>)`` layer marker."""
    return (
        end >= 4
        and text[end - 1] == ")"
        and text[end - 4] == "("
        and text[end - 3] == "L"
        and text[end - 2] in "0123456789"
    )


def normalize_framework_item(
    framework_name: str,
    item: str,
    *,
    framework_labels: Optional[Mapping[str, str]] = None,
) -> Optional[str]:
    """Normalize a framework mapping item into a stable canonical identifier."""
    if not item or not isinstance(item, str):
        return None

    item = item.strip()
    if not item or item.upper().startswith("N/A"):
        return None

    key = framework_key(
        framework_name,
        framework_labels=framework_labels,
    )
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
        return _strip_trailing_parenthetical(item)

    if key == "maestro":
        # Peel trailing parentheticals one at a time, then keep the shortest
        # prefix that still ends in a layer marker. This mirrors the lazy match
        # of ``^(.+?\(L\d\))(?:\s+\([^()]*\))+$`` without its backtracking, and
        # the newline check reproduces ``.`` never spanning a line break.
        boundaries: List[int] = []
        end = len(item)
        while True:
            start = _trailing_parenthetical_start(item, end)
            if start is None:
                break
            boundaries.append(start)
            end = start

        first_newline = item.find("\n")
        for boundary in reversed(boundaries):
            if (
                boundary > 4
                and _ends_with_maestro_layer(item, boundary)
                and (first_newline == -1 or first_newline >= boundary - 4)
            ):
                return item[:boundary].strip()

        if item.count("(") > 1:
            return _strip_trailing_parenthetical(item)
        return item

    if key is None:
        generic_id = re.match(
            r'^([A-Za-z][A-Za-z0-9]*(?:[._:/-][A-Za-z0-9]+)+)'
            r'(?=$|[\s:;,)\]])',
            item,
        )
        if generic_id:
            return generic_id.group(1).upper()

    return item


def extract_framework_coverage(
    defends_against: Iterable[Dict[str, Any]],
    *,
    framework_labels: Optional[Mapping[str, str]] = None,
) -> Dict[str, Set[str]]:
    """Extract normalized framework coverage sets from a defendsAgainst list."""
    coverage = empty_framework_sets()

    for mapping in defends_against or []:
        framework_name = mapping.get("framework", "")
        key = framework_coverage_key(
            framework_name,
            framework_labels=framework_labels,
        )
        if not key:
            continue

        for item in mapping.get("items", []):
            normalized = normalize_framework_item(
                framework_name,
                item,
                framework_labels=framework_labels,
            )
            if normalized:
                coverage.setdefault(key, set()).add(normalized)

    return coverage


def merge_framework_coverage_sets(*coverage_sets: Dict[str, Set[str]]) -> Dict[str, Set[str]]:
    """Merge multiple framework coverage dictionaries into one."""
    merged = empty_framework_sets(include_union=True)

    for coverage in coverage_sets:
        for key, values in coverage.items():
            if key == "owasp":
                continue
            merged.setdefault(key, set()).update(values)

    merged["owasp"].update(merged["owasp_llm"])
    merged["owasp"].update(merged["owasp_ml"])
    merged["owasp"].update(merged["owasp_agentic"])

    return merged


def build_framework_metrics(
    covered_sets: Dict[str, Set[str]],
    total_sets: Dict[str, Set[str]],
    *,
    framework_labels: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    """Build a consistent metrics payload for framework coverage."""
    labels = _effective_framework_labels(framework_labels)
    metrics: Dict[str, Any] = {
        "by_framework": {},
    }

    for key in FRAMEWORK_ORDER:
        covered_count = len(covered_sets.get(key, set()))
        top_level_total = TOP_LEVEL_TOTALS.get(key)
        total = top_level_total
        percentage = (
            round((covered_count / total) * 100, 1)
            if total is not None and total > 0
            else None
        )

        metrics["by_framework"][key] = {
            "label": labels[key],
            "items_covered": covered_count,
            "total_items": total,
            "coverage_percentage": percentage,
            "coverage_scope": (
                "authoritative_top_level_total"
                if top_level_total is not None
                else "mapped_items_count_only"
            ),
        }

    dynamic_keys = sorted(
        (set(covered_sets) | set(total_sets)) - set(FRAMEWORK_ORDER) - {"owasp"}
    )
    dynamic_metrics = {}
    for key in dynamic_keys:
        dynamic_metrics[key] = {
            "label": framework_coverage_label(key, labels),
            "items_covered": len(covered_sets.get(key, set())),
            "total_items": None,
            "coverage_percentage": None,
            "coverage_scope": "mapped_items_count_only",
        }
    metrics["by_framework"].update(
        public_framework_coverage_mapping(dynamic_metrics)
    )

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
