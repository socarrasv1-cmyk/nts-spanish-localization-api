# NTS Localization API V2.1

FastAPI backend for NTS Spanish Intelligence Hub — Production-grade localization validation, Translation Memory approval workflow, and staging-only Git integration.

## ✨ Features

### Core Localization
- ✅ Bearer API-key authentication (all endpoints except `/healthz`)
- ✅ Verified NTS site registry
- ✅ Immutable source/draft artifacts with configurable TTL (default 168 hours)
- ✅ Authoritative English-to-Spanish URL mapping (pre-approved only)
- ✅ URL candidate validation (distinct from approval)

### Six Strict-Mirror Validators
1. **PHP Linting** — Syntax validation without execution
2. **DOM Structure Parity** — English ↔ Spanish HTML structure comparison
3. **Protected Token Integrity** — Preserves PHP code, variables, constants, IDs, contact info, analytics IDs, etc.
4. **English Residue Scanning** — Detects unintended English in Spanish output
5. **JSON-LD/Schema Validation** — Syntax, URLs, @id fields, visible-content parity
6. **Links & hreflang** — Internal links, canonical tags, hreflang cross-linking, breadcrumbs

### Quality Assurance
- ✅ Page QA gate: requires score ≥95 AND zero blocking failures (non-negotiable)
- ✅ Batch QA: detects silent skips, duplicate targets, blockers
- ✅ Cross-site data isolation: prevents brand/phone/email/NAP/schema ID leakage

### Translation Memory
- ✅ Approved TM search (site-specific match preferred, then global fallback)
- ✅ Human-review-based proposal workflow (no auto-approval)
- ✅ Proposal rejection keeps entries non-canonical
- ✅ Full audit trail (reviewer, timestamp, reason)

### Git Staging (Staging-Only)
- ✅ Safe branch creation with path traversal protection
- ✅ File staging and commit creation
- ✅ Git push disabled by default (`NTS_GIT_PUSH_ENABLED=false`)
- ✅ Draft pull request support (requires GitHub token)
- ✅ No auto-merge, no production deployment

### Deployment Ready
- ✅ Docker containerization (Python 3.11-slim, PHP CLI, Git)
- ✅ docker-compose for local/staging environments
- ✅ Render Blueprint configuration (render.yaml) for managed hosting
- ✅ Persistent disk support for data retention
- ✅ Health check endpoint (`/healthz`)

---

## Quick Start (Local Development)

### Prerequisites
- Docker & Docker Compose
- Python 3.11+ (for local testing without Docker)

### Setup

```bash
# Clone repository
git clone https://github.com/socarrasv1-cmyk/nts-spanish-localization-api.git
cd nts-spanish-localization-api

# Checkout deployment branch
git checkout feature/v2.1-deployment

# Copy environment template
cp .env.example .env

# Edit .env with your API key
# NTS_API_KEY=your-secret-key-here (should be a strong random value)
```

### Run with Docker Compose

```bash
docker-compose up --build
```

Expected output:
```
nts-localization-api | INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Test Health Check

```bash
# No authentication required
curl http://localhost:8000/healthz
```

Response:
```json
{
  "status": "ok",
  "service": "nts-localization-api",
  "version": "2.1.0"
}
```

### Access API Documentation

Open browser to: `http://localhost:8000/docs`

Interactive Swagger UI with full endpoint documentation.

### Test Protected Endpoint

```bash
# Without authentication (401)
curl http://localhost:8000/v2/sites

# With valid Bearer token (200)
curl -H "Authorization: Bearer your-secret-key-here" http://localhost:8000/v2/sites
```

---

## Environment Variables

### Required (Secret)
- `NTS_API_KEY` — Bearer token for API authentication

### Configuration (Non-Secret)
- `NTS_ARTIFACT_TTL_HOURS=168` — Artifact retention time (default: 7 days)
- `NTS_DATA_DIR=./data` — Data directory (local dev) or `/var/data` (Render)
- `NTS_GIT_REPO_PATH=./data/git-repo` — Git staging repository path
- `NTS_GIT_REMOTE_NAME=origin` — Git remote name
- `NTS_GIT_DEFAULT_BASE_BRANCH=main` — Default base branch
- `NTS_GIT_PUSH_ENABLED=false` — Git push enable/disable (false by default)
- `NTS_GIT_PROVIDER=github` — Git provider (github)

### Optional (For GitHub Integration)
- `NTS_GITHUB_TOKEN` — GitHub personal access token (for draft PR creation)
- `NTS_GITHUB_REPOSITORY` — GitHub repository (e.g., `socarrasv1-cmyk/nts-spanish-localization-api`)

---

## API Endpoints

### Health & Metadata
- `GET /healthz` — Health check (no auth required)

### Sites
- `GET /v2/sites` — List verified NTS sites

### URL Mapping
- `POST /v2/url-map/get` — Get approved English→Spanish mapping
- `POST /v2/url-map/validate` — Validate candidate URL (not approval)

