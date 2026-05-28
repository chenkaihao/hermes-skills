# Kiro Account Status — 2026-05-20 (ALL SUSPENDED)

## Summary

**26/26 Kiro accounts AWS-suspended.** A dramatic reversal from 2026-05-17 when all 26 were valid (100%).

## 9Router Health Check Data

All 26 connections show `testStatus: "unavailable"` with identical error:

```
[403]: {"message":"Your User ID (XXX) temporarily is suspended"}
```

| Status | Count | Accounts |
|--------|-------|----------|
| unavailable (403) | 26 | ALL |

## Timeline

| Date | Valid | Dead | Notes |
|------|-------|------|-------|
| 2026-05-12 | 9/21 (42.9%) | 12 | CodeWhisperer 403 — later found to be false negatives |
| 2026-05-17 | 26/26 (100%) | 0 | Chat API (`/chat`) validation, IPRoyal US Hillside proxy |
| **2026-05-20** | **0/26 (0%)** | **26** | All AWS 403 "temporarily suspended" |

## Death Reason Classification

Survival monitor initially classified these as "超时" / "Expecting value" (empty chat API response). After adding 9Router health fallback (`providerConnections.testStatus` + `lastError`), correctly reclassified as **封号** (AWS 403 suspended).

## Impact

- **9Router**: All Kiro connections show as unavailable; `kr/claude-haiku-4.5` model returns errors
- **tokenfree.cc**: No Kiro models available to users
- **Survival monitor**: 26 deaths attributed to 封号

## Remaining Unknowns

- Exact suspension trigger (mass ban wave? proxy detection? usage pattern?)
- Whether accounts can be re-registered with same email/domain
- Whether new registrations (different emails) will succeed
