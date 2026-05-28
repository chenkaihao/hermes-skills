# Account Health Check Configuration

## Endpoints (production chain)

| Component | Endpoint | Notes |
|-----------|----------|-------|
| **OAuth Refresh** | `https://auth.openai.com/oauth/token` | grant_type=refresh_token |
| **New API** | `http://localhost:3000/v1/chat/completions` | Docker container `new-api` |
| **9Router** | `http://localhost:9000` (UI) | Routing engine reads from SQLite |
| **Upstream** | Via IPRoyal proxy | `geo.iproyal.com:12321`, `_country-us` suffix |

## OAuth Configuration

- **Codex client_id**: `app_EMoamEEZ73f0CkXaXp7hrann`
  - Source: `/root/src/9router/src/lib/oauth/constants/oauth.js` → `CODEX_CONFIG.clientId`
  - Also defined as `OPENAI_CONFIG.clientId` (same value)

## New API Configuration

- **Container**: `calciumion/new-api:v1.0.0-rc.6`
- **Data volume**: `/root/new-api/data` → container `/data`
- **Database**: `/root/new-api/data/one-api.db` (SQLite)
- **Main API key**: `uL6KoYoLALlLfuPnsKtZi91PnjoCjRJZESGYThukUX1EGzyH` (token id=1, name="khchen_api_key_1")
- **Channel**: id=1, type=1, name="9Router主渠道" — routes Codex models through 9Router

## 9Router Configuration

- **Database**: `/root/src/9router-data/db/data.sqlite`
- **Table**: `providerConnections` — columns: id, provider, authType, name, email, priority, isActive, data, createdAt, updatedAt
- **Codex provider field**: `"codex"` (lowercase)
- **data JSON** keys: accessToken, refreshToken, idToken, testStatus, backoffLevel, displayName, proxyId, providerSpecificData, modelLock_*, errorCode, lastError, lastUsedAt, consecutiveUseCount...

## ⚠️ CRITICAL: Correct health check endpoint

**WRONG**: `POST https://api.openai.com/v1/chat/completions` — free accounts get 429 quota exceeded
**CORRECT**: `POST http://localhost:3000/v1/chat/completions` with New API key → routes through 9Router → proxy → upstream

The survival monitor script (`monitor_survival.py`) currently uses `http://localhost:9000/v1/chat/completions` which is the 9Router UI port (returns 404 for API calls). The correct port is **3000** (New API).
