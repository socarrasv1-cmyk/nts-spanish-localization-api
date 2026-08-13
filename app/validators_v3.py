from __future__ import annotations

import csv
import io
import re
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from bs4 import BeautifulSoup, Comment, Doctype

from app.validators import ValidationResult


V3_VALIDATOR_VERSION = "3.0.0"
CSV_BASE_REQUIRED_COLUMNS = ("site_id", "source_url", "slug", "target_url")
CSV_HEADER_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
CSV_SECTION_PATTERN = re.compile(r"^body_section_(\d+(?:_\d+)*)$")
CSV_TRANSLATABLE_PATTERN = re.compile(
    r"^(?:title|meta_title|meta_description|h[1-6]|quick_answer|body_section_\d+(?:_\d+)*|"
    r"alt_\d+|faq(?:_\d+)?(?:_(?:question|answer))?|cta(?:_\d+)?(?:_(?:label|text))?)$"
)
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


def _image_key(header: str) -> Optional[str]:
    match = re.fullmatch(r"(?:image|img)_(\d+)", header.casefold().strip())
    return match.group(1) if match else None


def _alt_key(header: str) -> Optional[str]:
    match = re.fullmatch(r"alt_(\d+)", header.casefold().strip())
    return match.group(1) if match else None


def _semantic_number(value: str) -> Tuple[int, ...]:
    return tuple(int(part) for part in value.split("_"))


def _csv_rows(csv_content: str) -> Tuple[List[str], List[List[str]]]:
    return (
        lambda parsed: (parsed[0] if parsed else [], parsed[1:] if parsed else [])
    )(list(csv.reader(io.StringIO(csv_content, newline=""), strict=True)))


