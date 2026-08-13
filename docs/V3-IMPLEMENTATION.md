# NTS Spanish Translator — Blueprint V3 implementation

This candidate adds a provenance-aware V3 control plane while preserving every
existing V2.2 route. It is not authorized for production promotion until the
currently deployed Render source commit is matched to a GitHub commit and the
separate V3 staging service passes certification.

## Implemented V3 controls

- Exact build provenance, validator version, schema version, and knowledge
  manifest identity via `GET /v3/system/provenance`.
- Fail-closed knowledge manifest: any missing or unmigrated module blocks
  production promotion.
- Site-scoped approved URL mapping required before a job can proceed.
- Immutable English source and Spanish draft artifacts with SHA-256 identities,
  expiry metadata, and integrity verification on read.
- Auditable job state transitions and per-event SHA-256 hashes.
- Deterministic V2.2 validators plus V3 coverage, factual parity, site isolation,
  prompt-injection-as-data, and pSEO CSV contract validators.
- Human visual review gate before `READY`.
- Evidence packaging restricted to `READY` jobs running from verified
  provenance.
- Positive, negative, and adversarial regression fixtures exposed by
  `POST /v3/regression/run`.
- No automatic merge, Git push, or production deployment.

## Release topology

1. Keep the current Render production service and public GPT on the certified
   V2.2 Action contract.
2. Confirm Render production branch and exact deployed commit SHA.
3. Build the `v3` branch from that exact source baseline.
4. Deploy `render-v3-staging.yaml` as a separate private staging service.
5. Set `NTS_GIT_COMMIT`, `NTS_GIT_BRANCH=v3`, and
   `NTS_PROVENANCE_VERIFIED=true` only when they describe the deployed build.
6. Migrate and checksum every knowledge module; the manifest must report
   `VERIFIED`.
7. Run unit, integration, contract, and adversarial regression tests and retain
   the evidence.
8. Connect a private staging GPT to the V3 staging Action schema.
9. Promote only after human certification; update the public GPT last.

## Render staging contract

The separate staging service uses a Starter instance, `/healthz`, and a 1 GB
persistent disk mounted at `/var/data`. `NTS_API_KEY` is supplied in Render and
never committed. `NTS_GIT_PUSH_ENABLED` remains `false`.
