from __future__ import annotations

import csv
import io
import re
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from bs4 import BeautifulSoup, Comment, Doctype

from app.validators import ValidationResult


V3_VALIDATOR_VERSION = "3.0.0"
USER_FACING_ATTRIBUTES = ("alt", "title", "placeholder", "aria-label")
PROTECTED_FACT_PATTERNS: Sequence[Tuple[str, str]] = (
    ("number", r"(?<![\w-])\d+(?:[,.]\d+)*(?:\s?(?:lb|lbs|kg|ft|feet|in|inch|inches|mi|miles|%))?(?![\w-])"),
    ("currency", r"(?:\$|USD\s*)\d+(?:[,.]\d+)*"),
    ("email", r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"),
    ("phone", r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\d)"),
    ("date", r"\b(?:19|20)\d{2}[-/]\d{1,2}[-/]\d{1,2}\b"),
)
KNOWN_SITE_ENTITIES = {
    "nationwide transport services",
    "heavy equipment transport",
    "heavy haulers",
    "tractor transport",
    "auto transport",
    "container transport",
}
PROMPT_INJECTION_MARKERS = (
    "ignore previous instructions",
    "ignore all previous",
    "system prompt",
    "developer message",
    "reveal your instructions",
    "act as system",
)


def _issue(code: str, severity: str, message: str, **details: Any) -> Dict[str, Any]:
    issue: Dict[str, Any] = {"code": code, "severity": severity, "message": message}
    if details:
        issue["details"] = details
    return issue


def _result(issues: List[Dict[str, Any]], metrics: Dict[str, Any]) -> ValidationResult:
    blocking = any(issue.get("severity") == "error" for issue in issues)
    status = "FAIL" if blocking else "REVIEW" if issues else "PASS"
    return ValidationResult(status=status, blocking=blocking, issues=issues, metrics=metrics)


def _eligible_strings(html: str) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html or "", "lxml")
    for element in soup(["script", "style", "noscript", "template", "svg"]):
        element.decompose()
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()
    strings: List[Dict[str, str]] = []
    for node in soup.find_all(string=True):
        if isinstance(node, (Comment, Doctype)):
            continue
        value = " ".join(str(node).split())
        if value:
            strings.append({"location": node.parent.name if node.parent else "text", "value": value})
    for tag in soup.find_all(True):
        for attribute in USER_FACING_ATTRIBUTES:
            value = " ".join(str(tag.get(attribute, "")).split())
            if value:
                strings.append({"location": f"{tag.name}@{attribute}", "value": value})
        if tag.name == "meta" and str(tag.get("name", "")).lower() in {"description", "twitter:description"}:
            value = " ".join(str(tag.get("content", "")).split())
            if value:
                strings.append({"location": "meta@content", "value": value})
    return strings


def validate_coverage(source_html: str, target_html: str) -> ValidationResult:
    """Validate strict-mirror eligible-string inventory and detect unchanged source strings."""
    issues: List[Dict[str, Any]] = []
    source_strings = _eligible_strings(source_html)
    target_strings = _eligible_strings(target_html)
    if not source_strings or not target_strings:
        issues.append(_issue(
            "COVERAGE_EMPTY_INPUT", "error",
            "Both source and target must contain eligible user-facing strings.",
        ))
    source_count, target_count = len(source_strings), len(target_strings)
    if source_count != target_count:
        issues.append(_issue(
            "ELIGIBLE_STRING_COUNT_MISMATCH", "error",
            "Strict-mirror source and target eligible-string counts differ.",
            source_count=source_count, target_count=target_count,
        ))
    unchanged: List[Dict[str, Any]] = []
    for index, (source, target) in enumerate(zip(source_strings, target_strings)):
        source_value, target_value = source["value"].casefold(), target["value"].casefold()
        contains_letters = bool(re.search(r"[a-z]", source_value))
        protected_only = not contains_letters or source_value in KNOWN_SITE_ENTITIES
        if contains_letters and not protected_only and source_value == target_value:
            unchanged.append({"index": index, "location": source["location"], "value": source["value"][:160]})
    if unchanged:
        issues.append(_issue(
            "UNCHANGED_SOURCE_STRINGS", "error",
            "Eligible source strings remain unchanged in the Spanish target.",
            occurrences=unchanged[:30], total=len(unchanged),
        ))
    translated = max(0, min(source_count, target_count) - len(unchanged))
    return _result(issues, {
        "validator": "coverage", "version": V3_VALIDATOR_VERSION,
        "source_eligible_strings": source_count,
        "target_eligible_strings": target_count,
        "translated_strings": translated,
        "coverage_percent": round((translated / source_count) * 100, 2) if source_count else 0,
    })


