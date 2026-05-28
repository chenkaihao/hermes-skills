# Kiro Pricing Policy Research (2026-05-12)

## Sources
- Kiro pricing page: `https://kiro.dev/pricing`
- Amazon Q Developer pricing: `https://aws.amazon.com/q/developer/pricing/`
- CSS/text extraction via browser console + screenshot analysis

## Kiro Plan Structure

| Plan | Price | Credits/Month | Models |
|------|-------|---------------|--------|
| **KIRO FREE** | $0 | **50** | Open weight + Claude Sonnet 4.5 |
| **KIRO PRO** | $20 | 1,000 | Premium models, $0.04/credit overage |
| **KIRO PRO+** | $40 | 2,000 | Premium models, $0.04/credit overage |
| **KIRO POWER** | $200 | 10,000 | Premium models |

## Sign-up Bonus

- $20 credit applied to first paid plan upgrade
- Requires valid credit card
- Pro-rated: if upgrade mid-month, credit is proportional
- Available with social login or AWS Builder ID (NOT AWS Identity Center)

## Amazon Q Developer Free Tier (Kiro's Underlying Service)

From `https://aws.amazon.com/q/developer/pricing/`:

| Feature | Free Tier | Pro Tier ($19/user/mo) |
|---------|-----------|------------------------|
| IDE plugins & CLI | ✅ | ✅ |
| Agentic requests | **50/month** | Included (with limits) |
| Java transformation | 1,000 LOC/month | 4,000 LOC/month |
| Premium models | ❌ | ✅ |
| IP indemnity | ❌ | ✅ |
| Admin dashboard | ❌ | ✅ |

Key quote from AWS page:
> "Amazon Q Developer offers a perpetual Free Tier with monthly limits available to users logged in as an AWS Identity and Access Management (IAM) user or AWS Builder ID user."

> "Free Tier limits in the IDE are available only to Builder ID users."

## The 500 freeTrial Mystery

### What the 500 is NOT
- NOT on Kiro pricing page
- NOT on Amazon Q Developer pricing page
- NOT a Kiro plan feature (all plans above are per-month, not one-time)
- NOT the sign-up bonus ($20 credit is billing discount, not extra credits)

### What the 500 LIKELY was
- A **discontinued AWS Q Developer promotional trial** that gave 500 one-time credits to new Builder ID users
- Active for accounts registered **before approximately May 7, 2026**
- Discontinued for accounts registered **on/after May 8, 2026**

### Evidence
| Registration Date | Accounts | freeTrialStatus |
|------------------|----------|-----------------|
| Apr 27 - May 6 | 6 accounts | ACTIVE (500 credits) |
| May 8 | 7 accounts | None (0 credits) |

All accounts are on `KIRO FREE` plan (50 credits base). The 500 freeTrial is an additional one-time grant layered on top.

### AWS Q API Response Difference

**With freeTrial (ACTIVE)**:
```json
{
  "usageBreakdownList": [{
    "resourceType": "CREDIT",
    "usageLimitWithPrecision": 50.0,
    "freeTrialInfo": {
      "freeTrialStatus": "ACTIVE",
      "usageLimit": 500,
      "currentUsage": 0,
      "freeTrialExpiry": 1780125330.147
    }
  }]
}
```

**Without freeTrial (None)**:
```json
{
  "usageBreakdownList": [{
    "resourceType": "CREDIT",
    "usageLimitWithPrecision": 50.0,
    "freeTrialInfo": null
  }]
}
```

## Takeaways

1. **50 credits is the normal Kiro Free Plan quota** — NOT a bug or "unactivated" state
2. **500 freeTrial was a temporary promotion** — now discontinued
3. **Login/OTP/token-refresh cannot change this** — it's a server-side policy decision
4. **To get more credits**: upgrade to PRO ($20/mo, 1,000cr), PRO+ ($40/mo, 2,000cr), or POWER ($200/mo, 10,000cr)
5. **For free usage with 500 credits**: use accounts registered before May 7, 2026 (IDs: 7, 9, 10, 11, 12, 15)
