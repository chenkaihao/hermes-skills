# Kiro Account Status — 2026-05-26 (generateAssistantResponse validation)

## Test method
- **Endpoint**: `POST q.us-east-1.amazonaws.com/generateAssistantResponse`
- **Proxy**: IPRoyal US residential (`geo.iproyal.com:12321`, `_country-us` suffix)
- **Flow**: Token refresh (OIDC) → generateAssistantResponse (chat test)
- **NOT used**: `/chat` (false positive — returns 200 + UnknownOperationException)

## Results

| Category | Count | % | Detail |
|----------|-------|---|--------|
| ✅ Valid | 0 | 0% | None |
| 🚫 Suspended | 25 | 55.6% | Token refresh OK, but chat returns 403 "User ID temporarily suspended" |
| ❌ No refreshToken → chat 403 | 20 | 44.4% | Tested via existing accessToken; all return 403 suspended |
| 🚫 TLS/other errors | 3 | 6.7% | #10 TLS error, #28 usage query failed, #49 usage=0+403 |

### All 45 accounts fail on generateAssistantResponse

**Accounts with refreshToken (25)**: IDs 9-12, 15, 22-27, 49, 52, 53, 56, 58, 62, 64, 66, 69, 73, 74, 77, 80
- Token refresh ✅, usage query ✅
- `generateAssistantResponse` → 403 "User ID temporarily suspended"

**Accounts without refreshToken (20)**: IDs 44-48, 50, 54, 55, 57, 59-61, 63, 65, 67, 68, 71, 75, 76, 79
- **CORRECTED 2026-05-26**: Previously marked as "accessToken expired" without testing. When tested via existing accessToken against `generateAssistantResponse`, ALL return 403 "suspended." They're not just expired — they're banned same as the RT accounts.
- All have passwords → candidates for browser re-login (mail.qhvip.cc DNS fixed 2026-05-26, ready for re-auth)

### Correction: "无RT即跳过chat测试" bug
The original `check_account()` code had a critical flaw: accounts without `refreshToken` were marked `valid=True` based on `bool(access_token)` existence alone, without ever testing `generateAssistantResponse`. This produced 20 false positives. Fixed by routing no-RT accounts through the same chat test path.

## Previous false positive (2026-05-17)
A prior test using the `/chat` endpoint reported 45/45 valid. This was incorrect:
- `/chat` returns HTTP 200 for ALL requests (including invalid tokens)
- Body contains `UnknownOperationException`, not actual chat response
- Only `generateAssistantResponse` is authoritative
