from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Comment


SEVERITY_PENALTIES = {"error": 20, "warning": 5, "info": 1}
IGNORED_STRUCTURE_TAGS = {"script", "style", "noscript"}
ENGLISH_PHRASES = {
    "get a quote", "start quote", "request a quote", "learn more", "contact us",
    "call now", "read more", "our services", "why choose us", "frequently asked questions",
    "shipping services", "submit", "next", "previous",
}
ENGLISH_WORDS = {
    "about", "and", "available", "best", "call", "choose", "contact", "delivery",
    "equipment", "estimate", "faq", "free", "freight", "get", "haul", "learn",
    "more", "next", "now", "our", "previous", "quote", "request", "service",
    "shipping", "start", "submit", "truck", "why", "with",
}
ALLOWED_ENGLISH_TOKENS = {
    "api", "html", "json", "php", "seo", "url", "usd", "gps", "dot", "fmcsa",
    "nationwide", "transport", "services", "inc", "llc",
}


@dataclass
class ValidationResult:
    status: str
    blocking: bool
    issues: List[Dict[str, Any]] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "blocking": self.blocking,
            "issues": self.issues,
            "metrics": self.metrics,
        }


def _issue(code: str, severity: str, message: str, **details: Any) -> Dict[str, Any]:
    item: Dict[str, Any] = {"code": code, "severity": severity, "message": message}
    if details:
        item["details"] = details
    return item


def _result(issues: List[Dict[str, Any]], metrics: Dict[str, Any]) -> ValidationResult:
    blocking = any(issue.get("severity") == "error" for issue in issues)
    status = "FAIL" if blocking else "REVIEW" if issues else "PASS"
    return ValidationResult(status=status, blocking=blocking, issues=issues, metrics=metrics)


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html or "", "lxml")


def _visible_text(html: str) -> str:
    soup = _soup(html)
    for element in soup(["script", "style", "noscript", "template", "svg"]):
        element.decompose()
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()
    return " ".join(soup.stripped_strings)


def _tag_path(tag: Any) -> str:
    parts = []
    current = tag
    while getattr(current, "name", None) and len(parts) < 8:
        sibling_index = 1
        sibling = current.previous_sibling
        while sibling is not None:
            if getattr(sibling, "name", None) == current.name:
                sibling_index += 1
            sibling = sibling.previous_sibling
        parts.append(f"{current.name}:nth-of-type({sibling_index})")
        current = current.parent
    return " > ".join(reversed(parts))


def _structure_signature(html: str) -> Tuple[List[Tuple[int, str]], Counter, Dict[str, Counter]]:
    soup = _soup(html)
    sequence: List[Tuple[int, str]] = []
    attrs: Dict[str, Counter] = {"ids": Counter(), "classes": Counter(), "names": Counter()}
    for tag in soup.find_all(True):
        if tag.name in IGNORED_STRUCTURE_TAGS:
            continue
        depth = len(list(tag.parents))
        sequence.append((depth, tag.name))
        if tag.get("id"):
            attrs["ids"][tag["id"]] += 1
        for cls in tag.get("class", []):
            attrs["classes"][cls] += 1
        if tag.get("name"):
            attrs["names"][tag["name"]] += 1
    return sequence, Counter(name for _, name in sequence), attrs


