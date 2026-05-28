# Proxy Architecture Gap in any-auto-register (2026-05-26)

## Summary

any-auto-register has TWO proxy mechanisms, but the registration flow doesn't use the proxy pool — it relies solely on the API payload, creating a gap where registration tasks run without proxy even when proxies are configured.

## The Gap

| Component | Proxy Source | Behavior |
|-----------|-------------|----------|
| `check_valid()` (plugin.py) | `proxy_pool.get_next()` | Auto-selects proxy from DB ✅ |
| **Registration flow** | `config.proxy` ← API payload | Falls through to `None` if payload has `null` ❌ |

## Code Path

```
Frontend POST /api/tasks/register  { "proxy": null, ... }
  → application/tasks.py: create_register_task(payload) — payload passed as-is
  → services/task_runtime.py — ZERO proxy references
  → core/base_platform.py: _make_executor() → PlaywrightExecutor(proxy=self.config.proxy)
  → self.config.proxy = None  # ← never resolved to proxy_pool
```

The `proxy_pool` (core/proxy_pool.py) is only imported in `plugin.py:check_valid()` and never in registration path.

## Database State (as of discovery)

```sql
-- proxies table (both active)
id=2: http://100.64.247.23:7890         (cn, is_active=1)
id=3: http://USER:PASS_country-us@geo.iproyal.com:12321  (iproyal-us, is_default=1)
```

Both proxies fully functional but registration never touches them.

## Impact

1. Registration tasks run from the server's direct IP
2. OpenAI detects datacenter IP → 400 on add-phone/send (virtual number rejection)
3. Cloudflare 403 blocks on chatgpt.com API calls
4. All recent task failures (0/5 success) trace back to missing proxy

## Fix Direction

In `core/base_platform.py:_make_executor()` or during `RegisterConfig` construction:

```python
# Pseudocode fix
proxy = self.config.proxy
if not proxy:
    from core.proxy_pool import proxy_pool
    proxy = proxy_pool.get_next()
```

Or higher up in the call chain, resolve the proxy before passing to executor.

## Related

- account_selection → add_phone loop (also caused by no proxy → OpenAI rejects phone)
- add_phone skip dead loop (fixed separately in browser_register.py)