def _facts(content: str) -> Dict[str, Counter]:
    facts: Dict[str, Counter] = {}
    for name, pattern in PROTECTED_FACT_PATTERNS:
        facts[name] = Counter(re.findall(pattern, content or "", flags=re.I))
    lowered = (content or "").casefold()
    facts["site_entity"] = Counter(entity for entity in KNOWN_SITE_ENTITIES if entity in lowered)
    return facts


def validate_facts_parity(source_content: str, target_content: str) -> ValidationResult:
    """Require numerical facts, contact details, dates, and site entities to remain unchanged."""
    issues: List[Dict[str, Any]] = []
    if not (source_content or "").strip() or not (target_content or "").strip():
        issues.append(_issue("FACTS_EMPTY_INPUT", "error", "Both source and target content are required."))
        return _result(issues, {"validator": "facts_parity", "version": V3_VALIDATOR_VERSION})
    source, target = _facts(source_content), _facts(target_content)
    checked = 0
    for fact_type in source:
        checked += sum(source[fact_type].values())
        missing = dict(source[fact_type] - target[fact_type])
        extra = dict(target[fact_type] - source[fact_type])
        if missing or extra:
            issues.append(_issue(
                "FACT_PARITY_MISMATCH", "error",
                f"Protected {fact_type} values differ between source and target.",
                fact_type=fact_type, missing=missing, extra=extra,
            ))
    return _result(issues, {
        "validator": "facts_parity", "version": V3_VALIDATOR_VERSION,
        "facts_checked": checked, "fact_types_checked": sorted(source),
    })


def validate_site_isolation(source_content: str, target_content: str) -> ValidationResult:
    """Block known NTS site entities introduced by the target but absent from the source."""
    issues: List[Dict[str, Any]] = []
    source_lower, target_lower = (source_content or "").casefold(), (target_content or "").casefold()
    source_entities = {entity for entity in KNOWN_SITE_ENTITIES if entity in source_lower}
    target_entities = {entity for entity in KNOWN_SITE_ENTITIES if entity in target_lower}
    leaked = sorted(target_entities - source_entities)
    if leaked:
        issues.append(_issue(
            "CROSS_SITE_ENTITY_LEAKAGE", "error",
            "The target introduces NTS site or brand entities not supported by the source.",
            introduced_entities=leaked,
        ))
    return _result(issues, {
        "validator": "site_isolation", "version": V3_VALIDATOR_VERSION,
        "source_entities": sorted(source_entities), "target_entities": sorted(target_entities),
    })


def validate_prompt_injection_content(source_content: str) -> ValidationResult:
    """Identify instruction-like text so the orchestrator can treat it strictly as source data."""
    lowered = (source_content or "").casefold()
    matches = sorted(marker for marker in PROMPT_INJECTION_MARKERS if marker in lowered)
    issues = []
    if matches:
        issues.append(_issue(
            "SOURCE_INSTRUCTION_LIKE_TEXT", "warning",
            "Instruction-like text appears inside source content and must be treated as data, not as instructions.",
            markers=matches,
        ))
    return _result(issues, {
        "validator": "prompt_injection_content", "version": V3_VALIDATOR_VERSION,
        "markers_found": len(matches), "treatment": "data_only",
    })


def _is_image_header(header: str) -> bool:
    normalized = header.casefold().strip()
    return bool(re.search(r"(^|_)(?:image|img)(?:_|$)", normalized)) and "alt" not in normalized


def _is_alt_header(header: str) -> bool:
    return bool(re.search(r"(^|_)alt(?:_|$)", header.casefold().strip()))


