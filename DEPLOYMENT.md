# NTS Localization API V2.1 — Deployment Checklist

## Pre-Deployment Verification

- [ ] All environment variables configured in `.env`
- [ ] `NTS_API_KEY` set to a strong random value
- [ ] `NTS_DATA_DIR` writable by the container
- [ ] `NTS_GIT_REPO_PATH` writable by the container
- [ ] Git provider credentials set (if push is enabled)
- [ ] Docker image built and tested locally
- [ ] All unit tests passing
- [ ] No blocking QA issues in staging packages

## Deployment Steps

### 1. Build Docker Image
```bash
docker build -t ghcr.io/socarrasv1-cmyk/nts-spanish-localization-api:v2.1.0 .
```

### 2. Push to Registry
```bash
docker push ghcr.io/socarrasv1-cmyk/nts-spanish-localization-api:v2.1.0
```

### 3. Deploy to Staging Environment
```bash
# Update deployment manifests with new image tag
# Apply Kubernetes manifests or docker-compose configuration
docker-compose -f docker-compose.yml up -d
```

### 4. Run Smoke Tests
```bash
curl http://localhost:8000/healthz
# Expected response: {"status": "ok", "service": "nts-localization-api", "version": "2.1.0"}
```

### 5. Verify Git Staging Safety
- Confirm `NTS_GIT_PUSH_ENABLED=false` in production
- Verify staging branches are created but not pushed without explicit request

### 6. Monitor Logs
```bash
docker-compose logs -f nts-localization-api
```

## Rollback Procedure

```bash
docker-compose down
# Revert to previous image tag in docker-compose.yml
docker-compose up -d
```

## Post-Deployment Monitoring

- Monitor API response times and error rates
- Verify Translation Memory operations
- Check Git staging branch creation and metadata
- Validate Bearer token authentication on all endpoints

## Notes

- **Staging-Only**: This deployment is staging-only with no production deployment without explicit human approval
- **No Auto-Merge**: Git staging never merges branches automatically
- **Data Retention**: All artifacts are immutable and permanently retained in `NTS_DATA_DIR`
- **Bearer Token**: All API clients must include valid `Authorization: Bearer {NTS_API_KEY}` header
