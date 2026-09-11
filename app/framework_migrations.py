"""Framework edition-registry validation and semantic reference resolution.

The migration registry is authored and released by the AIDEFEND Framework.
This module deliberately resolves superseded identifiers by their declared
semantic successor instead of assuming that a rank keeps the same meaning.
"""

from __future__ import annotations

import re
from copy import deepcopy
from datetime import date
from typing import Any, Dict, List, Mapping, Optional
from urllib.parse import urlsplit

SUPPORTED_REGISTRY_SCHEMA_VERSION = "1.0"
RESOLUTION_STATUSES = {
    "canonical",
    "migrated",
    "normalized",
    "fallback_latest",
    "ambiguous",
    "invalid",
}


class FrameworkMigrationRegistryError(ValueError):
    """Raised when a framework migration registry violates its contract."""


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FrameworkMigrationRegistryError(f"{path} must be an object")
    return value


def _list(value: Any, path: str) -> List[Any]:
    if not isinstance(value, list):
        raise FrameworkMigrationRegistryError(f"{path} must be an array")
    return value


def _text(value: Any, path: str, *, maximum: int = 4096) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(ord(character) < 32 and character not in "\t\n\r" for character in value)
    ):
        raise FrameworkMigrationRegistryError(
            f"{path} must be a non-empty, non-padded string of at most {maximum} characters"
        )
    return value


