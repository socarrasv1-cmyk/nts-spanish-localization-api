# KB-A V3 - Language, Terminology, and Translation Memory

Version: 3.0.0  
Owner: Javier Socarras  
Locale: es-US  
Dependency: NTS Spanish Translator Blueprint V3

## Language contract

Use neutral U.S. Spanish that sounds like a logistics specialist: professional,
direct, reassuring, concise, and operationally precise. Prefer `usted` or neutral
constructions; never mix `tú`, `usted`, and `vos`. Use natural Spanish sentence
capitalization, punctuation, short paragraphs, and active voice when natural.
Avoid Spain-specific vocabulary when a pan-Hispanic term is clearer.

The English source controls facts and claim strength. Preserve numbers, units,
currency, dates, dimensions, model punctuation, legal language, quoted testimony,
and uncertainty. Never convert units or silently correct inconsistent source claims.

## Binding terminology

| English | Preferred es-US | Allowed/context note | Never use |
|---|---|---|---|
| transportation | transporte | movement/service context | transportación |
| heavy equipment transport | transporte de equipo pesado | transporte de maquinaria pesada | transportación de equipo pesado |
| Heavy Equipment Transport | Heavy Equipment Transport | protected brand | translated brand name |
| Nationwide Transport Services | Nationwide Transport Services | protected brand/legal name | translated brand name |
| auto transport | transporte de vehículos | transporte de automóviles when context requires | transportación de autos |
| car shipping | envío de vehículos | transporte de vehículos | envío marítimo unless ocean context |
| shipping | envío / transporte | choose from operational context | literal one-term substitution |
| carrier | transportista | carrier may remain in legal/technical code | cargador |
| shipper | remitente / cliente remitente | resolve from contract context | transportista when source means customer |
| freight | carga | mercancía in customs context | flete when source means cargo |
| quote | cotización | presupuesto only when source context supports it | cuota |
| get a quote | solicitar una cotización | obtener una cotización | conseguir una cuota |
| heavy haul | transporte de carga pesada | acarreo pesado when approved by site context | traducción literal without context |
| oversize load | carga sobredimensionada | carga de gran tamaño | carga de sobrepeso unless weight-specific |
| overweight load | carga con sobrepeso | carga de peso excedente | carga sobredimensionada unless size-specific |
| break bulk | carga fraccionada | carga suelta in approved ocean context | carga a granel |
| bulk cargo | carga a granel | - | carga fraccionada |
| project cargo | carga de proyecto | carga para proyectos | carga de proyectos genérica when entity-specific |
| drayage | acarreo portuario | transporte de corta distancia in explanatory copy | dragado |
| power only | servicio power only | transporte solo con tractor when explanatory | translate machine/service identifiers |
| LTL | LTL / carga parcial | expand once when helpful | change acronym |
| FTL | FTL / carga completa | expand once when helpful | change acronym |
| flatbed | plataforma | remolque de plataforma | cama plana |
| step deck | plataforma escalonada | remolque step deck | escalón de cubierta |
| lowboy | lowboy | remolque de cama baja | niño bajo |
| RGN | RGN | remolque de cuello desmontable | change acronym |
| loading | carga | proceso de carga | cargamento when process is meant |
| unloading | descarga | proceso de descarga | descargando as noun |
| securement | sujeción de la carga | aseguramiento de la carga | seguridad when mechanical securement is meant |
| transit time | tiempo de tránsito | plazo estimado de tránsito | tiempo garantizado |
| pickup | recogida | recolección where site-approved | camioneta unless vehicle context |
| delivery | entrega | - | suministro when transport delivery is meant |
| route | ruta | corredor for corridor context | recorrido when URL entity is a route |
| port | puerto | terminal only when source says terminal | marina |
| bill of lading | conocimiento de embarque | BOL may remain | factura de carga |
| permit | permiso | autorización when jurisdiction uses it | licencia unless source says license |

Every terminology record has: source term, preferred translation, approved
variants, prohibited variants, site, component, context, status, reviewer,
effective date, and affected outputs. Context overrides string-only matching.

## Translation Memory governance

Search exact source + locale + site + component first, then an approved global
component, then context-compatible approved variants. Fuzzy matches are suggestions
only. Only `approved` records are canonical. Proposal IDs must be refreshed from a
current list before review; a not-found ID is terminal and must not be retried.
Approvals and rejections require a human reviewer, reason, timestamp, prior/new
status, and audit event. A canonical-term change triggers regression review for
every affected site, page, component, URL, and template.

Global UI translations use stable component keys. Never apply page-specific prose
as a global translation and never reuse a term across sites when its context differs.
