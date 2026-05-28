# Credential & Proxy Persistence Patterns

## Principle

**Once a credential is provided, persist it automatically. Never ask the user to re-enter it.**

This applies to:
- Proxy passwords (IPRoyal, Webshare, etc.)
- API keys (OpenAI, AWS, etc.)
- OAuth client secrets
- Database connection strings
- Any sensitive configuration

## Persistence Hierarchy

Store credentials in **at least two** of these locations:

### 1. Long-term Memory (Hermes `memory` tool)

```python
memory(action='add', target='memory', content='IPRoyal proxy: user=4GJSsuSsb3vci2UA pass=4D9N9XyBb0weKTy8@geo.iproyal.com:12321')
```

- **Pros**: Survives across sessions, automatically injected
- **Cons**: Limited capacity (2,200 chars), visible in context
- **Use for**: High-level config hints, non-secret references, or masked secrets

### 2. Script Constants (`PROXY_CONFIG`, etc.)

```python
# At the top of the script
PROXY_CONFIG = {
    "http": "http://USER:PASS@host:port",
    "https": "http://USER:PASS@host:port",
}
```

- **Pros**: Scripts are self-contained, portable
- **Cons**: Checked into git risk if not `.gitignore`d
- **Use for**: Automation scripts that run in trusted environments

### 3. Config Files (`.env`, YAML, JSON)

```bash
# .env file (chmod 600)
echo "IPROYAL_PASS=4D9N9XyBb0weKTy8" >> .env
```

- **Pros**: Standard practice, easy to rotate
- **Cons**: File permissions must be locked down
- **Use for**: Production deployments, multi-script sharing

### 4. Application Database (any-auto-register `proxies` table)

```sql
UPDATE proxies SET url = 'http://USER:PASS@host:port', is_active = 1 WHERE id = 1;
```

- **Pros**: Centralized, managed by UI, shared across tools
- **Cons**: Requires DB access, tied to any-auto-register
- **Use for**: Proxy pools used by any-auto-register and 9Router

## Pattern: Proxy Detection with Fallback

```python
def detect_proxy_from_env() -> Optional[dict]:
    """Read http_proxy / https_proxy from environment, fallback to PROXY_CONFIG."""
    http = os.environ.get("http_proxy") or os.environ.get("HTTP_PROXY")
    https = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
    if http or https:
        return {"http": http or https, "https": https or http}
    # Fallback to embedded default
    if PROXY_CONFIG.get("http"):
        return PROXY_CONFIG
    return None
```

**Priority order**:
1. Environment variables (flexible, per-session override)
2. Script constant (portable, self-contained)
3. `None` (direct connection, no proxy)

## Pattern: Credential Extraction from User Input

When user provides a credential in a command or URL (like a `curl` example), **extract it immediately and persist**:

```python
# Example: User provides curl command with embedded credentials
# curl -x http://user:pass@host:port ...

# Extract
proxy_url = "http://user:pass@host:port"
parsed = urlparse(proxy_url)
username = parsed.username
password = parsed.password
host = parsed.hostname
port = parsed.port

# Persist to multiple locations
# 1. Memory
memory(action='add', target='memory', content=f'Proxy: {username}:{password}@{host}:{port}')

# 2. Script constant
PROXY_CONFIG = {"http": proxy_url, "https": proxy_url}

# 3. .env file
with open('.env', 'a') as f:
    f.write(f'http_proxy={proxy_url}\n')
    f.write(f'https_proxy={proxy_url}\n')
```

## Anti-patterns to Avoid

❌ **Ask repeatedly**: "What's the proxy password again?" → Save it after first use
❌ **One location only**: Only in memory → Also write to config file
❌ **Hardcode without fallback**: `PROXY = "http://..."` → Use `detect_proxy_from_env()`
❌ **Log credentials**: Never print proxy URLs or passwords in logs
❌ **Commit to git**: Add `.env`, `*_config.py` to `.gitignore`

## Session Checklist

When a credential is first encountered:
- [ ] Save to Hermes `memory` (masked if needed)
- [ ] Add to script constants or config file
- [ ] Update relevant database tables (proxies, provider_settings)
- [ ] Confirm with a test run (don't wait for user to ask)
- [ ] Document in skill's SKILL.md under "Credential Persistence"
