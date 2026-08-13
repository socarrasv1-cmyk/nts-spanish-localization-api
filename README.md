# NTS Localization API Starter

FastAPI starter for the NTS Spanish Intelligence Hub Actions V2.

## Included
- Bearer API-key authentication
- verified site registry
- localization jobs
- immutable source/draft artifacts
- approved URL-map lookup
- Spanish URL candidate validation
- PHP lint
- structural parity
- protected-token checks
- English-residue scan
- JSON-LD/schema checks
- canonical/hreflang/internal-link checks
- page QA
- batch QA
- staging ZIP generation

## Safety boundary
No production deploy, FTP/cPanel/SSH, arbitrary shell, arbitrary SQL, DNS/CDN, CRM writes, or live-site file modification.

## Start locally

```bash
cp .env.example .env
# edit NTS_API_KEY
docker compose up --build
```

Open:
`http://localhost:8000/docs`

## GPT Builder
Deploy this API behind HTTPS. Then paste the V2 OpenAPI schema into Add Actions and replace the placeholder server URL with your deployed API origin.

## Translation Memory + Git staging
This build adds approval-based Translation Memory and staging-only Git integration. It can create local branches/commits and optionally push/create a draft GitHub PR. It never auto-merges or deploys.

## Durable production storage

Set `DATABASE_URL` to a PostgreSQL connection string in production. The API
creates the `nts_kv_store` table automatically and stores Translation Memory,
proposals, approvals, and rejections there. This keeps review state available
across Render restarts, deployments, and instance changes.

Without `DATABASE_URL`, the service uses atomic JSON files under
`NTS_DATA_DIR`. That fallback is intended for local development only because a
normal Render container filesystem is ephemeral.

After configuring production storage:

1. Submit a Translation Memory proposal.
2. Confirm it appears in `GET /v2/tm/proposals?status=proposed`.
3. Restart the service.
4. Confirm the same proposal still appears.
5. Approve or reject it using its exact `proposal_id`.

Run tests with:

```bash
pytest -q
```
