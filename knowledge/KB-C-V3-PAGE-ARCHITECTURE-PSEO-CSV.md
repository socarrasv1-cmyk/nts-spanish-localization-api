# KB-C V3 - Page Architecture, Programmatic SEO, and CSV

Version: 3.0.0  
Owner: Javier Socarras  
Dependencies: Blueprint V3, KB-A V3, KB-B V3

## Universal architecture rule

Classify the source page family before translation and preserve every source module,
its order, entity, intent, relationships, responsive duplicates, and conversion path.
The inventories below are completeness checks, not permission to add absent content.

- Homepage: top bar, navigation/mega menu, hero/form, trust, service cards,
  authority, geographic lists, shipments, affiliations, manufacturers, cases,
  testimonials, footer, legal, metadata, schema, accessibility.
- Service hub/page: filters/states, full service inventory, definitions, process,
  use cases, cargo/equipment, requirements, linked services, shipments, trailers,
  FAQs, CTAs, compliance.
- State/city: exact geographic entity, parent/children, access points, highways,
  sourced ports/rail/air, nearby cities, routes, services, equipment, facts, maps,
  FAQs and CTAs. Never invent local expertise or facilities.
- Route/lane: immutable origin, destination, direction, reverse route, distance,
  estimated transit, corridor, restrictions, equipment, sourced cost, related lanes.
- Equipment/manufacturer/model/trailer: protected names, condition, dimensions,
  weight, loading, securement, permits, compatible trailer, specifications and units.
- Port/container/international: official port/terminal, container/chassis, drayage,
  loading, crane/forklift, customs, TWIC, documents, border/trade direction.
- Article/glossary/case study/about/legal/form: preserve author/reviewer, dates,
  sources, quick answer, facts, IDs, testimony, people, credentials, legal numbering,
  field states, privacy, and required review.

Preserve the intelligence-hub role: brand → hub → category → entity; state → city;
directional route → reverse route; guide/glossary/FAQ/case; tool/form. A child page
must not collapse into generic parent copy or compete with its parent.

## Programmatic record

Each page records primary entity, intent, canonical concept, supporting concepts,
parent, children, siblings, breadcrumb, unique facts, direct-answer block, CTA, FAQ,
title, description, H1, schema, source revision, approved URL, and site ID. Bind every
variable to its correct entity record. Block wrong city/state/origin/destination/
service/site leakage. Suppress a module when its required data is absent; never
manufacture filler. Flag thin or near-duplicate output without fabricating uniqueness.

## Mandatory CSV production contract

CSV is a production interface. The required rules have no exceptions:

1. One semantic purpose per column.
2. Required base columns are `site_id`, `source_url`, `slug`, and `target_url`; every
   row must contain a non-empty value for each.
3. Stable lowercase `snake_case` headers, order, numbering, UTF-8 without BOM,
   consistent line endings, quoting, row width, and empty-value policy.
4. Preserve source section order using ascending `body_section_N` columns.
5. Keep a heading and its following body/list in the approved logical section group.
6. A paragraph and its directly related list stay together in one `body_section_N`
   cell as structured HTML; never split them into `body_p_N` and `body_list_N` columns.
7. Every image occupies its own dedicated numbered column.
8. Every image alt occupies its own dedicated column immediately after that image.
9. Pairing is exact: `image_01` → `alt_01`, `image_02` → `alt_02`; mismatched
   numbering, alt without image, image without alt, or non-adjacent pairs are BLOCKING.
10. Never combine an image path and alt text or place unrelated content in either column.
11. Source and Spanish CSV headers, column order, and row count must match exactly;
    every eligible source cell requires a translated Spanish counterpart.
12. Approved target URLs and slugs are unique; rows preserve site/entity/parent-child isolation.
13. Required fields, unique page data, links, facts, protected tokens, language coverage,
    site isolation, media pairs, and importer-required
    responsive copies must validate before READY.

Any missing alt, non-adjacent image/alt pair, duplicate target, split logical group,
missing required column, duplicate header, malformed CSV, or wrong entity is BLOCKING.
