#!/usr/bin/env python3
"""Kiro Browser Re-login Worker — re-authenticates a single Kiro account via headed Camoufox OAuth flow.
Usage: python kiro-browser-relogin.py <account_id>
Reads email+password from any-auto-register DB, produces JSON result.
Requires: Xvfb :99 running, camoufox + playwright in venv, IPRoyal proxy.
"""

import os, sys, time, json, sqlite3, hashlib, base64, uuid, re
from urllib.parse import urlencode
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread, Event
from urllib.parse import urlparse, parse_qs

AID = int(sys.argv[1])
DB_PATH = os.getenv("ANY_AUTO_REGISTER_DB", "/root/src/any-auto-register/account_manager.db")
os.environ.setdefault("DISPLAY", ":99")

# IPRoyal US residential proxy — MUST use split username/password format for Camoufox
PROXY_SERVER = "http://geo.iproyal.com:12321"
PROXY_USER = "4GJSsuSsb3vci2UA"
PROXY_PASS = "4D9N9XyBb0weKTy8_country-us"  # _country-us suffix routes to US node

# Read account from DB
db = sqlite3.connect(DB_PATH)
c = db.cursor()
c.execute("SELECT email, password FROM accounts WHERE id=?", (AID,))
row = c.fetchone()
db.close()
if not row:
    print(json.dumps({"id": AID, "success": False, "error": "Account not found"}))
    sys.exit(1)
EMAIL, PASSWORD = row

# ─── OTP callback (for qhvip.cc CF Worker mailboxes) ─────────────────────────
def otp_cb():
    from curl_cffi import requests as cr
    try:
        r = cr.post("https://mail.qhvip.cc/api/messages/latest-otp",
            json={"email": EMAIL}, timeout=30, impersonate="chrome131")
        if r.status_code == 200:
            code = r.json().get("code") or r.json().get("otp") or ""
            if code: return str(code)
    except: pass
    try:
        r2 = cr.post("https://mail.qhvip.cc/api/messages",
            json={"email": EMAIL, "limit": 5}, timeout=30, impersonate="chrome131")
        if r2.status_code == 200:
            for msg in r2.json().get("messages", []):
                m = re.search(r'\b(\d{6})\b', msg.get("body", ""))
                if m: return m.group(1)
    except: pass
    return None

# ─── OIDC Callback Server ────────────────────────────────────────────────────
class CallbackServer:
    def __init__(self, s): self.state = s; self.ev = Event(); self.code = None; self.srv = None; self.port = None
    def start(self):
        parent = self
        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                qs = parse_qs(urlparse(self.path).query)
                if qs.get("code"): parent.code = qs["code"][0]; parent.ev.set(); self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
                else: self.send_response(400); self.end_headers()
            def log_message(self, *a): pass
        for p in range(18765, 18800):
            try: self.srv = HTTPServer(("127.0.0.1", p), H); self.port = p; break
            except OSError: continue
        Thread(target=self.srv.serve_forever, daemon=True).start()
    @property
    def uri(self): return f"http://127.0.0.1:{self.port}/oauth/callback"
    def wait(self): self.ev.wait(5); return self.code
    def close(self):
        if self.srv: self.srv.shutdown()

# ─── HTTP helper ─────────────────────────────────────────────────────────────
def http_post(url, body):
    from curl_cffi import requests as cr
    r = cr.post(url, json=body, headers={"content-type": "application/json"},
        impersonate="chrome131", timeout=30,
        proxies={"https": f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_SERVER.split('://')[1]}",
                 "http": f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_SERVER.split('://')[1]}"})
    if r.status_code != 200: raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
    return r.json()

# ─── Main Flow ───────────────────────────────────────────────────────────────
result = {"id": AID, "email": EMAIL, "success": False, "error": ""}
OIDC = "https://oidc.us-east-1.amazonaws.com"
START_URL = "https://view.awsapps.com/start"  # Correct issuer URL for Kiro
SCOPES = ["codewhisperer:completions", "codewhisperer:analysis", "codewhisperer:conversations",
          "codewhisperer:transformations", "codewhisperer:taskassist"]

