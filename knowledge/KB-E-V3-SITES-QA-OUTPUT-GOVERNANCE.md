# KB-E V3 - Sites, Entity Isolation, QA, Output, and Governance

Version: 3.0.0  
Owner: Javier Socarras  
Dependencies: Blueprint V3, KB-A/B/C/D V3

## Site and entity isolation

Each job has one site ID and one evidence boundary. A brand, legal entity, phone,
email, address, logo, schema ID, testimonial, award, employee, credential, count,
local claim, URL, form endpoint, analytics value, service claim, or Translation Memory
record from another site is BLOCKING unless the authoritative source explicitly
supports it. `Heavy Equipment Transport` and `Nationwide Transport Services` remain
protected brands. Site aliases normalize to canonical IDs before retrieval and QA.

## Governed states and evidence

`INTAKE → URL_RESOLVED → SOURCE_LOCKED → TRANSLATED → VALIDATED →
NEEDS_REVIEW | READY | BLOCKED → PACKAGED`.

Every consequential transition records event ID, actor, timestamp, prior/new state,
reason, source/draft hashes and integrity status. Source and draft artifacts are
immutable, expire under policy, and verify SHA-256 on retrieval. No state is skipped.

## Mandatory validators

- PHP lint without execution
- DOM topology, order, IDs, classes and names
- protected tokens and byte-level restoration
- unintended English residue
- schema, canonical and reciprocal hreflang
- links, domains, unsafe schemes and approved mappings
- eligible-string inventory and 100% coverage
- factual/numerical/entity parity
- terminology and prohibited variants
- forms, accessibility and responsive/global components
- site/entity isolation
- CSV contract and duplicate targets when applicable
- batch expected/received/completed/missing/duplicate/blocked counts
- human visual review: expansion, clipping, wrapping, media, tables and mobile parity

Each result includes request ID, validator/version, PASS/REVIEW/FAIL, blocking flag,
issue code/severity/location, metrics, hashes and execution time. Hard-coded PASS,
fixed scores, placeholder URLs and fabricated READY are forbidden.

READY requires every mandatory check, 100% coverage, zero blockers, zero protected
drift, correct facts/URLs/schema/links, valid syntax, no leakage, completed visual
review and score ≥95. Any error is BLOCKED. Warnings or pending review produce
NEEDS_REVIEW. Packaging requires READY plus verified runtime and knowledge provenance.

## Output contract

Lead with the true completion state and deliverable. Report mode, locale, site/page
family, source revision/hash, target URL approval, output type, source/translated
counts, protected tokens, validators, score, blockers/warnings, visual review and final
status. Distinguish created/proposed, validated/approved, staged/merged,
configured/deployed, and observed behavior/verified provenance.

## Security and release governance

Public Actions expose only governed V3 operations. Terminology/URL approval, Git
staging, merge and deployment are private human workflows. Never request or reveal
secrets. Enforce bearer authentication, constant-time comparison, payload/rate limits,
atomic or transactional persistence, retention, path validation and redacted logs.
Every release runs positive, negative, boundary, adversarial, restart, persistence,
malformed-input, cross-site, CSV-order, prompt-injection-as-data, and page-family pilot
tests. Production requires a verified branch/full SHA, matching schema/validator/
knowledge versions, passing evidence, rollback plan, and Javier Socarras's approval.