### Validators
- `POST /v2/validate/php` — PHP syntax linting
- `POST /v2/validate/structure` — DOM structure parity
- `POST /v2/validate/protected-tokens` — Protected token integrity
- `POST /v2/validate/english-residue` — English residue scanning
- `POST /v2/validate/schema` — JSON-LD/schema validation
- `POST /v2/validate/links` — Links, canonical, hreflang validation

### QA
- `POST /v2/qa/page` — Page QA gate (score ≥95 + zero blockers = READY)
- `POST /v2/qa/batch` — Batch QA (completeness check)

### Translation Memory
- `POST /v2/tm/search` — Search approved TM
- `POST /v2/tm/proposals` — Submit proposal for review
- `GET /v2/tm/proposals` — List proposals by status
- `POST /v2/tm/proposals/{id}/approve` — Approve proposal
- `POST /v2/tm/proposals/{id}/reject` — Reject proposal

### Git Staging
- `GET /v2/git/status` — Git staging status
- `POST /v2/git/branches` — Create staging branch
- `POST /v2/git/stage` — Stage files and commit
- `POST /v2/git/push` — Push branch (if enabled)
- `POST /v2/git/draft-pr` — Create draft pull request

See `NTS-LOCALIZATION-ACTIONS-OPENAPI-V2.1-LIVE.json` for complete OpenAPI V3.1 specification.

---

## Staging Deployment (Render)

