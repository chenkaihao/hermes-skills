#!/usr/bin/env python3
"""
Single-account health check: OAuth refresh → New API LLM call → persist tokens.
Usage: python3 health_check_single.py <email>
       python3 health_check_single.py stephaniejenkins@qhvip.cc

Chain: OAuth refresh (auth.openai.com) → token update → New API (port 3000) →
       9Router routing → IPRoyal proxy → upstream Codex model.

CRITICAL: Do NOT test via api.openai.com — free accounts get 429 there.
Use the actual production endpoint (localhost:3000) with New API key.
"""
import sqlite3, json, time, sys, requests

# === Config ===
NEW_API = "http://localhost:3000/v1/chat/completions"
API_KEY = "uL6KoYoLALlLfuPnsKtZi91PnjoCjRJZESGYThukUX1EGzyH"
NINE_ROUTER_DB = "/root/src/9router-data/db/data.sqlite"
CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"  # From 9router/src/lib/oauth/constants/oauth.js
OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
TEST_MODELS = ["cx/gpt-5.5", "cx/gpt-5.3-codex-xhigh", "cx/gpt-5.4"]
TIMEOUT = 30


def get_account(email):
    conn = sqlite3.connect(NINE_ROUTER_DB)
    cur = conn.cursor()
    cur.execute("SELECT id, provider, data FROM providerConnections WHERE email = ?", (email,))
    row = cur.fetchone()
    conn.close()
    return (row[0], row[1], json.loads(row[2])) if row else None


def update_db(email, updates):
    conn = sqlite3.connect(NINE_ROUTER_DB)
    cur = conn.cursor()
    cur.execute("SELECT data FROM providerConnections WHERE email = ?", (email,))
    row = cur.fetchone()
    if row:
        d = json.loads(row[0])
        d.update(updates)
        d["lastUsedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
        cur.execute("UPDATE providerConnections SET data = ?, updatedAt = datetime('now') WHERE email = ?",
                     (json.dumps(d), email))
        conn.commit()
    conn.close()


def refresh_oauth(refresh_token):
    """OAuth refresh — returns (success, new_access_token, new_refresh_token, error)."""
    t0 = time.time()
    try:
        r = requests.post(OAUTH_TOKEN_URL, json={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": CODEX_CLIENT_ID,
        }, headers={"Content-Type": "application/json"}, timeout=20)
        elapsed = time.time() - t0
        
        if r.status_code == 200:
            tokens = r.json()
            return True, tokens["access_token"], tokens.get("refresh_token"), f"{elapsed:.1f}s"
        else:
            err = r.json().get("error", {}).get("message", f"HTTP {r.status_code}")
            return False, None, None, f"{elapsed:.1f}s — {err}"
    except Exception as e:
        return False, None, None, f"{time.time()-t0:.1f}s — {e}"


def llm_call():
    """Real LLM call through New API → 9Router → proxy → upstream."""
    for model in TEST_MODELS:
        t0 = time.time()
        try:
            r = requests.post(NEW_API, json={
                "model": model,
                "messages": [{"role": "user", "content": "Say hello in one word"}],
                "max_tokens": 5,
            }, headers={"Authorization": f"Bearer {API_KEY}"}, timeout=TIMEOUT)
            elapsed = time.time() - t0
            
            if r.status_code == 200:
                body = r.json()
                reply = body.get("choices", [{}])[0].get("message", {}).get("content", "")
                return True, model, reply, f"{elapsed:.1f}s"
            else:
                err = r.json().get("error", {}).get("message", f"HTTP {r.status_code}")
                continue  # Try next model
        except Exception as e:
            continue
    return False, None, None, f"all models failed"


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 health_check_single.py <email>")
        sys.exit(1)
    
    email = sys.argv[1]
    print(f"Health Check: {email}")
    
    acct = get_account(email)
    if not acct:
        print(f"❌ Account {email} not found in 9Router")
        sys.exit(1)
    
    acc_id, provider, data = acct
    rt = data.get("refreshToken", "")
    print(f"  ID: {acc_id[:16]}...  provider: {provider}  RT: {'✅' if rt else '❌'}")
    
    # Step 1: OAuth refresh
    print("\n[1/2] OAuth refresh...", end=" ", flush=True)
    if rt:
        ok, new_at, new_rt, msg = refresh_oauth(rt)
        if ok:
            print(f"✅ ({msg})")
            update_db(email, {
                "accessToken": new_at,
                "refreshToken": new_rt or rt,
                "testStatus": "available",
                "backoffLevel": 0,
                "errorCode": None,
                "lastError": None,
            })
        else:
            print(f"❌ {msg}")
            update_db(email, {"testStatus": "unavailable", "lastError": msg})
    else:
        print("⚠️ no refreshToken — skip")
    
    # Step 2: LLM call through production chain
    print("[2/2] LLM call (New API → 9Router → proxy → upstream)...", end=" ", flush=True)
    ok, model, reply, msg = llm_call()
    if ok:
        print(f"✅ {model} ({msg}): \"{reply}\"")
    else:
        print(f"❌ {msg}")
    
    # Final state
    acct = get_account(email)
    if acct:
        _, _, data = acct
        print(f"\nFinal: testStatus={data.get('testStatus')} backoff={data.get('backoffLevel')}")


if __name__ == "__main__":
    main()