def validate_php(php_code: str) -> ValidationResult:
    """Run php -l against supplied PHP/HTML content without executing it."""
    issues: List[Dict[str, Any]] = []
    code = php_code or ""
    php_binary = shutil.which("php")
    metrics: Dict[str, Any] = {
        "validator": "php", "version": "2.2",
        "bytes_checked": len(code.encode("utf-8")),
        "php_blocks": len(re.findall(r"<\?(?:php|=)?", code, flags=re.I)),
    }
    if not code.strip():
        issues.append(_issue("PHP_EMPTY_INPUT", "error", "No PHP content was supplied."))
        return _result(issues, metrics)
    if metrics["php_blocks"] == 0:
        metrics["lint_skipped"] = "no_php_blocks"
        return _result(issues, metrics)
    if not php_binary:
        issues.append(_issue("PHP_CLI_UNAVAILABLE", "error", "PHP CLI is unavailable; syntax cannot be verified."))
        return _result(issues, metrics)
    try:
        with tempfile.TemporaryDirectory(prefix="nts_php_") as tmpdir:
            path = Path(tmpdir) / "candidate.php"
            path.write_text(code, encoding="utf-8")
            proc = subprocess.run(
                [php_binary, "-l", str(path)], capture_output=True, text=True,
                timeout=12, check=False,
            )
        metrics["exit_code"] = proc.returncode
        if proc.returncode != 0:
            message = (proc.stderr or proc.stdout or "PHP syntax error").strip()
            message = message.replace(str(path), "candidate.php")
            issues.append(_issue("PHP_SYNTAX_ERROR", "error", message[:800]))
    except subprocess.TimeoutExpired:
        issues.append(_issue("PHP_LINT_TIMEOUT", "error", "PHP lint exceeded the 12-second safety limit."))
    except OSError as exc:
        issues.append(_issue("PHP_LINT_ERROR", "error", f"PHP lint could not run: {exc}"))
    return _result(issues, metrics)


def validate_structure(source_html: str, target_html: str) -> ValidationResult:
    """Compare DOM topology and protected structural attributes."""
    issues: List[Dict[str, Any]] = []
    if not (source_html or "").strip() or not (target_html or "").strip():
        issues.append(_issue("STRUCTURE_EMPTY_INPUT", "error", "Both source_html and target_html are required."))
        return _result(issues, {"validator": "structure", "version": "2.2"})
    source_seq, source_counts, source_attrs = _structure_signature(source_html)
    target_seq, target_counts, target_attrs = _structure_signature(target_html)
    metrics: Dict[str, Any] = {
        "validator": "structure", "version": "2.2",
        "source_elements": len(source_seq), "target_elements": len(target_seq),
        "element_delta": len(target_seq) - len(source_seq),
    }
    if source_seq != target_seq:
        first_diff = next(
            (index for index, pair in enumerate(zip(source_seq, target_seq)) if pair[0] != pair[1]),
            min(len(source_seq), len(target_seq)),
        )
        issues.append(_issue(
            "DOM_TOPOLOGY_MISMATCH", "error", "English and Spanish DOM topology is not an exact mirror.",
            first_difference_index=first_diff,
            missing_tags=dict(source_counts - target_counts), extra_tags=dict(target_counts - source_counts),
        ))
    for attr_name in ("ids", "classes", "names"):
        missing = dict(source_attrs[attr_name] - target_attrs[attr_name])
        extra = dict(target_attrs[attr_name] - source_attrs[attr_name])
        if missing or extra:
            issues.append(_issue(
                f"DOM_{attr_name.upper()}_MISMATCH", "error",
                f"Protected DOM {attr_name} changed in the Spanish mirror.", missing=missing, extra=extra,
            ))
    return _result(issues, metrics)