### Prerequisites
- Render account (https://render.com)
- Repository connected to Render

### Deploy via Render Blueprint

1. Go to Render Dashboard: https://dashboard.render.com
2. Click "New +" → "Web Service from Git"
3. Select repository: `socarrasv1-cmyk/nts-spanish-localization-api`
4. Select branch: `feature/v2.1-deployment`
5. Render automatically reads `render.yaml` configuration
6. Enter secret:
   - **Environment Variable:** `NTS_API_KEY`
   - **Value:** Strong random API key (32+ characters)
7. Click "Deploy"
8. Wait for health check to pass (~2-3 minutes)

### Verify Staging Deployment

```bash
# Health check
curl https://YOUR-SERVICE-NAME.onrender.com/healthz

# With valid token
curl -H "Authorization: Bearer YOUR-API-KEY" \
  https://YOUR-SERVICE-NAME.onrender.com/v2/sites
```

See `STAGING-DEPLOYMENT-HANDOFF.md` for complete deployment instructions.

---

## GPT Actions Connection

### Prerequisites
- Staging HTTPS endpoint deployed and responsive
- GPT Builder access (https://builder.openai.com)

### Steps

1. **Get OpenAPI Schema:**
   - Copy contents of `NTS-LOCALIZATION-ACTIONS-OPENAPI-V2.1-LIVE.json`
   - Update server URL to your real staging endpoint

2. **In GPT Builder:**
   - Click "Add → Actions"
   - Fill form:
     - **Name:** NTS Localization API V2.1
     - **Authentication Type:** API Key
     - **Auth Scheme:** Bearer
     - **Schema:** Paste OpenAPI JSON
     - **Secret:** Same `NTS_API_KEY` from Render

3. **Test Preview Prompts:**
   - List the verified NTS sites available through the localization API.
   - Get the approved Spanish URL mapping for /services/break-bulk-transport.php on HET.
   - Search Translation Memory for "Start Quote".
   - Validate /es/servicios/transporte-de-carga-fraccionada.php as the Spanish target.
   - Run PHP, structure, protected-token, English-residue, schema, and link validation.
   - Run final NTS page QA and do not mark READY unless score >=95 with zero blockers.

4. **Save as Draft Action** (do not publish yet)

See `STAGING-DEPLOYMENT-HANDOFF.md` for detailed instructions.

---

## Testing

### Run Unit Tests

```bash
# Local (requires Python 3.11+)
pip install -r requirements.txt
pytest tests/test_app.py -v

# Or with Docker
docker-compose run nts-localization-api pytest tests/test_app.py -v
```

### Test Coverage

Tests cover:
- ✅ Authentication (401/200 responses)
- ✅ Health check
- ✅ Data persistence
- ✅ Translation Memory workflow
- ✅ URL mapping validation
- ✅ All six validators
- ✅ QA publication gate
- ✅ Git staging safety
- ✅ Regression tests (T16, T18, T19, T21, T23, etc.)

### Live Staging Tests

Once deployed to Render:

```bash
API_KEY="your-staging-api-key"
ENDPOINT="https://your-service.onrender.com"

# Health check (no auth required)
curl $ENDPOINT/healthz

# List sites
curl -H "Authorization: Bearer $API_KEY" \
  $ENDPOINT/v2/sites

# Search Translation Memory
curl -X POST -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"source":"Start Quote","locale":"es-US"}' \
  $ENDPOINT/v2/tm/search

# Run page QA
curl -X POST -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"site_id":"het","artifact_id":"test"}' \
  $ENDPOINT/v2/qa/page
```

---

## Architecture

### Authentication & Security
- Bearer token on all protected endpoints (stored in `NTS_API_KEY`)
- `/healthz` intentionally public (health check)
- OpenAPI docs available (configurable in production)
- No secrets committed to repository

### Data Persistence
- JSON-based persistent store at `NTS_DATA_DIR`
- Thread-safe operations with locking
- Render persistent disk at `/var/data` (1 GB)
- Configurable TTL for temporary artifacts (default 168 hours)

### Staging-Only Design
- Git push disabled by default (`NTS_GIT_PUSH_ENABLED=false`)
- No auto-merge, no production deployment
- QA gate non-negotiable (score ≥95 + zero blockers)
- Translation Memory requires explicit human approval
- URL validation distinct from URL approval

---

## Important Safeguards

⚠️ **These safeguards cannot be weakened:**

1. **QA Publication Gate** — READY requires score ≥95 AND zero blocking failures. No exceptions.
2. **Translation Memory Approval** — New translations enter as proposals and require explicit reviewer approval. No auto-canonicalization.
3. **URL Validation vs. Approval** — A validated URL is NOT automatically approved. Approval is a separate human decision.
4. **Cross-Site Data Isolation** — No silent data leakage between sites (brand, phone, email, addresses, schema IDs, etc.).
5. **Protected Token Preservation** — PHP code, variables, constants, HTML IDs, contact info, analytics IDs must not change.
6. **Git Push Disabled** — `NTS_GIT_PUSH_ENABLED=false` by default. Enabling requires explicit owner approval.
7. **No Production Deploy** — This API is staging-only. No direct production website deployment.

---

## File Structure

```
nts-spanish-localization-api/
├── app/
│   ├── main.py                      # FastAPI application + 40+ endpoints
│   ├── security.py                  # Bearer token authentication
│   ├── store.py                     # Thread-safe persistent data store
│   ├── validators.py                # Six strict-mirror validators
│   ├── tm.py                        # Translation Memory service
│   └── git_stage.py                 # Git staging & safety
├── tests/
│   └── test_app.py                  # Comprehensive test suite
├── .github/
│   └── workflows/
│       ├── docker-build.yml         # Docker build & push
│       ├── tests.yml                # Unit tests & coverage
│       └── security.yml             # Security scanning
├── Dockerfile                        # Python 3.11-slim + PHP + Git
├── docker-compose.yml               # Local development setup
├── render.yaml                      # Render Blueprint (Starter plan)
├── .env.example                     # Configuration template
├── requirements.txt                 # Python dependencies
├── NTS-LOCALIZATION-ACTIONS-OPENAPI-V2.1-LIVE.json  # OpenAPI schema
├── README.md                        # This file
├── DEPLOYMENT.md                    # Deployment procedures
└── STAGING-DEPLOYMENT-HANDOFF.md   # Staging & GPT Actions handoff
```

---

## Troubleshooting

### Port 8000 Already in Use
```bash
# Find and kill process
lsof -i :8000
kill -9 <PID>

# Or use different port
docker-compose run -p 8001:8000 nts-localization-api
```

### Health Check Failing
```bash
# Check logs
docker-compose logs nts-localization-api

# Verify NTS_API_KEY is set
echo $NTS_API_KEY

# Test with curl
curl http://localhost:8000/healthz
```

### Git Push Returns 400
```
This is expected in staging. Push is disabled by default:
NTS_GIT_PUSH_ENABLED=false

To enable, set environment variable to "true" and restart.
Requires owner approval before enabling in production.
```

### Translation Memory Proposal Not Approved
```
Proposals require explicit /v2/tm/proposals/{id}/approve call.
To check pending proposals:
  curl -H "Authorization: Bearer $API_KEY" \
    "http://localhost:8000/v2/tm/proposals?status=proposed"
```

---

## Support & Documentation

- **API Docs (Interactive):** http://localhost:8000/docs
- **OpenAPI Schema:** `NTS-LOCALIZATION-ACTIONS-OPENAPI-V2.1-LIVE.json`
- **Deployment Guide:** `STAGING-DEPLOYMENT-HANDOFF.md`
- **Deployment Checklist:** `DEPLOYMENT.md`
- **Repository:** https://github.com/socarrasv1-cmyk/nts-spanish-localization-api

---

## Version

**NTS Localization API V2.1**

Released: 2026-08-13

### What's New in V2.1
- ✨ Translation Memory approval workflow
- ✨ Git staging for branch-based translation workflow
- ✨ Comprehensive OpenAPI schema for GPT Actions
- ✨ Render Blueprint deployment configuration
- ✨ Production-grade test suite
- ✨ Cross-site data isolation validators
- ✨ Staging-only safety enforcement

---

## License

Proprietary — NTS Spanish Intelligence Hub

---

## Contact

For questions or issues:
- GitHub Issues: https://github.com/socarrasv1-cmyk/nts-spanish-localization-api/issues
- NTS Support: https://www.nationwidetransportservices.com