try:
    from camoufox.sync_api import Camoufox
    print(f"[{AID}] {EMAIL} — launching browser...", flush=True)

    with Camoufox(headless=False,
        proxy={"server": PROXY_SERVER, "username": PROXY_USER, "password": PROXY_PASS},
        os=["windows"]) as browser:

        print(f"[{AID}] browser OK", flush=True)

        # Step 1: Register OIDC client
        state, verifier = uuid.uuid4().hex, uuid.uuid4().hex + uuid.uuid4().hex
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")

        cb = CallbackServer(state)
        cb.start()

        reg = http_post(f"{OIDC}/client/register", {
            "clientName": "Kiro IDE", "clientType": "public", "scopes": SCOPES,
            "grantTypes": ["authorization_code", "refresh_token"],
            "redirectUris": [cb.uri], "issuerUrl": START_URL,
        })
        cid, csec = reg["clientId"], reg["clientSecret"]
        print(f"[{AID}] OIDC client registered", flush=True)

        # Step 2: Authorize (AWS Builder ID login happens here)
        auth_url = f"{OIDC}/authorize?" + urlencode({
            "response_type": "code", "client_id": cid, "redirect_uri": cb.uri,
            "scopes": ",".join(SCOPES), "state": state,
            "code_challenge": challenge, "code_challenge_method": "S256",
        })

        page = browser.new_page()
        page.goto(auth_url, wait_until="domcontentloaded", timeout=60000)

        t0 = time.time()
        while time.time() - t0 < 180:
            if cb.ev.is_set(): break

            # Fill email
            try:
                el = page.query_selector('input[type="email"],input[placeholder*="username@example.com"]')
                if el and el.is_visible():
                    el.click(); el.fill(""); el.type(EMAIL, delay=50)
                    for b in ["Next", "Continue"]:
                        try: page.click(f'button:has-text("{b}")', timeout=3000); break
                        except: pass
                    page.wait_for_timeout(3000)
            except: pass

            # Fill password
            try:
                el = page.query_selector('input[type="password"]')
                if el and el.is_visible():
                    el.click(); el.fill(""); el.type(PASSWORD, delay=50)
                    for b in ["Sign in", "Continue"]:
                        try: page.click(f'button:has-text("{b}")', timeout=3000); break
                        except: pass
                    page.wait_for_timeout(3000)
            except: pass

            # Fill OTP
            try:
                el = page.query_selector('input[inputmode="numeric"]')
                if el and el.is_visible():
                    code = otp_cb()
                    if code:
                        el.click(); el.fill(code)
                        for b in ["Verify", "Submit", "Continue"]:
                            try: page.click(f'button:has-text("{b}")', timeout=2000); break
                            except: pass
                        page.wait_for_timeout(3000)
            except: pass

            # Click Trust/Allow/Authorize
            for lbl in ["Trust", "Allow access", "Allow", "Authorize", "Continue"]:
                try:
                    btn = page.locator(f'text="{lbl}"').last
                    if btn.is_visible(): btn.click(timeout=2000); page.wait_for_timeout(500); break
                except: pass
            page.wait_for_timeout(500)

        auth_code = cb.wait()
        cb.close()

        if not auth_code:
            result["error"] = f"No auth code, URL: {page.url[:80]}"
        else:
            # Step 3: Exchange code for tokens
            tokens = http_post(f"{OIDC}/token", {
                "clientId": cid, "clientSecret": csec, "grantType": "authorization_code",
                "redirectUri": cb.uri, "code": auth_code, "codeVerifier": verifier,
            })

            if tokens.get("refreshToken"):
                db = sqlite3.connect(DB_PATH); cur = db.cursor()
                for k in ["refreshToken", "accessToken", "clientId", "clientSecret"]:
                    v = tokens.get(k) or (cid if k == "clientId" else csec if k == "clientSecret" else "")
                    if v:
                        cur.execute("""
                            INSERT INTO account_credentials (account_id, provider_name, key, value, created_at, updated_at)
                            VALUES (?, 'kiro', ?, ?, datetime('now'), datetime('now'))
                            ON CONFLICT(account_id, provider_name, key) DO UPDATE
                            SET value=excluded.value, updated_at=datetime('now')
                        """, (AID, k, v))
                db.commit(); db.close()
                result["success"] = True
                print(f"[{AID}] ✅ SUCCESS — refreshToken saved!", flush=True)
            else:
                result["error"] = "No refreshToken in token response"

        page.close()

except Exception as e:
    result["error"] = str(e)[:300]
    import traceback; traceback.print_exc()
    print(f"[{AID}] ❌ {result['error']}", flush=True)

print(json.dumps(result))
