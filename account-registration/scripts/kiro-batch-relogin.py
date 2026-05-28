#!/usr/bin/env python3
"""Batch Kiro browser re-login — processes all accounts without refreshToken via subprocess workers."""
import os, sys, json, sqlite3, subprocess, time

DB_PATH = os.getenv("ANY_AUTO_REGISTER_DB", "/root/src/any-auto-register/account_manager.db")
VENV_PY = "/root/src/any-auto-register/.venv/bin/python3"
WORKER = os.path.join(os.path.dirname(__file__), "kiro-browser-relogin.py")

db = sqlite3.connect(DB_PATH); c = db.cursor()
c.execute("""
    SELECT a.id, a.email FROM accounts a
    WHERE a.platform='kiro' AND a.password IS NOT NULL AND a.password != ''
    AND (SELECT value FROM account_credentials WHERE account_id=a.id AND provider_name='kiro' AND key='refreshToken') IS NULL
    ORDER BY a.id
""")
accounts = [(r[0], r[1]) for r in c.fetchall()]
db.close()

print(f"Accounts to process: {len(accounts)}")
results = []
for aid, email in accounts:
    print(f"\n[{'='*30}]\n[{aid}] {email}", flush=True)
    try:
        r = subprocess.run([VENV_PY, WORKER, str(aid)], capture_output=True, text=True, timeout=300,
            env={**os.environ, "DISPLAY": ":99"}, cwd=os.path.dirname(DB_PATH))
        # Extract JSON result from stdout
        for line in r.stdout.strip().split('\n'):
            if line.startswith('{"id":'):
                results.append(json.loads(line))
                break
        else:
            results.append({"id": aid, "email": email, "success": False, "error": f"No JSON; rc={r.returncode}"})
    except subprocess.TimeoutExpired:
        results.append({"id": aid, "email": email, "success": False, "error": "Timeout (300s)"})
    except Exception as e:
        results.append({"id": aid, "email": email, "success": False, "error": str(e)[:200]})
    time.sleep(3)

ok = [r for r in results if r.get("success")]
fail = [r for r in results if not r.get("success")]
print(f"\n{'='*30}\nSUMMARY: {len(ok)}/{len(results)} success")
for r in ok: print(f"  ✅ [{r['id']}] {r['email']}")
for r in fail: print(f"  ❌ [{r['id']}] {r['email']} — {r.get('error','')[:80]}")
with open("/root/kiro_relogin_results.json", "w") as f:
    json.dump(results, f, indent=2)