def csv_translatable_text(csv_content: str) -> str:
    """Return only user-facing CSV values, excluding headers, URLs, IDs, and media paths."""
    try:
        headers, raw_rows = _csv_rows(csv_content)
    except (csv.Error, UnicodeError):
        return ""
    eligible_indexes = [
        index for index, header in enumerate(headers)
        if CSV_TRANSLATABLE_PATTERN.fullmatch(header.casefold().strip())
    ]
    return "\n".join(
        row[index].strip()
        for row in raw_rows
        for index in eligible_indexes
        if index < len(row) and row[index].strip()
    )


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
    if csv_content.startswith("\ufeff"):
        issues.append(_issue("CSV_UTF8_BOM_FORBIDDEN", "error", "CSV must use UTF-8 without a byte-order mark."))
    without_crlf = csv_content.replace("\r\n", "")
    has_crlf = "\r\n" in csv_content
    has_lf = "\n" in without_crlf
    has_bare_cr = "\r" in without_crlf
    if (has_crlf and has_lf) or has_bare_cr:
        issues.append(_issue("CSV_MIXED_LINE_ENDINGS", "error", "CSV must use one consistent line-ending convention."))
    try:
        headers, raw_rows = _csv_rows(csv_content)
    except (csv.Error, UnicodeError) as exc:
        issues.append(_issue("CSV_PARSE_ERROR", "error", "CSV content could not be parsed.", error=str(exc)))
        return _result(issues, metrics)
    metrics.update({"columns": len(headers), "rows": len(raw_rows), "headers": headers})
    if not headers:
        issues.append(_issue("CSV_HEADERS_MISSING", "error", "CSV headers are required."))
        return _result(issues, metrics)
    empty_headers = [index + 1 for index, header in enumerate(headers) if not header.strip()]
    if empty_headers:
        issues.append(_issue("CSV_EMPTY_HEADER", "error", "CSV column names cannot be empty.", columns=empty_headers))
    invalid_headers = [header for header in headers if header and not CSV_HEADER_PATTERN.fullmatch(header)]
    if invalid_headers:
        issues.append(_issue(
            "CSV_HEADER_FORMAT_INVALID", "error",
            "CSV headers must be lowercase snake_case identifiers.", headers=invalid_headers,
        ))
    duplicates = sorted(header for header, count in Counter(headers).items() if count > 1)
    if duplicates:
        issues.append(_issue("CSV_DUPLICATE_HEADERS", "error", "CSV headers must be unique.", headers=duplicates))
    mandatory_columns = set(CSV_BASE_REQUIRED_COLUMNS) | set(required_columns or [])
    missing_required = sorted(mandatory_columns - set(headers))
    if missing_required:
        issues.append(_issue("CSV_REQUIRED_COLUMNS_MISSING", "error", "Mandatory CSV columns are missing.", columns=missing_required))
    row_width_errors = [
        {"row": index, "expected": len(headers), "actual": len(row)}
        for index, row in enumerate(raw_rows, start=2) if len(row) != len(headers)
    ]
    if row_width_errors:
        issues.append(_issue(
            "CSV_ROW_WIDTH_MISMATCH", "error",
            "Every CSV row must contain exactly one value for every header.", rows=row_width_errors[:30],
        ))
    blank_rows = [index for index, row in enumerate(raw_rows, start=2) if not any(value.strip() for value in row)]
    if blank_rows:
        issues.append(_issue("CSV_EMPTY_ROWS", "error", "Blank CSV rows are not allowed.", rows=blank_rows))
    rows = [dict(zip(headers, row)) for row in raw_rows if len(row) == len(headers)]

    section_headers = [header for header in headers if CSV_SECTION_PATTERN.fullmatch(header)]
    if not section_headers:
        issues.append(_issue(
            "CSV_BODY_SECTION_MISSING", "error",
            "At least one body_section_N column is required; related paragraph/list HTML belongs in that one logical column.",
        ))
    else:
        section_keys = [CSV_SECTION_PATTERN.fullmatch(header).group(1) for header in section_headers]
        semantic_sections = [_semantic_number(key) for key in section_keys]
        if semantic_sections != sorted(semantic_sections):
            issues.append(_issue(
                "CSV_SECTION_ORDER_INVALID", "error",
                "body_section_N columns must follow ascending source section order.", columns=section_headers,
            ))
        duplicate_sections = sorted(key for key, count in Counter(semantic_sections).items() if count > 1)
        if duplicate_sections:
            issues.append(_issue(
                "CSV_SECTION_NUMBER_DUPLICATE", "error",
                "Section numbers must be semantically unique; do not mix forms such as 1 and 01.",
                sections=["_".join(str(part) for part in key) for key in duplicate_sections],
            ))
    for index, header in enumerate(headers):
        if _is_image_header(header):
            image_key = _image_key(header)
            next_header = headers[index + 1] if index + 1 < len(headers) else None
            if image_key is None:
                issues.append(_issue(
                    "CSV_IMAGE_HEADER_INVALID", "error",
                    "Image headers must use image_N or img_N numbering.", image_column=header,
                ))
            if not next_header or _alt_key(next_header) != image_key:
                issues.append(_issue(
                    "CSV_IMAGE_ALT_ADJACENCY", "error",
                    "Every image_N column must be followed immediately by its matching alt_N column.",
                    image_column=header, following_column=next_header,
                ))
        if _is_alt_header(header):
            alt_key = _alt_key(header)
            previous_header = headers[index - 1] if index else None
            if alt_key is None or _image_key(previous_header or "") != alt_key:
                issues.append(_issue(
                    "CSV_ALT_IMAGE_PAIR_INVALID", "error",
                    "Every alt_N column must immediately follow its matching image_N column.",
                    alt_column=header, preceding_column=previous_header,
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
    for row_index, row in enumerate(rows, start=2):
        empty_required = sorted(column for column in CSV_BASE_REQUIRED_COLUMNS if not (row.get(column) or "").strip())
        if empty_required:
            issues.append(_issue(
                "CSV_REQUIRED_VALUE_MISSING", "error",
                "Every row requires non-empty site_id, source_url, slug, and target_url values.",
                row=row_index, columns=empty_required,
            ))
    targets = [(row.get("target_url") or "").strip() for row in rows if (row.get("target_url") or "").strip()]
    duplicate_targets = sorted(target for target, count in Counter(targets).items() if count > 1)
    if duplicate_targets:
        issues.append(_issue("CSV_DUPLICATE_TARGET_URL", "error", "Target URLs must be unique.", urls=duplicate_targets))
    slugs = [(row.get("slug") or "").strip() for row in rows if (row.get("slug") or "").strip()]
    duplicate_slugs = sorted(slug for slug, count in Counter(slugs).items() if count > 1)
    if duplicate_slugs:
        issues.append(_issue("CSV_DUPLICATE_SLUG", "error", "Page slugs must be unique.", slugs=duplicate_slugs))
    image_columns = [header for header in headers if _is_image_header(header)]
    for row_index, row in enumerate(rows, start=2):
        for image_header in image_columns:
            image_index = headers.index(image_header)
            alt_header = headers[image_index + 1] if image_index + 1 < len(headers) else None
            image_value = (row.get(image_header) or "").strip()
            alt_value = (row.get(alt_header) or "").strip() if alt_header and _alt_key(alt_header) == _image_key(image_header) else ""
            if image_value and not alt_value:
                issues.append(_issue(
                    "CSV_IMAGE_ALT_VALUE_MISSING", "error",
                    "Every populated image value requires a populated adjacent alt value.",
                    row=row_index, image_column=image_header, alt_column=alt_header,
                ))
            if alt_value and not image_value:
                issues.append(_issue(
                    "CSV_ALT_WITHOUT_IMAGE", "error",
                    "A populated alt value requires its matching image value.",
                    row=row_index, image_column=image_header, alt_column=alt_header,
                ))
    metrics["image_columns"] = image_columns
    metrics["image_alt_pairs"] = sum(1 for index, header in enumerate(headers[:-1]) if _is_image_header(header) and _is_alt_header(headers[index + 1]))
    return _result(issues, metrics)


def validate_csv_translation_coverage(source_csv: str, target_csv: str) -> ValidationResult:
    """Require row/header parity and complete translation of eligible pSEO CSV cells."""
    issues: List[Dict[str, Any]] = []
    metrics: Dict[str, Any] = {"validator": "csv_translation_coverage", "version": V3_VALIDATOR_VERSION}
    try:
        source_headers, source_rows = _csv_rows(source_csv)
        target_headers, target_rows = _csv_rows(target_csv)
    except (csv.Error, UnicodeError) as exc:
        issues.append(_issue("CSV_COVERAGE_PARSE_ERROR", "error", "Source and target CSV must parse for coverage QA.", error=str(exc)))
        return _result(issues, metrics)
    if source_headers != target_headers:
        issues.append(_issue(
            "CSV_SOURCE_TARGET_HEADERS_MISMATCH", "error",
            "Source and translated CSV headers and order must match exactly.",
            source_headers=source_headers, target_headers=target_headers,
        ))
    if len(source_rows) != len(target_rows):
        issues.append(_issue(
            "CSV_SOURCE_TARGET_ROW_COUNT_MISMATCH", "error",
            "Source and translated CSV row counts must match exactly.",
            source_rows=len(source_rows), target_rows=len(target_rows),
        ))
    eligible_indexes = [
        index for index, header in enumerate(source_headers)
        if CSV_TRANSLATABLE_PATTERN.fullmatch(header.casefold().strip())
    ]
    missing: List[Dict[str, Any]] = []
    unchanged: List[Dict[str, Any]] = []
    translated = 0
    source_eligible = 0
    for row_index, (source_row, target_row) in enumerate(zip(source_rows, target_rows), start=2):
        for index in eligible_indexes:
            if index >= len(source_row):
                continue
            source_value = source_row[index].strip()
            target_value = target_row[index].strip() if index < len(target_row) else ""
            if not source_value:
                continue
            source_eligible += 1
            if not target_value:
                missing.append({"row": row_index, "column": source_headers[index]})
                continue
            contains_letters = bool(re.search(r"[A-Za-z]", source_value))
            protected_brand = source_value.casefold() in KNOWN_SITE_ENTITIES
            if contains_letters and not protected_brand and source_value.casefold() == target_value.casefold():
                unchanged.append({"row": row_index, "column": source_headers[index], "value": source_value[:160]})
            else:
                translated += 1
    if missing:
        issues.append(_issue(
            "CSV_ELIGIBLE_VALUE_MISSING", "error",
            "Translated CSV is missing eligible user-facing values.", occurrences=missing[:30], total=len(missing),
        ))
    if unchanged:
        issues.append(_issue(
            "CSV_UNCHANGED_SOURCE_VALUE", "error",
            "Eligible English CSV values remain unchanged in the Spanish target.",
            occurrences=unchanged[:30], total=len(unchanged),
        ))
    metrics.update({
        "eligible_columns": [source_headers[index] for index in eligible_indexes],
        "source_eligible_values": source_eligible,
        "translated_values": translated,
        "coverage_percent": round((translated / source_eligible) * 100, 2) if source_eligible else 0,
    })
    return _result(issues, metrics)