DEFAULT_TOKEN_PATTERNS: Sequence[Tuple[str, str]] = (
    ("php_block", r"<\?(?:php|=)?[\s\S]*?\?>"),
    ("php_variable", r"\$[A-Za-z_][A-Za-z0-9_]*"),
    ("template_token", r"\{\{[^{}]+\}\}|\{[%#][\s\S]*?[%#]\}"),
    ("printf_token", r"%(?:\d+\$)?[bcdeEfFgGosuxX]"),
    ("email", r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"),
    ("phone", r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\d)"),
    # Localized internal paths are expected to change; preserve the origin so a
    # translation cannot silently redirect to another host.
    ("web_origin", r"https?://[^/\s\"'<>]+"),
    ("analytics_id", r"\b(?:G-[A-Z0-9]{6,}|UA-\d+-\d+|GTM-[A-Z0-9]+)\b"),
)


def _extract_tokens(content: str, patterns: Optional[Iterable[str]] = None) -> Dict[str, Counter]:
    extracted: Dict[str, Counter] = {}
    named_patterns = list(DEFAULT_TOKEN_PATTERNS)
    if patterns:
        named_patterns.extend((f"custom_{index + 1}", pattern) for index, pattern in enumerate(patterns))
    for name, pattern in named_patterns:
        try:
            extracted[name] = Counter(re.findall(pattern, content or "", flags=re.I))
        except re.error as exc:
            extracted[name] = Counter({f"INVALID_PATTERN:{exc}": 1})
    return extracted


def validate_protected_tokens(
    source_content: str, target_content: str, token_patterns: Optional[Iterable[str]] = None,
) -> ValidationResult:
    """Require protected code/factual tokens to match exactly, including counts."""
    issues: List[Dict[str, Any]] = []
    if not (source_content or "").strip() or not (target_content or "").strip():
        issues.append(_issue("TOKENS_EMPTY_INPUT", "error", "Both source_content and target_content are required."))
        return _result(issues, {"validator": "protected_tokens", "version": "2.2"})
    normalized_patterns: List[str] = []
    if token_patterns:
        if isinstance(token_patterns, str):
            issues.append(_issue("TOKEN_PATTERNS_INVALID", "error", "token_patterns must be an array of regular expressions."))
            return _result(issues, {"validator": "protected_tokens", "version": "2.2"})
        for index, pattern in enumerate(token_patterns):
            try:
                re.compile(pattern)
                normalized_patterns.append(pattern)
            except (re.error, TypeError) as exc:
                issues.append(_issue(
                    "TOKEN_PATTERN_INVALID", "error", "A custom protected-token pattern is invalid.",
                    pattern_index=index, error=str(exc),
                ))
        if issues:
            return _result(issues, {"validator": "protected_tokens", "version": "2.2"})
    source = _extract_tokens(source_content, normalized_patterns)
    target = _extract_tokens(target_content, normalized_patterns)
    checked = 0
    for token_type in source:
        checked += sum(source[token_type].values())
        missing = dict(source[token_type] - target[token_type])
        extra = dict(target[token_type] - source[token_type])
        if missing or extra:
            issues.append(_issue(
                "PROTECTED_TOKEN_MISMATCH", "error", f"Protected {token_type} values changed.",
                token_type=token_type, missing=missing, extra=extra,
            ))
    return _result(issues, {
        "validator": "protected_tokens", "version": "2.2", "protected_tokens_checked": checked,
    })


def validate_english_residue(target_content: str) -> ValidationResult:
    """Heuristically detect untranslated English in Spanish visible text."""
    issues: List[Dict[str, Any]] = []
    if not (target_content or "").strip():
        issues.append(_issue("ENGLISH_EMPTY_INPUT", "error", "No Spanish target content was supplied."))
        return _result(issues, {"validator": "english_residue", "version": "2.2"})
    text = _visible_text(target_content)
    lowered = text.lower()
    phrases = sorted(phrase for phrase in ENGLISH_PHRASES if phrase in lowered)
    tokens = re.findall(r"[A-Za-z][A-Za-z'-]{2,}", lowered)
    word_hits = sorted({token for token in tokens if token in ENGLISH_WORDS and token not in ALLOWED_ENGLISH_TOKENS})
    hit_count = sum(lowered.count(phrase) for phrase in phrases) + sum(tokens.count(word) for word in word_hits)
    ratio = hit_count / max(len(tokens), 1)
    if phrases:
        issues.append(_issue(
            "ENGLISH_PHRASE_RESIDUE", "error", "High-confidence English phrases remain in Spanish visible text.",
            phrases=phrases[:20],
        ))
    if word_hits:
        severity = "warning" if ratio < 0.08 and len(word_hits) <= 4 else "error"
        issues.append(_issue(
            "ENGLISH_WORD_RESIDUE", severity, "Possible untranslated English words remain.",
            words=word_hits[:30], english_hit_ratio=round(ratio, 4),
        ))
    return _result(issues, {
        "validator": "english_residue", "version": "2.2", "visible_words": len(tokens),
        "english_hits": hit_count, "english_hit_ratio": round(ratio, 4),
    })


def _walk_json(value: Any, path: str = "$") -> Iterable[Tuple[str, Any]]:
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk_json(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_json(child, f"{path}[{index}]")


def _rel_contains(value: Any, target: str) -> bool:
    values = value if isinstance(value, list) else [value]
    return target in {str(item).lower() for item in values if item}


def _url_matches_expected(actual: str, expected: str) -> bool:
    actual_parts, expected_parts = urlparse(actual), urlparse(expected)
    expected_path = expected_parts.path or expected
    return actual_parts.path == expected_path and (
        not expected_parts.netloc or actual_parts.netloc.casefold() == expected_parts.netloc.casefold()
    )


def validate_schema(html_content: str, expected_spanish_url: Optional[str] = None) -> ValidationResult:
    """Validate JSON-LD syntax, canonical and hreflang metadata."""
    issues: List[Dict[str, Any]] = []
    if not (html_content or "").strip():
        issues.append(_issue("SCHEMA_EMPTY_INPUT", "error", "No HTML content was supplied."))
        return _result(issues, {"validator": "schema", "version": "2.2"})
    soup = _soup(html_content)
    jsonld_nodes = soup.find_all("script", attrs={"type": re.compile(r"application/ld\+json", re.I)})
    parsed_count = 0
    schema_types: List[str] = []
    for index, node in enumerate(jsonld_nodes):
        raw = node.string or node.get_text()
        try:
            document = json.loads(raw)
            parsed_count += 1
            for path, value in _walk_json(document):
                if path.endswith(".@context") and isinstance(value, str) and "schema.org" not in value:
                    issues.append(_issue("SCHEMA_CONTEXT_INVALID", "error", "JSON-LD @context must reference schema.org.", path=path))
                if path.endswith(".@type"):
                    schema_types.extend(value if isinstance(value, list) else [value])
                if path.endswith((".url", ".@id")) and isinstance(value, str) and value.startswith("/"):
                    issues.append(_issue("SCHEMA_RELATIVE_URL", "warning", "Schema URL should be absolute.", path=path, value=value))
        except json.JSONDecodeError as exc:
            issues.append(_issue(
                "SCHEMA_JSON_INVALID", "error", "JSON-LD is not valid JSON.",
                script_index=index, line=exc.lineno, column=exc.colno,
            ))
    if not jsonld_nodes:
        issues.append(_issue("SCHEMA_JSONLD_MISSING", "warning", "No JSON-LD block was found."))
    canonical_nodes = soup.find_all("link", rel=lambda value: _rel_contains(value, "canonical"))
    if len(canonical_nodes) != 1:
        issues.append(_issue("CANONICAL_COUNT_INVALID", "error", "Exactly one canonical link is required.", count=len(canonical_nodes)))
    elif not canonical_nodes[0].get("href"):
        issues.append(_issue("CANONICAL_HREF_MISSING", "error", "Canonical link is missing href."))
    elif expected_spanish_url and not _url_matches_expected(canonical_nodes[0].get("href", ""), expected_spanish_url):
        issues.append(_issue(
            "CANONICAL_TARGET_MISMATCH", "error", "Canonical does not point to the expected Spanish URL.",
            expected=expected_spanish_url, actual=canonical_nodes[0].get("href"),
        ))
    alternates = soup.find_all("link", rel=lambda value: _rel_contains(value, "alternate"))
    hreflangs = {str(node.get("hreflang", "")).lower() for node in alternates if node.get("hreflang")}
    if not any(lang.startswith("es") for lang in hreflangs):
        issues.append(_issue("HREFLANG_ES_MISSING", "warning", "Spanish hreflang alternate is missing."))
    if not any(lang.startswith("en") for lang in hreflangs):
        issues.append(_issue("HREFLANG_EN_MISSING", "warning", "English hreflang alternate is missing."))
    return _result(issues, {
        "validator": "schema", "version": "2.2", "jsonld_blocks": len(jsonld_nodes),
        "jsonld_parsed": parsed_count, "schema_types": sorted({str(item) for item in schema_types}),
        "hreflangs": sorted(hreflangs),
    })


def validate_links(html_content: str, expected_spanish_url: Optional[str] = None) -> ValidationResult:
    """Validate local link/reference syntax without making outbound requests."""
    issues: List[Dict[str, Any]] = []
    if not (html_content or "").strip():
        issues.append(_issue("LINKS_EMPTY_INPUT", "error", "No HTML content was supplied."))
        return _result(issues, {"validator": "links", "version": "2.2"})
    soup = _soup(html_content)
    links = soup.find_all(["a", "link", "img", "script", "source"])
    checked = placeholder_count = unsafe_count = 0
    for tag in links:
        attr = "href" if tag.name in {"a", "link"} else "src"
        value = (tag.get(attr) or "").strip()
        if not value:
            if tag.name == "a":
                issues.append(_issue("LINK_TARGET_MISSING", "warning", "Anchor is missing href.", selector=_tag_path(tag)))
            continue
        checked += 1
        lowered = value.lower()
        if lowered.startswith(("javascript:", "data:text/html")):
            unsafe_count += 1
            issues.append(_issue("LINK_UNSAFE_SCHEME", "error", "Unsafe link scheme detected.", value=value, selector=_tag_path(tag)))
        if value == "#" or "placeholder" in lowered or "example.com" in lowered:
            placeholder_count += 1
            issues.append(_issue("LINK_PLACEHOLDER", "warning", "Placeholder link detected.", value=value, selector=_tag_path(tag)))
        if " " in value and not value.startswith("data:"):
            issues.append(_issue("LINK_UNENCODED_SPACE", "warning", "Link contains an unencoded space.", value=value))
        parsed = urlparse(value)
        if parsed.scheme and parsed.scheme not in {"http", "https", "mailto", "tel", "data"}:
            issues.append(_issue("LINK_UNKNOWN_SCHEME", "warning", "Unexpected link scheme.", value=value))
    canonicals = soup.find_all("link", rel=lambda value: _rel_contains(value, "canonical"))
    if expected_spanish_url and canonicals:
        href = canonicals[0].get("href", "")
        if not _url_matches_expected(href, expected_spanish_url):
            issues.append(_issue("LINK_CANONICAL_MISMATCH", "error", "Canonical does not match target_url.", expected=expected_spanish_url, actual=href))
    return _result(issues, {
        "validator": "links", "version": "2.2", "references_checked": checked,
        "placeholder_links": placeholder_count, "unsafe_links": unsafe_count,
    })


def score_validation_results(checks: Dict[str, ValidationResult]) -> Dict[str, Any]:
    """Calculate deterministic QA score and publication status from evidence."""
    weights = {
        "php": 15, "structure": 20, "protected_tokens": 20,
        "english_residue": 15, "schema": 15, "links": 15,
    }
    score = 100
    blocking_issues: List[Dict[str, Any]] = []
    for name, result in checks.items():
        max_penalty = weights.get(name, 10)
        raw_penalty = sum(SEVERITY_PENALTIES.get(issue.get("severity", "warning"), 5) for issue in result.issues)
        score -= min(max_penalty, raw_penalty)
        if result.blocking:
            blocking_issues.extend(
                {"validator": name, **issue} for issue in result.issues if issue.get("severity") == "error"
            )
    score = max(0, min(100, score))
    status = "BLOCKED" if blocking_issues else "READY" if score >= 95 else "NEEDS_REVIEW"
    return {"score": score, "status": status, "blocking_issues": blocking_issues}
