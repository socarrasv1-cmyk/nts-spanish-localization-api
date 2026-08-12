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