def _group_key(header: str) -> Optional[str]:
    match = re.fullmatch(r"body_(?:p|list)_(\d+(?:_\d+)*)", header.casefold().strip())
    return match.group(1) if match else None


def validate_csv_contract(
    csv_content: str,
    required_columns: Optional[Iterable[str]] = None,
) -> ValidationResult:
    """Validate deterministic pSEO CSV grouping plus mandatory image→alt adjacency."""
    issues: List[Dict[str, Any]] = []
    metrics: Dict[str, Any] = {"validator": "csv_contract", "version": V3_VALIDATOR_VERSION}
    if not (csv_content or "").strip():
        issues.append(_issue("CSV_EMPTY_INPUT", "error", "CSV content is required."))
        return _result(issues, metrics)
    try:
        reader = csv.DictReader(io.StringIO(csv_content))
        headers = list(reader.fieldnames or [])
        rows = list(reader)
    except (csv.Error, UnicodeError) as exc:
        issues.append(_issue("CSV_PARSE_ERROR", "error", "CSV content could not be parsed.", error=str(exc)))
        return _result(issues, metrics)
    metrics.update({"columns": len(headers), "rows": len(rows), "headers": headers})
    if not headers:
        issues.append(_issue("CSV_HEADERS_MISSING", "error", "CSV headers are required."))
        return _result(issues, metrics)
    duplicates = sorted(header for header, count in Counter(headers).items() if count > 1)
    if duplicates:
        issues.append(_issue("CSV_DUPLICATE_HEADERS", "error", "CSV headers must be unique.", headers=duplicates))
    missing_required = sorted(set(required_columns or []) - set(headers))
    if missing_required:
        issues.append(_issue("CSV_REQUIRED_COLUMNS_MISSING", "error", "Mandatory CSV columns are missing.", columns=missing_required))
    for index, header in enumerate(headers):
        if _is_image_header(header):
            next_header = headers[index + 1] if index + 1 < len(headers) else None
            if not next_header or not _is_alt_header(next_header):
                issues.append(_issue(
                    "CSV_IMAGE_ALT_ADJACENCY", "error",
                    "Every image column must be followed immediately by its own alt column.",
                    image_column=header, following_column=next_header,
                ))
    grouped: Dict[str, List[str]] = {}
    for header in headers:
        key = _group_key(header)
        if key:
            grouped.setdefault(key, []).append(header)
    split_groups = {key: values for key, values in grouped.items() if len(values) > 1}
    if split_groups:
        issues.append(_issue(
            "CSV_SECTION_GROUP_SPLIT", "error",
            "A paragraph and its directly related list must remain in one logical content column.",
            groups=split_groups,
        ))
    target_header = next((header for header in headers if header.casefold() in {"target_url", "spanish_url", "canonical_url"}), None)
    if target_header:
        targets = [row.get(target_header, "").strip() for row in rows if row.get(target_header, "").strip()]
        duplicate_targets = sorted(target for target, count in Counter(targets).items() if count > 1)
        if duplicate_targets:
            issues.append(_issue("CSV_DUPLICATE_TARGET_URL", "error", "Target URLs must be unique.", urls=duplicate_targets))
    image_columns = [header for header in headers if _is_image_header(header)]
    for row_index, row in enumerate(rows, start=2):
        for image_header in image_columns:
            image_index = headers.index(image_header)
            alt_header = headers[image_index + 1] if image_index + 1 < len(headers) else None
            image_value = (row.get(image_header) or "").strip()
            alt_value = (row.get(alt_header) or "").strip() if alt_header and _is_alt_header(alt_header) else ""
            if image_value and not alt_value:
                issues.append(_issue(
                    "CSV_IMAGE_ALT_VALUE_MISSING", "error",
                    "Every populated image value requires a populated adjacent alt value.",
                    row=row_index, image_column=image_header, alt_column=alt_header,
                ))
    metrics["image_columns"] = image_columns
    metrics["image_alt_pairs"] = sum(1 for index, header in enumerate(headers[:-1]) if _is_image_header(header) and _is_alt_header(headers[index + 1]))
    return _result(issues, metrics)
