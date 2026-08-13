# KB-B V3 - Technical SEO, URL, Schema, PHP, and Deployment

Version: 3.0.0  
Owner: Javier Socarras  
Dependencies: Blueprint V3, KB-A V3

## Strict technical mirror

The production equation is: same PHP functionality + same DOM topology + same
layout/modules + same facts + complete Spanish content + approved localized URLs.
Preserve PHP/HTML/JS/CSS/template syntax, execution order, includes, functions,
variables, constants, keys, classes, IDs, selectors, form names and machine values,
API/CRM/database fields, analytics IDs, media paths, responsive copies, and schema
topology. Translate every visible and invisible user-facing value, including errors,
loading/success states, consent copy, metadata, alt/title/ARIA, and descriptive schema.

Full-page and batch requests require complete deployable files, never fragments or
samples. Restore protected tokens byte-for-byte and lint PHP without executing it.

## Approved URL contract

A Spanish production URL must come from the approved site-specific URL map. A bare
`/es/` prefix plus an English slug is not approval. Each mapping stores site ID,
source URL/canonical, Spanish URL/canonical, reciprocal `en` and `es-US` hreflang,
optional x-default, approval/reviewer, collision result, existence/indexability,
version, and verified date. Validation never equals approval.

After approval, update navigation, mega menus, breadcrumbs, contextual links,
cards, parent-child links, reverse routes, CTAs, canonicals, hreflang, JSON-LD URLs,
schema `@id`, sitemap entries, and redirects from the same mapping. Freeze approved
mappings; changes require a new version and review. Block collisions, unsafe schemes,
wrong domains, placeholder links, missing targets, and mismatched canonicals.

## Metadata and schema

Preserve source intent and facts while localizing titles, descriptions, headings,
anchors, and visible schema descriptions naturally. Exactly one canonical is
required. English and `es-US` alternates must be reciprocal. Schema must parse as
JSON, use schema.org context, match visible Spanish content, and preserve keys,
types, entity relationships, ratings, prices, people, locations, and identifiers.
Never invent reviews, ratings, prices, FAQs, credentials, locations, or business facts.

## Forms and accessibility

Translate labels, placeholders, option display text, required indicators, help,
validation, loading, success, error, confirmation, consent, and privacy text.
Preserve machine option values, field names, IDs, endpoints, hidden controls,
anti-spam controls, analytics, and CRM mappings. Preserve heading hierarchy,
landmarks, focus behavior, labels, ARIA relationships, and alternative text.

## Deployment boundary

Every package records API/schema/validator/knowledge versions, site, locale, source
revision and hashes, destination tree, URL-map version, manifest, QA evidence,
review status, known blockers, rollback note, and deployment instructions. Production
merge/deployment requires Javier Socarras's explicit approval. No autonomous merge,
push, or deploy is permitted. Secrets remain in environment variables and logs redact
authorization headers and private artifacts.
