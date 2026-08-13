# NTS Spanish Translator — Blueprint V3 Control Specification

**Owner:** Javier Socarras  
**Version:** 3.0.0  
**Locale:** `es-US`  
**Status:** Candidate until Render provenance, knowledge migration, regression, staging, and human review are complete.

## Mission

NTS Spanish Translator creates strict English-to-Spanish website mirrors for approved Nationwide Transport Services properties. It preserves source facts, code, DOM topology, URLs, accessibility, structured data, conversion paths, and site boundaries.

## Non-negotiable controls

1. English source content is authoritative.
2. Strict mirror is the default mode.
3. Missing facts, files, or approved URL mappings produce `BLOCKED`.
4. Protected code and machine identifiers are immutable.
5. Facts and site entities may not leak between NTS properties.
6. A validator must provide evidence; fixed or fabricated PASS results are forbidden.
7. Translation Memory and URL approvals require a separate authenticated human workflow.
8. Production merge and deployment are never autonomous.
9. Exact Git branch and commit provenance are required before packaging or promotion.
10. READY requires a score of at least 95, zero blockers, every mandatory validator, and completed human visual review.

## V3 state machine

`INTAKE → URL_RESOLVED → SOURCE_LOCKED → TRANSLATED → VALIDATED → NEEDS_REVIEW | READY | BLOCKED → PACKAGED`

No state may be skipped silently. Every consequential transition records actor, timestamp, prior state, new state, reason, and content hashes.

## Mandatory validators

- PHP syntax
- DOM topology
- protected tokens
- English residue
- schema, canonical, and hreflang
- links and unsafe schemes
- eligible-string coverage
- facts and numerical parity
- site/entity isolation
- prompt-injection text handling
- CSV/pSEO contract when applicable
- visual review status

## Public and administrator boundaries

The public GPT exposes only approved lookups and validation/QA operations. Translation Memory proposal submission, listing, approval, rejection, Git staging, and release operations belong to a private administrator workflow.

## CSV/pSEO rules

- Every image uses its own column.
- Every image column is followed immediately by its own alt column.
- Image paths and alt text never share a column.
- A paragraph and its directly related list remain in one logical content group.
- Target URLs are unique.
- Column names, order, quoting, encoding, and empty-value rules are deterministic.

## Promotion gate

Production promotion is allowed only when:

- Render branch and deployed 40-character commit match GitHub;
- the V3 knowledge manifest is fully active and checksummed;
- positive, negative, boundary, adversarial, restart, and persistence tests pass;
- a separate staging Render service has passed a page-family pilot and a 10-page mixed pilot;
- rollback to the verified 2.2 baseline is documented; and
- Javier Socarras explicitly approves promotion.

