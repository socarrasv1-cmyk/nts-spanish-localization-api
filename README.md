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
- x-api-key header compatibility
- health endpoints (`/health`, `/healthz`)
- OpenAPI schema (`/openapi.json`)

## Safety boundary
No production deploy, FTP/cPanel/SSH, arbitrary shell, arbitrary SQL, DNS/CDN, CRM writes, or live-site file modification.

## Start locally

```bash
cp .env.example .env
# edit NTS_API_KEY (recommended) and ALLOWED_ORIGINS
docker compose up --build
```

Open:
`http://localhost:8000/docs`

Quick checks:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/openapi.json
```

## Environment variables

Required in production:
- `NTS_ENV=production`
- `NTS_API_KEY=<strong-random-token>`

Optional / recommended:
- `ALLOWED_ORIGINS=https://your-lovable-app.com,https://another-origin.com`
- `DATABASE_URL=postgres://...` (for durable production storage)
- `NTS_DATA_DIR=./data` (local fallback only)

Auth behavior:
- `NTS_ENV=development` and no `NTS_API_KEY`: auth checks are relaxed for local development.
- `NTS_ENV=production`: API key auth is required.
- Supported headers:
  - `Authorization: ******`
  - `x-api-key: <NTS_API_KEY>`

## Deployment notes

- Deploy behind HTTPS (Render/Railway/Fly/AWS/GCP).
- Confirm your deployed URL serves:
  - `GET /health`
  - `GET /openapi.json`
- Configure secrets in deployment settings, never in source files.

## GPT Builder
### Connect Custom GPT Action
1. Deploy API and copy your HTTPS base URL, for example `https://api.example.com`.
2. In GPT Actions, import:
   - `https://api.example.com/openapi.json`
3. Configure Action authentication using your API key.
4. Test `GET /health` and then a protected endpoint like `GET /v2/sites`.

If your GPT workflow needs a static schema file, publish a generated `openapi.json` artifact at a stable HTTPS URL and keep the server URL aligned with the deployed API base URL.

## Lovable
### Connect a Lovable project
Set environment variables:
- `API_BASE_URL=https://api.example.com`
- `API_KEY=<same NTS_API_KEY>`

Send one of these headers from Lovable:
- `x-api-key: <API_KEY>` (recommended for web clients)
- `Authorization: ******`

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

## CI

GitHub Actions workflow (`.github/workflows/ci.yml`) runs on push/PR and validates:
- tests (`pytest -q`)
- Docker image build (`docker build .`)

## Troubleshooting

- **CORS error from Lovable/browser**: add the exact frontend origin to `ALLOWED_ORIGINS` and redeploy.
- **401 Unauthorized**: verify `NTS_API_KEY` matches the sent value and send either `x-api-key` or `Authorization`.
- **GPT schema import fails**: open `https://<your-api>/openapi.json` in a browser and verify it is public HTTPS JSON.