def _positive_integer(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise FrameworkMigrationRegistryError(f"{path} must be a positive integer")
    return value


def _https_url(value: Any, path: str, *, required_host: Optional[str] = None) -> str:
    url = _text(value, path)
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise FrameworkMigrationRegistryError(f"{path} must be a canonical HTTPS URL")
    if required_host and parsed.hostname.casefold() != required_host.casefold():
        raise FrameworkMigrationRegistryError(
            f"{path} must use the official {required_host} host"
        )
    return url


def _validate_catalog(key: str, raw_catalog: Any) -> None:
    catalog = _mapping(raw_catalog, f"frameworks.{key}")
    if catalog.get("stableKey") != key:
        raise FrameworkMigrationRegistryError(
            f"frameworks.{key}.stableKey must equal its registry key"
        )

    active_edition = _text(
        catalog.get("activeEdition"), f"frameworks.{key}.activeEdition", maximum=32
    )
    active_label = _text(
        catalog.get("activeLabel"),
        f"frameworks.{key}.activeLabel",
        maximum=256,
    )
    _text(catalog.get("officialTitle"), f"frameworks.{key}.officialTitle", maximum=256)
    _https_url(catalog.get("sourceUrl"), f"frameworks.{key}.sourceUrl")

    editions = _mapping(catalog.get("editions"), f"frameworks.{key}.editions")
    if active_edition not in editions:
        raise FrameworkMigrationRegistryError(
            f"frameworks.{key}.editions must contain the active edition"
        )
    for edition, raw_edition in editions.items():
        _text(edition, f"frameworks.{key}.editions key", maximum=32)
        edition_record = _mapping(raw_edition, f"frameworks.{key}.editions.{edition}")
        _text(
            edition_record.get("label"),
            f"frameworks.{key}.editions.{edition}.label",
            maximum=256,
        )
        status = _text(
            edition_record.get("status"),
            f"frameworks.{key}.editions.{edition}.status",
            maximum=32,
        )
        if status not in {"current", "superseded"}:
            raise FrameworkMigrationRegistryError(
                f"frameworks.{key}.editions.{edition}.status is unsupported"
            )
    current_editions = {
        edition
        for edition, edition_record in editions.items()
        if edition_record.get("status") == "current"
    }
    if current_editions != {active_edition}:
        raise FrameworkMigrationRegistryError(
            f"frameworks.{key} must declare exactly its active edition as current"
        )
    if editions[active_edition].get("label") != active_label:
        raise FrameworkMigrationRegistryError(
            f"frameworks.{key}.activeLabel must exactly match the active edition label"
        )

    response_contract = _mapping(
        catalog.get("responseContract"), f"frameworks.{key}.responseContract"
    )
    if response_contract.get("canonicalEdition") != active_edition:
        raise FrameworkMigrationRegistryError(
            f"frameworks.{key}.responseContract canonical edition differs"
        )
    _text(
        response_contract.get("canonicalIdFormat"),
        f"frameworks.{key}.responseContract.canonicalIdFormat",
        maximum=128,
    )
    if response_contract.get("metadataField") != "resolution":
        raise FrameworkMigrationRegistryError(
            f"frameworks.{key}.responseContract.metadataField must be resolution"
        )
    metadata_values = _list(
        response_contract.get("metadataValues"),
        f"frameworks.{key}.responseContract.metadataValues",
    )
    if (
        any(not isinstance(value, str) for value in metadata_values)
        or len(metadata_values) != len(set(metadata_values))
        or set(metadata_values) != RESOLUTION_STATUSES
    ):
        raise FrameworkMigrationRegistryError(
            f"frameworks.{key}.responseContract.metadataValues is unsupported"
        )

    active_items = _list(catalog.get("activeItems"), f"frameworks.{key}.activeItems")
    if not active_items or len(active_items) > 1000:
        raise FrameworkMigrationRegistryError(
            f"frameworks.{key}.activeItems must contain 1 through 1000 items"
        )
    # Every catalog shares the envelope/edition invariants above. Cisco's
    # hierarchy has no ranks and can repeat names across independent branches.
    # Keep the original ranked catalog contract available for other profiles;
    # admission of a profile does not imply that our resolver understands it.
    if key == "cisco" and _has_cisco_hierarchy(catalog):
        _validate_cisco_catalog(catalog)
        return
    active_by_id: Dict[str, Mapping[str, Any]] = {}
    ranks = set()
    names = set()
    for index, raw_item in enumerate(active_items):
        path = f"frameworks.{key}.activeItems[{index}]"
        item = _mapping(raw_item, path)
        identifier = _text(item.get("id"), f"{path}.id", maximum=128)
        rank = _positive_integer(item.get("rank"), f"{path}.rank")
        name = _text(item.get("name"), f"{path}.name", maximum=256)
        _text(item.get("description"), f"{path}.description", maximum=4096)
        if identifier in active_by_id or rank in ranks or name.casefold() in names:
            raise FrameworkMigrationRegistryError(
                f"{path} duplicates an active identifier, rank, or name"
            )
        active_by_id[identifier] = item
        ranks.add(rank)
        names.add(name.casefold())

        if key == "owasp_llm":
            match = re.fullmatch(r"LLM(\d{2}):([0-9]{4})", identifier)
            if not match or match.group(2) != active_edition or int(match.group(1)) != rank:
                raise FrameworkMigrationRegistryError(
                    f"{path} does not match its OWASP LLM rank and active edition"
                )

    if key == "owasp_llm" and (len(active_items) != 10 or ranks != set(range(1, 11))):
        raise FrameworkMigrationRegistryError(
            "frameworks.owasp_llm.activeItems must be exactly ranks 1 through 10"
        )

    migrations = _list(catalog.get("migrations"), f"frameworks.{key}.migrations")
    if len(migrations) > 1000:
        raise FrameworkMigrationRegistryError(f"frameworks.{key}.migrations exceeds 1000 entries")
    seen_from_ids = set()
    for index, raw_migration in enumerate(migrations):
        path = f"frameworks.{key}.migrations[{index}]"
        migration = _mapping(raw_migration, path)
        source = _mapping(migration.get("from"), f"{path}.from")
        target = _mapping(migration.get("to"), f"{path}.to")
        source_edition = _text(source.get("edition"), f"{path}.from.edition", maximum=32)
        source_id = _text(source.get("id"), f"{path}.from.id", maximum=128)
        _text(source.get("name"), f"{path}.from.name", maximum=256)
        target_edition = _text(target.get("edition"), f"{path}.to.edition", maximum=32)
        target_id = _text(target.get("id"), f"{path}.to.id", maximum=128)
        target_name = _text(target.get("name"), f"{path}.to.name", maximum=256)
        if source_edition not in editions or editions[source_edition].get("status") != "superseded":
            raise FrameworkMigrationRegistryError(
                f"{path}.from.edition is not a declared superseded edition"
            )
        if target_edition != active_edition or target_id not in active_by_id:
            raise FrameworkMigrationRegistryError(
                f"{path}.to must reference an active registry item"
            )
        if active_by_id[target_id].get("name") != target_name:
            raise FrameworkMigrationRegistryError(
                f"{path}.to.name differs from the active registry item"
            )
        if source_id in seen_from_ids:
            raise FrameworkMigrationRegistryError(f"{path}.from.id duplicates another migration")
        seen_from_ids.add(source_id)
        if migration.get("mappingCarryForward") != "requires-semantic-review":
            raise FrameworkMigrationRegistryError(
                f"{path}.mappingCarryForward must require semantic review"
            )
        _text(migration.get("relation"), f"{path}.relation", maximum=128)
        _text(migration.get("note"), f"{path}.note", maximum=4096)
        change_types = _list(migration.get("changeTypes"), f"{path}.changeTypes")
        if (
            not change_types
            or len(change_types) != len(set(change_types))
            or any(
                not isinstance(value, str) or not value or value != value.strip()
                for value in change_types
            )
        ):
            raise FrameworkMigrationRegistryError(
                f"{path}.changeTypes must be a non-empty unique string array"
            )
        if key == "owasp_llm":
            source_match = re.fullmatch(r"LLM(\d{2}):([0-9]{4})", source_id)
            if not source_match or source_match.group(2) != source_edition:
                raise FrameworkMigrationRegistryError(
                    f"{path}.from.id differs from its OWASP LLM edition"
                )

    if key == "owasp_llm":
        if not re.fullmatch(r"[0-9]{4}", active_edition):
            raise FrameworkMigrationRegistryError(
                "frameworks.owasp_llm.activeEdition must be a four-digit year"
            )
        superseded_editions = {
            edition for edition, value in editions.items() if value.get("status") == "superseded"
        }
        for edition in superseded_editions:
            expected_ids = {f"LLM{rank:02d}:{edition}" for rank in range(1, 11)}
            edition_ids = {
                migration["from"]["id"]
                for migration in migrations
                if migration["from"]["edition"] == edition
            }
            if edition_ids != expected_ids:
                raise FrameworkMigrationRegistryError(
                    f"frameworks.owasp_llm migrations do not completely cover {edition}"
                )

    # These sections are public provenance and policy surfaces. Their presence
    # is part of schema 1.0; the OWASP LLM catalog additionally has a strict
    # edition contract because clients expose this metadata as authoritative.
    source_artifact = _mapping(catalog.get("sourceArtifact"), f"frameworks.{key}.sourceArtifact")
    source_license = _mapping(catalog.get("sourceLicense"), f"frameworks.{key}.sourceLicense")
    resolution_policy = _mapping(
        catalog.get("resolutionPolicy"), f"frameworks.{key}.resolutionPolicy"
    )

    if key == "owasp_llm":
        expected_active_label = f"OWASP LLM Top 10 {active_edition}"
        expected_official_title = f"OWASP Top 10 for LLM Applications {active_edition}"
        if catalog.get("activeLabel") != expected_active_label:
            raise FrameworkMigrationRegistryError(
                "frameworks.owasp_llm.activeLabel differs from its active edition"
            )
        if catalog.get("officialTitle") != expected_official_title:
            raise FrameworkMigrationRegistryError(
                "frameworks.owasp_llm.officialTitle differs from its active edition"
            )
        _https_url(
            catalog.get("sourceUrl"),
            "frameworks.owasp_llm.sourceUrl",
            required_host="genai.owasp.org",
        )
        if response_contract.get("canonicalIdFormat") != f"LLMdd:{active_edition}":
            raise FrameworkMigrationRegistryError(
                "frameworks.owasp_llm.responseContract.canonicalIdFormat differs "
                "from its active edition"
            )

        for edition, edition_record in editions.items():
            if edition_record.get("label") != f"OWASP LLM Top 10 {edition}":
                raise FrameworkMigrationRegistryError(
                    f"frameworks.owasp_llm.editions.{edition}.label differs from its edition"
                )
            if edition_record.get("status") == "superseded":
                if edition_record.get("successorEdition") != active_edition:
                    raise FrameworkMigrationRegistryError(
                        f"frameworks.owasp_llm.editions.{edition}.successorEdition "
                        "must equal the active edition"
                    )

        release = _text(
            source_artifact.get("release"),
            "frameworks.owasp_llm.sourceArtifact.release",
            maximum=64,
        )
        _https_url(
            source_artifact.get("downloadUrl"),
            "frameworks.owasp_llm.sourceArtifact.downloadUrl",
            required_host="genai.owasp.org",
        )
        file_name = _text(
            source_artifact.get("fileName"),
            "frameworks.owasp_llm.sourceArtifact.fileName",
            maximum=255,
        )
        if "/" in file_name or "\\" in file_name:
            raise FrameworkMigrationRegistryError(
                "frameworks.owasp_llm.sourceArtifact.fileName must be a base name"
            )
        if source_artifact.get("mediaType") != "application/pdf":
            raise FrameworkMigrationRegistryError(
                "frameworks.owasp_llm.sourceArtifact.mediaType must be application/pdf"
            )
        _positive_integer(
            source_artifact.get("bytes"),
            "frameworks.owasp_llm.sourceArtifact.bytes",
        )
        _positive_integer(
            source_artifact.get("pageCount"),
            "frameworks.owasp_llm.sourceArtifact.pageCount",
        )
        artifact_sha = _text(
            source_artifact.get("sha256"),
            "frameworks.owasp_llm.sourceArtifact.sha256",
            maximum=64,
        )
        if not re.fullmatch(r"[A-Fa-f0-9]{64}", artifact_sha):
            raise FrameworkMigrationRegistryError(
                "frameworks.owasp_llm.sourceArtifact.sha256 must be 64 hexadecimal characters"
            )
        publication_date = source_artifact.get("publicationDate")
        if publication_date is not None:
            publication_date = _text(
                publication_date,
                "frameworks.owasp_llm.sourceArtifact.publicationDate",
                maximum=10,
            )
            try:
                date.fromisoformat(publication_date)
            except ValueError as exc:
                raise FrameworkMigrationRegistryError(
                    "frameworks.owasp_llm.sourceArtifact.publicationDate must be "
                    "null or a valid YYYY-MM-DD date"
                ) from exc
        _text(
            source_artifact.get("publicationDateStatus"),
            "frameworks.owasp_llm.sourceArtifact.publicationDateStatus",
            maximum=256,
        )
        if editions[active_edition].get("artifactRelease") != release:
            raise FrameworkMigrationRegistryError(
                "frameworks.owasp_llm active edition artifactRelease differs "
                "from sourceArtifact.release"
            )

        if source_license.get("spdxExpression") != "CC-BY-SA-4.0":
            raise FrameworkMigrationRegistryError(
                "frameworks.owasp_llm.sourceLicense.spdxExpression must be CC-BY-SA-4.0"
            )
        _https_url(
            source_license.get("licenseUrl"),
            "frameworks.owasp_llm.sourceLicense.licenseUrl",
        )
        for field in ("attribution", "scope", "changesMade"):
            _text(
                source_license.get(field),
                f"frameworks.owasp_llm.sourceLicense.{field}",
                maximum=2048,
            )

        required_policy_fields = {
            "omittedEdition",
            "latestEdition",
            "explicitCurrentId",
            "explicitSupersededId",
            "legacyName",
            "bareId",
            "nonPaddedRank",
            "editionContext",
            "malformedOrUnsupportedEdition",
            "multipleConcepts",
            "unversionedIdNameConflict",
            "versionedIdNameConflict",
            "mappingCarryForward",
        }
        if set(resolution_policy) != required_policy_fields:
            raise FrameworkMigrationRegistryError(
                "frameworks.owasp_llm.resolutionPolicy fields do not match schema 1.0"
            )
        for field in sorted(required_policy_fields):
            _text(
                resolution_policy[field],
                f"frameworks.owasp_llm.resolutionPolicy.{field}",
                maximum=2048,
            )

        active_ids = set(active_by_id)
        for edition in superseded_editions:
            edition_migrations = [
                migration for migration in migrations if migration["from"]["edition"] == edition
            ]
            target_ids = {migration["to"]["id"] for migration in edition_migrations}
            source_names = {
                migration["from"]["name"].casefold() for migration in edition_migrations
            }
            if target_ids != active_ids:
                raise FrameworkMigrationRegistryError(
                    f"frameworks.owasp_llm migrations from {edition} must map "
                    "one-to-one onto the active catalog"
                )
            if len(source_names) != len(edition_migrations):
                raise FrameworkMigrationRegistryError(
                    f"frameworks.owasp_llm migrations from {edition} contain "
                    "duplicate risk names"
                )


def validate_framework_migration_registry(
    registry: Mapping[str, Any],
) -> Dict[str, Any]:
    """Validate one registry and return a detached plain-dict copy."""
    root = _mapping(registry, "framework migration registry")
    if root.get("schemaVersion") != SUPPORTED_REGISTRY_SCHEMA_VERSION:
        raise FrameworkMigrationRegistryError(
            "framework migration registry schemaVersion is unsupported"
        )
    _text(root.get("registryVersion"), "registryVersion", maximum=64)
    _text(root.get("contract"), "contract", maximum=512)
    frameworks = _mapping(root.get("frameworks"), "frameworks")
    if not frameworks or len(frameworks) > 50:
        raise FrameworkMigrationRegistryError(
            "frameworks must contain 1 through 50 catalogs"
        )
    if "owasp_llm" not in frameworks:
        raise FrameworkMigrationRegistryError(
            "frameworks.owasp_llm is required by registry schema 1.0"
        )
    for key, catalog in frameworks.items():
        if not isinstance(key, str) or not re.fullmatch(r"[a-z0-9_]{1,64}", key):
            raise FrameworkMigrationRegistryError(
                f"invalid framework registry key: {key!r}"
            )
        _validate_catalog(key, catalog)
    edition_labels: Dict[str, str] = {}
    for key, catalog in frameworks.items():
        for edition_record in catalog["editions"].values():
            label = edition_record["label"]
            folded = label.casefold()
            prior_key = edition_labels.get(folded)
            if prior_key is not None and prior_key != key:
                raise FrameworkMigrationRegistryError(
                    "framework edition label values collide case-insensitively: "
                    f"frameworks.{prior_key} and frameworks.{key} both use {label!r}"
                )
            edition_labels[folded] = key
    return deepcopy(dict(root))


def _normalize_concept_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def resolve_framework_reference(
    raw_reference: Any,
    registry: Mapping[str, Any],
    *,
    framework_key: str = "owasp_llm",
) -> Optional[Dict[str, Any]]:
    """Resolve a current, bare, or superseded framework reference.

    ``None`` means that the text does not refer to the selected framework.
    Invalid and ambiguous framework references return structured metadata and
    intentionally omit a canonical target.
    """
    validated = validate_framework_migration_registry(registry)
    if framework_key == "cisco":
        if "cisco" not in validated["frameworks"]:
            return {
                "status": "invalid",
                "input": str(raw_reference or "").strip(),
                "frameworkKey": "cisco",
                "reasonCode": "registry_unavailable",
                "reason": "This index has no Cisco edition metadata; complete a successful framework sync.",
            }
        catalog = validated["frameworks"]["cisco"]
        if not _has_cisco_hierarchy(catalog):
            return {
                "status": "invalid",
                "input": str(raw_reference or "").strip(),
                "frameworkKey": "cisco",
                "reasonCode": "unsupported_catalog_profile",
                "reason": "This catalog supports ingestion and coverage, but its identifier profile is not supported by the Cisco reference resolver.",
            }
        return _resolve_cisco_reference(raw_reference, catalog)
    if framework_key != "owasp_llm":
        raise FrameworkMigrationRegistryError(
            f"reference resolution is not implemented for {framework_key!r}"
        )
    catalog = validated["frameworks"][framework_key]
    input_value = str(raw_reference or "").strip()
    if not input_value:
        return None

    active_items = catalog["activeItems"]
    migrations = catalog["migrations"]
    current_by_id = {item["id"].upper(): item for item in active_items}
    migration_by_old_id = {migration["from"]["id"].upper(): migration for migration in migrations}
    supported_editions = list(catalog["editions"])
    id_reference_pattern = (
        r"\bLLM(\d+)(?::([a-z0-9_-]+))?" r"(?=$|[\s/(),;\[\]{}&?]|\.(?=$|\s|LLM))"
    )
    id_tokens = list(re.finditer(id_reference_pattern, input_value, re.I))
    llm_id_like_starts = {
        match.start() for match in re.finditer(r"(?<![a-z0-9])LLM\d+", input_value, re.I)
    }
    contains_llm_id_like_text = bool(llm_id_like_starts)
    contains_recognized_framework_label = bool(
        re.search(
            r"\bOWASP\s+(?:LLM(?:\s+TOP\s+10)?|TOP\s+10\s+FOR\s+"
            r"(?:LLM|LARGE\s+LANGUAGE\s+MODEL)\s+APPLICATIONS)\b",
            input_value,
            re.I,
        )
    )

    context_input = re.sub(id_reference_pattern, " ", input_value, flags=re.I)
    edition_contexts = set()
    for pattern in (
        r"\bOWASP\s+LLM(?:\s+TOP\s+10)?\s*\(?\s*(20\d{2})(?![a-z0-9.]|\.\d)\s*\)?",
        r"\bOWASP\s+TOP\s+10\s+FOR\s+LLM\s+APPLICATIONS\s*\(?\s*(20\d{2})(?![a-z0-9.]|\.\d)\s*\)?",
        r"\bOWASP\s+TOP\s+10\s+FOR\s+LARGE\s+LANGUAGE\s+MODEL\s+APPLICATIONS\s*\(?\s*(20\d{2})(?![a-z0-9.]|\.\d)\s*\)?",
        r"\bOWASP\s*\(?\s*(20\d{2})(?![a-z0-9.]|\.\d)\s*\)?",
    ):
        edition_contexts.update(re.findall(pattern, context_input, flags=re.I))
    has_owasp_signal = bool(
        contains_recognized_framework_label or contains_llm_id_like_text or edition_contexts
    )
    edition_reference_pattern = r"(?<![a-z0-9])20\d{2}" r"(?=$|[\s/(),;\[\]{}&?]|\.(?=$|\s|LLM))"
    edition_tokens = list(re.finditer(edition_reference_pattern, context_input, re.I))
    if has_owasp_signal:
        edition_contexts.update(match.group(0) for match in edition_tokens)

    def invalid(reason: str) -> Dict[str, Any]:
        return {
            "status": "invalid",
            "input": input_value,
            "frameworkKey": catalog["stableKey"],
            "reason": reason,
            "supportedEditions": supported_editions,
            "canonicalIdFormat": catalog["responseContract"]["canonicalIdFormat"],
        }

    if re.search(r"\bLLM\d+:(?=\s|$|[^a-z0-9_-])", input_value, re.I):
        return invalid("The OWASP LLM edition suffix is empty or malformed.")
    parsed_id_starts = {match.start() for match in id_tokens}
    if llm_id_like_starts - parsed_id_starts:
        return invalid(
            "At least one OWASP LLM identifier is malformed or joined with an "
            "unsupported delimiter; use separate LLMdd, LLMdd:latest, or "
            "supported four-digit edition references."
        )
    if has_owasp_signal:
        parsed_edition_starts = {match.start() for match in edition_tokens}
        edition_like_starts = {
            match.start()
            for match in re.finditer(
                r"(?<![a-z0-9])20[a-z0-9][a-z0-9._-]*",
                context_input,
                re.I,
            )
        }
        if edition_like_starts - parsed_edition_starts:
            return invalid(
                "At least one OWASP LLM edition context is malformed or joined "
                "with an unsupported delimiter."
            )
    if len(edition_contexts) > 1:
        return invalid("The query contains conflicting OWASP LLM edition contexts.")
    context_edition = next(iter(edition_contexts), None)
    if context_edition and context_edition not in supported_editions:
        return invalid(f"OWASP LLM edition context {context_edition!r} is not supported.")
    has_standalone_latest = bool(re.search(r"\blatest\b", context_input, re.I))
    if has_standalone_latest and context_edition and context_edition != catalog["activeEdition"]:
        return invalid(
            "The latest OWASP LLM edition conflicts with a superseded "
            "surrounding edition context."
        )

    resolved_id_tokens = []
    for match in id_tokens:
        rank_text = match.group(1)
        if not re.fullmatch(r"(?:[1-9]|0[1-9]|10)", rank_text):
            return invalid(f"OWASP LLM rank {rank_text!r} has malformed zero padding or width.")
        rank = int(rank_text)
        suffix = match.group(2).lower() if match.group(2) else None
        if rank < 1 or rank > 10:
            return invalid(
                f"OWASP LLM rank {match.group(1)!r} is outside the supported Top 10 catalog."
            )
        if suffix and suffix != "latest" and suffix not in supported_editions:
            return invalid(f"OWASP LLM edition {match.group(2)!r} is not supported.")
        if context_edition and suffix == "latest" and context_edition != catalog["activeEdition"]:
            return invalid(
                "The latest OWASP LLM edition conflicts with a superseded surrounding edition context."
            )
        if context_edition and suffix and suffix != "latest" and suffix != context_edition:
            return invalid(
                "The explicit OWASP LLM identifier edition conflicts with the surrounding edition context."
            )

        bare_id = f"LLM{rank:02d}"
        effective_edition = (
            catalog["activeEdition"] if suffix == "latest" else (suffix or context_edition)
        )
        explicit_id = (
            f"{bare_id}:{effective_edition}".upper()
            if effective_edition and suffix != "latest"
            else None
        )
        source = None
        if explicit_id is None:
            current = current_by_id.get(f"{bare_id}:{catalog['activeEdition']}".upper())
            resolution_status = "fallback_latest"
            note = "A bare or latest OWASP LLM rank is resolved against the current edition."
        elif explicit_id in current_by_id:
            current = current_by_id[explicit_id]
            resolution_status = "canonical"
            note = "The query uses a current, versioned OWASP LLM identifier."
        elif explicit_id in migration_by_old_id:
            migration = migration_by_old_id[explicit_id]
            source = migration["from"]
            current = current_by_id[migration["to"]["id"].upper()]
            resolution_status = "migrated"
            note = migration["note"]
        else:
            return invalid(
                f"OWASP LLM identifier {explicit_id} is not declared in the current or superseded catalog."
            )
        if current is None:
            return invalid("The OWASP LLM current catalog is incomplete.")
        resolved_id_tokens.append(
            {
                "raw": match.group(0),
                "explicitId": explicit_id,
                "source": source,
                "current": current,
                "status": resolution_status,
                "note": note,
            }
        )

    input_name = _normalize_concept_name(context_input)
    framework_phrases = {
        catalog["activeLabel"],
        catalog["officialTitle"],
        *(edition["label"] for edition in catalog["editions"].values()),
        "OWASP Top 10 for Large Language Model Applications",
        "OWASP Top 10 for LLM Applications",
        "OWASP LLM Top 10",
        "OWASP LLM",
        "OWASP",
    }
    for phrase in sorted(
        (_normalize_concept_name(value) for value in framework_phrases),
        key=len,
        reverse=True,
    ):
        if phrase:
            input_name = re.sub(
                rf"(?:^|\s){re.escape(phrase)}(?=\s|$)",
                " ",
                input_name,
            )
    input_name = _normalize_concept_name(input_name)
    input_name = re.sub(r"(?:^|\s)20\d{2}(?=\s|$)", " ", input_name)
    input_name = re.sub(
        r"(?:^|\s)(?:latest|from|edition|version)(?=\s|$)",
        " ",
        input_name,
    )
    input_name = _normalize_concept_name(input_name)

    concept_definitions = []
    for item in active_items:
        concept_definitions.append(
            {
                "name": _normalize_concept_name(item["name"]),
                "current": item,
                "source": None,
                "kind": "current",
            }
        )
    for migration in migrations:
        concept_definitions.append(
            {
                "name": _normalize_concept_name(migration["from"]["name"]),
                "current": current_by_id[migration["to"]["id"].upper()],
                "source": migration["from"],
                "kind": "legacy",
                "note": migration["note"],
            }
        )

    matched_definitions = []
    covered_characters = [False] * len(input_name)
    for definition in sorted(
        concept_definitions,
        key=lambda value: len(value["name"]),
        reverse=True,
    ):
        name = definition["name"]
        if not name:
            continue
        pattern = re.compile(rf"(?:^|\s)({re.escape(name)})(?=\s|$)")
        for match in pattern.finditer(input_name):
            matched_definitions.append(definition)
            for index in range(match.start(1), match.end(1)):
                covered_characters[index] = True

    uncovered_name = _normalize_concept_name(
        "".join(
            " " if covered_characters[index] else character
            for index, character in enumerate(input_name)
        )
    )
    uncovered_tokens = uncovered_name.split() if uncovered_name else []
    concept_text_is_fully_covered = all(token in {"and", "or"} for token in uncovered_tokens)
    accepted_definitions = matched_definitions if concept_text_is_fully_covered else []

    current_name_targets: Dict[str, Dict[str, Any]] = {}
    for definition in accepted_definitions:
        if definition["kind"] == "current":
            current_name_targets[definition["current"]["id"]] = {
                "current": definition["current"],
                "source": None,
                "kind": "current",
            }
    legacy_name_targets: Dict[str, Dict[str, Any]] = {}
    legacy_name_targets_by_edition: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for definition in accepted_definitions:
        if definition["kind"] == "legacy":
            current = definition["current"]
            target = {
                "current": current,
                "source": definition["source"],
                "kind": "legacy",
                "note": definition["note"],
            }
            legacy_name_targets[current["id"]] = target
            legacy_name_targets_by_edition.setdefault(definition["source"]["edition"], {})[
                current["id"]
            ] = target

    if context_edition == catalog["activeEdition"]:
        if not current_name_targets and legacy_name_targets:
            return invalid(
                "The recognized risk name belongs to a superseded OWASP LLM edition, not the declared current edition."
            )
        name_targets = current_name_targets
    elif context_edition:
        name_targets = legacy_name_targets_by_edition.get(context_edition, {})
        if not name_targets and current_name_targets:
            return invalid(
                f"The recognized risk name is not declared in the OWASP LLM {context_edition} edition."
            )
    else:
        # Preserve both current and superseded concept names. Current entries
        # intentionally win only when the same canonical ID appears in both;
        # a different legacy-only concept must remain visible as ambiguity.
        name_targets = {**legacy_name_targets, **current_name_targets}

    id_target_ids = {token["current"]["id"] for token in resolved_id_tokens}
    name_target_ids = set(name_targets)
    if len(id_target_ids) > 1 or len(name_target_ids) > 1:
        candidate_ids = id_target_ids | name_target_ids
        candidates = []
        for identifier in sorted(
            candidate_ids,
            key=lambda candidate: (
                current_by_id[candidate.upper()]["rank"],
                candidate,
            ),
        ):
            item = current_by_id.get(identifier.upper())
            if item:
                candidates.append(
                    {
                        "framework": catalog["activeLabel"],
                        "edition": catalog["activeEdition"],
                        "id": item["id"],
                        "name": item["name"],
                        "label": f"{item['id']} {item['name']}",
                    }
                )
        return {
            "status": "ambiguous",
            "input": input_value,
            "frameworkKey": catalog["stableKey"],
            "candidates": candidates,
            "reason": (
                "The query contains multiple OWASP LLM identifiers or risk names "
                "that resolve to different current concepts. Specify one risk concept; "
                "no rank is guessed."
            ),
        }

    id_token = resolved_id_tokens[0] if resolved_id_tokens else None
    name_target = next(iter(name_targets.values()), None)
    recognized_name_target = name_target["current"] if name_target else None
    id_name_conflict = bool(
        id_token
        and recognized_name_target
        and recognized_name_target["id"] != id_token["current"]["id"]
    )

    source = None
    if id_name_conflict:
        current = recognized_name_target
        source = name_target["source"]
        status = "normalized"
        reason = (
            "The identifier/name conflict resolves by risk concept: the identifier "
            f"points to {id_token['current']['id']}, while the recognized name "
            f"identifies {recognized_name_target['id']}; the named concept's current "
            "canonical successor is returned."
        )
    elif id_token and id_token["explicitId"]:
        status = id_token["status"]
        source = id_token["source"]
        current = id_token["current"]
        reason = id_token["note"]
    elif id_token and name_target:
        current = name_target["current"]
        status = "migrated" if name_target["kind"] == "legacy" else "normalized"
        source = name_target["source"]
        reason = (
            "The unversioned identifier and recognized risk name resolve to the current canonical item."
            if id_token["current"]["id"] == name_target["current"]["id"]
            else (
                "The unversioned rank and risk name conflict; the recognized risk "
                f"concept resolves to {name_target['current']['id']} rather than "
                "carrying the old rank forward."
            )
        )
    elif id_token:
        status = id_token["status"]
        source = id_token["source"]
        current = id_token["current"]
        reason = id_token["note"]
    elif name_target:
        source = name_target["source"]
        current = name_target["current"]
        status = "migrated" if name_target["kind"] == "legacy" else "normalized"
        reason = name_target.get("note") or (
            "The recognized risk name resolves to the current canonical item."
        )
    else:
        if contains_recognized_framework_label:
            return invalid(
                "The query names the OWASP LLM framework but does not identify one recognized risk concept."
            )
        return None

    canonical = {
        "frameworkKey": catalog["stableKey"],
        "framework": catalog["activeLabel"],
        "edition": catalog["activeEdition"],
        "id": current["id"],
        "name": current["name"],
        "label": f"{current['id']} {current['name']}",
    }
    result: Dict[str, Any] = {
        "status": status,
        "input": input_value,
        "canonical": canonical,
        "reason": reason,
    }
    if id_name_conflict:
        result["inputNameConflict"] = {
            "normalizedInputName": input_name,
            "identifierTarget": (f"{id_token['current']['id']} {id_token['current']['name']}"),
            "recognizedNameTarget": (
                f"{recognized_name_target['id']} {recognized_name_target['name']}"
            ),
            "resolvedBy": "recognized-risk-name",
        }
    if len(resolved_id_tokens) > 1:
        result["coResolvedReferences"] = [token["raw"] for token in resolved_id_tokens]
    if source:
        result["migratedFrom"] = {
            **source,
            "label": f"{source['id']} {source['name']}",
        }
    return result


def canonical_lookup_id(resolution: Optional[Mapping[str, Any]]) -> Optional[str]:
    """Return the bare reverse-index key for one successful resolution."""
    if not isinstance(resolution, Mapping):
        return None
    canonical = resolution.get("canonical")
    if not isinstance(canonical, Mapping):
        return None
    identifier = canonical.get("id")
    if not isinstance(identifier, str):
        return None
    match = re.fullmatch(r"(LLM\d{2}):[0-9]{4}", identifier, flags=re.I)
    if canonical.get("frameworkKey") == "cisco":
        return identifier.upper()
    return match.group(1).upper() if match else identifier


CISCO_ID_FORMAT = "AITech-N.N or AISubtech-N.N.N"


def _has_cisco_hierarchy(catalog: Mapping[str, Any]) -> bool:
    """Recognize hierarchy fields as well as the declared format to prevent downgrade."""
    response = catalog.get("responseContract")
    if isinstance(response, Mapping) and response.get("canonicalIdFormat") == CISCO_ID_FORMAT:
        return True
    if "historicalItems" in catalog:
        return True
    return any(
        isinstance(item, Mapping)
        and (
            "parentObjective" in item
            or "parentTechnique" in item
            or re.match(r"AI(?:Subtech|Tech)-\d+\.", str(item.get("id", "")), re.I)
        )
        for item in catalog.get("activeItems", [])
    )


def _edition_aliases(edition: str) -> set[str]:
    """Only zero suffixes may be omitted: 2.1 never aliases a 2.1.1 release."""
    aliases = {edition.lower()}
    parts = edition.lower().split(".")
    while len(parts) > 1 and parts[-1] == "0":
        parts.pop()
        aliases.add(".".join(parts))
    return aliases


def _validate_cisco_catalog(raw_catalog: Any) -> None:
    """Validate the hierarchy contract; the trusted registry owns release values."""
    path = "frameworks.cisco"
    catalog = _mapping(raw_catalog, path)
    active_edition = catalog["activeEdition"]
    if not re.fullmatch(r"[1-9]\d*(?:\.(?:0|[1-9]\d*)){0,2}", active_edition):
        raise FrameworkMigrationRegistryError("Cisco hierarchy edition must be a numeric release")
    if int(active_edition.split(".")[0]) < 2:
        raise FrameworkMigrationRegistryError("The legacy Cisco hierarchy is not served")
    _text(catalog.get("displayLabel"), path + ".displayLabel", maximum=256)
    _https_url(
        catalog.get("sourceUrl"), path + ".sourceUrl", required_host="learn-cloudsecurity.cisco.com"
    )
    editions = _mapping(catalog.get("editions"), path + ".editions")
    seen_aliases = set()
    for edition in editions:
        if not re.fullmatch(r"[1-9]\d*(?:\.(?:0|[1-9]\d*)){0,2}", edition):
            raise FrameworkMigrationRegistryError("Cisco hierarchy edition is malformed")
        aliases = _edition_aliases(edition)
        if aliases & seen_aliases:
            raise FrameworkMigrationRegistryError("Cisco edition aliases collide")
        seen_aliases.update(aliases)
    response = _mapping(catalog.get("responseContract"), path + ".responseContract")
    if response.get("canonicalIdFormat") != CISCO_ID_FORMAT:
        raise FrameworkMigrationRegistryError("Cisco resolution response contract differs")
    items = _list(catalog.get("activeItems"), path + ".activeItems")
    active = {}
    pattern = r"(?:AITech-[1-9]\d*\.[1-9]\d*|AISubtech-[1-9]\d*\.[1-9]\d*\.[1-9]\d*)"
    for item in items:
        item = _mapping(item, path + ".activeItems entry")
        identifier = _text(item.get("id"), path + ".activeItems.id", maximum=128)
        if re.fullmatch(pattern, identifier) is None or identifier in active:
            raise FrameworkMigrationRegistryError(
                "Cisco active identifier is malformed or duplicated"
            )
        _text(item.get("name"), path + ".activeItems.name", maximum=256)
        if identifier.startswith("AITech-"):
            if not re.fullmatch(r"OB-\d{3}", str(item.get("parentObjective", ""))):
                raise FrameworkMigrationRegistryError("Cisco technique objective is malformed")
        else:
            _text(item.get("parentTechnique"), path + ".activeItems.parentTechnique", maximum=128)
        active[identifier] = item
    for item in items:
        if item["id"].startswith("AISubtech-"):
            # Hierarchy is publisher data, not inferred from reused numeric IDs.
            parent = item["parentTechnique"]
            if not parent.startswith("AITech-") or parent not in active:
                raise FrameworkMigrationRegistryError(
                    "Cisco subtechnique technique parent is absent"
                )
    historical = _list(catalog.get("historicalItems"), path + ".historicalItems")
    if len(historical) > 1000:
        raise FrameworkMigrationRegistryError("Cisco historical conflict metadata is excessive")
    seen = set()
    for item in historical:
        item = _mapping(item, path + ".historicalItems entry")
        identifier = _text(item.get("id"), path + ".historicalItems.id", maximum=128)
        name = _text(item.get("name"), path + ".historicalItems.name", maximum=256)
        edition = _text(item.get("edition"), path + ".historicalItems.edition", maximum=32)
        if (
            set(item) != {"edition", "id", "name", "status"}
            or edition not in editions
            or editions[edition]["status"] != "superseded"
            or re.fullmatch(pattern, identifier) is None
            or (edition, identifier) in seen
            or item["status"] not in {"retired", "name-changed"}
            or (item["status"] == "retired" and identifier in active)
            or (
                item["status"] == "name-changed"
                and (identifier not in active or active[identifier]["name"] == name)
            )
        ):
            raise FrameworkMigrationRegistryError(
                "Cisco historical metadata conflicts with current catalog"
            )
        seen.add((edition, identifier))
    if catalog.get("migrations") != []:
        raise FrameworkMigrationRegistryError("Cisco must not declare automatic legacy successors")
    artifact = _mapping(catalog.get("sourceArtifact"), path + ".sourceArtifact")
    if (
        artifact.get("release") != "v" + active_edition
        or re.fullmatch(r"[0-9a-fA-F]{64}", str(artifact.get("sha256", ""))) is None
    ):
        raise FrameworkMigrationRegistryError("Cisco source release/digest differs")
    for field in ("publicationDate", "retrievedDate"):
        try:
            date.fromisoformat(_text(artifact.get(field), path + ".sourceArtifact." + field))
        except ValueError as error:
            raise FrameworkMigrationRegistryError("Cisco source date is invalid") from error
    _https_url(
        artifact.get("announcementUrl"),
        path + ".sourceArtifact.announcementUrl",
        required_host="blogs.cisco.com",
    )
    license_record = _mapping(catalog.get("sourceLicense"), path + ".sourceLicense")
    for field in ("attribution", "scope", "changesMade"):
        _text(license_record.get(field), path + ".sourceLicense." + field)
    policy = _mapping(catalog.get("resolutionPolicy"), path + ".resolutionPolicy")
    for field in (
        "bareId",
        "explicitLegacyEdition",
        "retiredId",
        "idNameConflict",
        "multipleReferences",
    ):
        _text(policy.get(field), path + ".resolutionPolicy." + field)
    if (
        policy.get("mappingCarryForward")
        != "never automatic; requires target-edition semantic review"
    ):
        raise FrameworkMigrationRegistryError("Cisco mapping carry-forward policy differs")


def is_cisco_reference(raw_reference: Any, catalog: Any = None) -> bool:
    """Recognize current catalog names without assuming a permanent vendor label."""
    value = str(raw_reference or "").strip()
    if re.search(r"\b(?:Cisco|AI(?:Subtech|Tech))", value, re.I):
        return True
    if not isinstance(catalog, Mapping):
        return False
    return any(
        isinstance(label, str)
        and label.strip()
        and re.search(r"(?<!\w)" + re.escape(label) + r"(?!\w)", value, re.I)
        for label in (
            catalog.get("activeLabel"),
            catalog.get("officialTitle"),
            catalog.get("displayLabel"),
        )
    )


def _resolve_cisco_reference(
    raw_reference: Any, catalog: Mapping[str, Any]
) -> Optional[Dict[str, Any]]:
    value = str(raw_reference or "").strip()
    if not value or not is_cisco_reference(value, catalog):
        return None
    base = {"input": value, "frameworkKey": "cisco", "activeEdition": catalog["activeEdition"]}
    active_edition = catalog["activeEdition"]

    def invalid(code, reason, **extra):
        return {"status": "invalid", **base, "reasonCode": code, "reason": reason, **extra}

    if re.search(r"\b(?:LLM\d|AML\.T|ASI\d|NISTAML\.)", value, re.I):
        return invalid("mixed_frameworks", "Submit one framework reference per query.")
    token_pattern = r"\bAI(?:Subtech|Tech)-[^\s,;()[\]{}&/?]+"
    tokens = list(re.finditer(token_pattern, value, re.I))
    if len(tokens) != len(re.findall(r"\bAI(?:Subtech|Tech)", value, re.I)):
        return invalid(
            "malformed_identifier", "Use a complete AITech-N.N or AISubtech-N.N.N identifier."
        )
    editions, identifiers = [], []
    for token in tokens:
        match = re.fullmatch(
            r"(AITech|AISubtech)-([1-9]\d*\.[1-9]\d*(?:\.[1-9]\d*)?)(?::([^:]+))?",
            token.group(),
            re.I,
        )
        if not match or len(match[2].split(".")) != (3 if match[1].lower() == "aisubtech" else 2):
            return invalid(
                "malformed_identifier", "Cisco identifier or edition suffix is malformed."
            )
        identifiers.append(
            ("AISubtech-" if match[1].lower() == "aisubtech" else "AITech-") + match[2]
        )
        if match[3] is not None:
            editions.append(match[3].lower())
    remainder = re.sub(token_pattern, " ", value, flags=re.I)

    def take_edition(match):
        editions.append(match[1].lower())
        return " "

    remainder = re.sub(
        r"\b(?:version\s+|edition\s+|v(?=\d|latest|current|next))([^\s,;()[\]{}&/?]+)",
        take_edition,
        remainder,
        flags=re.I,
    )
    normalized_editions = [re.sub(r"^v", "", item) for item in editions]
    active_aliases = _edition_aliases(active_edition) | {"latest", "current"}
    legacy_aliases = {
        alias
        for edition in catalog["editions"]
        if edition != active_edition
        for alias in _edition_aliases(edition)
    } | {"1", "1.0", "1.0.0"}
    if any(item not in active_aliases for item in normalized_editions):
        legacy = any(item in legacy_aliases for item in normalized_editions)
        return invalid(
            "unsupported_edition" if legacy else "malformed_or_unsupported_edition",
            f"Only the active Cisco edition {active_edition} is served. Superseded references are not migrated automatically.",
            requestedEditions=normalized_editions,
            supportedEditions=[catalog["activeEdition"]],
        )
    # Strip exact declared labels before the familiar Cisco prefix. Labels are
    # metadata aliases, not evidence of equivalence between old and new items.
    for label in sorted(
        {catalog["activeLabel"], catalog["displayLabel"], catalog["officialTitle"]},
        key=len,
        reverse=True,
    ):
        remainder = re.sub(r"(?<!\w)" + re.escape(label) + r"(?!\w)", " ", remainder, flags=re.I)
    remainder = re.sub(
        r"\bCisco(?:\s+(?:Integrated\s+)?AI\s+Security(?:\s*(?:and|&)\s*Safety)?(?:\s+Framework)?)?",
        " ",
        remainder,
        flags=re.I,
    )
    remainder = re.sub(r"^\s*[-:,;()[\]{}]+|[-:,;()[\]{}]+\s*$", " ", remainder).strip()
    name = _normalize_concept_name(remainder)
    by_id = {item["id"]: item for item in catalog["activeItems"]}
    identifiers = list(dict.fromkeys(identifiers))

    def canonical(item):
        return {
            "frameworkKey": "cisco",
            "framework": catalog["activeLabel"],
            "displayFramework": catalog["displayLabel"],
            "edition": catalog["activeEdition"],
            "id": item["id"],
            "name": item["name"],
            "label": item["id"] + " " + item["name"],
        }

    if len(identifiers) > 1:
        return {
            "status": "ambiguous",
            **base,
            "reasonCode": "multiple_identifiers",
            "reason": "Submit one Cisco technique or subtechnique per query.",
            "candidates": [canonical(by_id[item]) for item in identifiers if item in by_id],
            "requestedIds": identifiers,
        }
    named = (
        [item for item in catalog["activeItems"] if _normalize_concept_name(item["name"]) == name]
        if name
        else []
    )
    historical = (
        [
            item
            for item in catalog["historicalItems"]
            if _normalize_concept_name(item["name"]) == name
        ]
        if name
        else []
    )
    if not identifiers:
        if len(named) > 1:
            return {
                "status": "ambiguous",
                **base,
                "reasonCode": "multiple_name_matches",
                "reason": "This Cisco name is not unique; use an exact current identifier.",
                "candidates": [canonical(item) for item in named],
            }
        if len(named) == 1:
            return {
                "status": "normalized",
                **base,
                "canonical": canonical(named[0]),
                "reason": f"The exact name resolves within the active Cisco edition {active_edition}.",
            }
        return invalid(
            "legacy_name_unsupported" if historical else "unrecognized_reference",
            "Use an exact current Cisco identifier or canonical name; historical names are not migrated automatically.",
            **({"historicalReferences": historical} if historical else {}),
        )
    identifier = identifiers[0]
    if identifier not in by_id:
        retired = [
            item
            for item in catalog["historicalItems"]
            if item["id"] == identifier and item["status"] == "retired"
        ]
        return invalid(
            "retired_identifier" if retired else "unknown_identifier",
            f"This identifier is not active in Cisco edition {active_edition}. No successor is inferred.",
            requestedId=identifier,
            **({"historicalReferences": retired} if retired else {}),
        )
    current = by_id[identifier]
    if name and _normalize_concept_name(current["name"]) != name:
        return invalid(
            "id_name_conflict",
            "The supplied name does not match the current identifier; neither silently overrides the other.",
            requestedId=identifier,
            identifierCandidate=canonical(current),
            namedCandidates=[canonical(item) for item in named],
            **({"historicalReferences": historical} if historical else {}),
        )
    return {
        "status": "canonical",
        **base,
        "canonical": canonical(current),
        "reason": f"The identifier resolves against Cisco edition {active_edition} only; superseded meanings and mappings are not carried forward.",
        **(
            {"reusedIdentifier": True}
            if any(item["id"] == identifier for item in catalog["historicalItems"])
            else {}
        ),
    }
