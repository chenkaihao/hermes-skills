#!/usr/bin/env python3
"""账号存活观测系统 — 每 6 小时运行一次，通过真实 LLM 调用判定死活，生成 HTML 报表。"""
import sqlite3, json, time, requests, sys
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict
from pathlib import Path

DB = "/root/src/9router-data/db/data.sqlite"
REPORT = "/var/www/html/report/survival.html"
API = "http://localhost:9000/v1/chat/completions"
TIMEOUT = 20
CONCURRENCY = 3  # 并发验证数
MODEL_MAP = {"codex": "cx/gpt-5.5", "kiro": "kr/claude-haiku-4.5"}


# ── 数据库操作 ────────────────────────────────────────
def load_accounts():
    conn = sqlite3.connect(DB)
    rows = conn.execute("""
        SELECT LOWER(email), provider, isActive, data
        FROM providerConnections WHERE isActive=1
    """).fetchall()
    conn.close()
    accounts = []
    for email, provider, active, data_json in rows:
        try:
            data = json.loads(data_json)
        except:
            data = {}
        domain = email.split("@")[-1] if "@" in email else "unknown"
        accounts.append({
            "email": email, "provider": provider, "domain": domain,
            "rt": data.get("refreshToken", ""),
            "at": data.get("accessToken", ""),
        })
    return accounts


def load_lifespan():
    conn = sqlite3.connect(DB)
    rows = conn.execute("SELECT email, status, first_seen, last_alive, died_at, death_reason, check_count FROM account_lifespan").fetchall()
    conn.close()
    return {r[0]: {"status": r[1], "first_seen": r[2], "last_alive": r[3],
                   "died_at": r[4], "death_reason": r[5], "check_count": r[6]} for r in rows}


def upsert_lifespan(email, provider, domain, alive, reason, now):
    conn = sqlite3.connect(DB)
    row = conn.execute("SELECT status, check_count FROM account_lifespan WHERE email=?", (email,)).fetchone()
    if row:
        old_status, count = row
        if alive:
            conn.execute("UPDATE account_lifespan SET last_alive=?, status='alive', death_reason=NULL, check_count=? WHERE email=?",
                         (now, count + 1, email))
        else:
            if old_status == "alive":
                conn.execute("UPDATE account_lifespan SET died_at=?, status='dead', death_reason=?, check_count=? WHERE email=?",
                             (now, reason[:100], count + 1, email))
            else:
                conn.execute("UPDATE account_lifespan SET check_count=? WHERE email=?", (count + 1, email))
    else:
        status = "alive" if alive else "dead"
        conn.execute("""INSERT INTO account_lifespan (email, provider, domain, first_seen, last_alive, died_at, status, death_reason, check_count)
                        VALUES (?,?,?,?,?,?,?,?,1)""",
                     (email, provider, domain, now, now if alive else None, now if not alive else None, status, reason[:100] if not alive else None))
    conn.commit(); conn.close()


# ── 验证 ──────────────────────────────────────────────
def check_one(acc):
    model = MODEL_MAP.get(acc["provider"], "cx/gpt-5.5")
    try:
        r = requests.post(API,
            json={"model": model, "messages": [{"role": "user", "content": "1+1"}], "max_tokens": 3},
            headers={"Authorization": "Bearer sk-9router"}, timeout=TIMEOUT)
        if r.status_code == 200 and "choices" in r.json():
            return True, "ok"
        else:
            msg = r.json().get("error", {}).get("message", f"HTTP {r.status_code}")[:100]
            return False, classify_death(msg)
    except Exception as e:
        return False, classify_death(str(e))


def classify_death(msg):
    msg_lower = msg.lower()
    if "403" in msg_lower or "suspended" in msg_lower or "banned" in msg_lower or "blocked" in msg_lower:
        return "封号"
    elif "timeout" in msg_lower or "timed out" in msg_lower:
        return "超时"
    elif "401" in msg_lower or "unauthorized" in msg_lower or "invalid" in msg_lower:
        return "token失效"
    elif "429" in msg_lower or "rate" in msg_lower:
        return "限流"
    elif "500" in msg_lower or "502" in msg_lower or "503" in msg_lower:
        return "上游故障"
    else:
        return f"其他: {msg[:40]}"


# ── 统计 ──────────────────────────────────────────────
def compute_stats(lifespan, now_str):
    now = datetime.fromisoformat(now_str) if isinstance(now_str, str) else now_str
    alive = {k: v for k, v in lifespan.items() if v["status"] == "alive"}
    dead = {k: v for k, v in lifespan.items() if v["status"] == "dead"}
    total = len(alive) + len(dead)

    # 7 日死亡率
    cutoff_7d = (now - timedelta(days=7)).isoformat()
    deaths_7d = sum(1 for v in dead.values() if v.get("died_at", "") >= cutoff_7d)

    # 中位寿命（天）
    lifespans_h = []
    for v in dead.values():
        if v.get("first_seen") and v.get("died_at"):
            try:
                born = datetime.fromisoformat(v["first_seen"])
                died = datetime.fromisoformat(v["died_at"])
                lifespans_h.append((died - born).total_seconds() / 3600)
            except:
                pass
    lifespans_h.sort()
    median_h = lifespans_h[len(lifespans_h) // 2] if lifespans_h else 0

    # 按平台
    def platform_stats(label):
        a = sum(1 for v in alive.values() if v.get("provider") == label)
        d = sum(1 for v in dead.values() if v.get("provider") == label)
        t = a + d
        if t == 0: return (0, 0, 0, 0)
        return (t, a, d, round(a / t * 100, 1))

    # 按域名
    def domain_stats():
        ds = defaultdict(lambda: [0, 0])  # [alive, dead]
        for v in {**alive, **dead}.values():
            d = v.get("domain", "unknown")
            if v["status"] == "alive": ds[d][0] += 1
            else: ds[d][1] += 1
        return sorted([(d, a, b, round(a/(a+b)*100, 1) if a+b else 0) for d, (a, b) in ds.items()],
                      key=lambda x: x[1] + x[2], reverse=True)

    # 存活最久的
    top_survivors = []
    for email, v in sorted(alive.items(), key=lambda x: x[1].get("first_seen", ""), reverse=False)[:10]:
        try:
            born = datetime.fromisoformat(v["first_seen"])
            days = (now - born).days
            top_survivors.append((email, days, v.get("provider", "")))
        except:
            pass

    # 最近死亡
    recent_deaths = []
    for email, v in sorted(dead.items(), key=lambda x: x[1].get("died_at", ""), reverse=True)[:15]:
        reason = v.get("death_reason", "?")
        try:
            born = datetime.fromisoformat(v["first_seen"]) if v.get("first_seen") else now
            died = datetime.fromisoformat(v["died_at"]) if v.get("died_at") else now
            days = (died - born).days
            recent_deaths.append((email, days, v.get("provider", ""), reason, v.get("died_at", "")[:10]))
        except:
            recent_deaths.append((email, 0, v.get("provider", ""), reason, "?"))

    # 生存曲线数据
    curve = []
    all_lived = []
    for v in {**alive, **dead}.values():
        try:
            born = datetime.fromisoformat(v["first_seen"])
            end = datetime.fromisoformat(v.get("died_at", now_str)) if v["status"] == "dead" else now
            all_lived.append((end - born).total_seconds() / 3600)
        except:
            pass
    all_lived.sort()
    for pct in [100, 90, 80, 70, 60, 50, 40, 30, 20, 10, 5]:
        idx = max(0, int(len(all_lived) * (1 - pct / 100)) - 1)
        curve.append((pct, round(all_lived[idx] / 24, 1) if idx < len(all_lived) else 0))

    return {
        "total": total, "alive": len(alive), "dead": len(dead),
        "deaths_7d": deaths_7d, "death_rate_7d": round(deaths_7d / max(total, 1) * 100, 1),
        "median_lifespan_h": round(median_h, 1),
        "median_lifespan_d": round(median_h / 24, 1),
        "kiro": platform_stats("kiro"),
        "codex": platform_stats("codex"),
        "domains": domain_stats(),
        "top_survivors": top_survivors,
        "recent_deaths": recent_deaths,
        "curve": curve,
    }


# ── HTML 报表 ──────────────────────────────────────────
def render_html(stats, now_str):
    """生成深色主题 HTML 报表"""
    def bar(pct, label="", w=20):
        filled = int(pct * w / 100)
        return f'<span class="bar"><span class="fill" style="width:{pct}%">{pct}%</span></span> {label}'

    # 平台对比行
    k = stats["kiro"]
    c = stats["codex"]
    platform_rows = ""
    for name, data in [("Kiro", k), ("Codex", c)]:
        t, a, d, rate = data
        if t == 0: continue
        platform_rows += f"""
        <tr>
            <td>{name}</td><td>{t}</td><td>{a}</td><td>{d}</td>
            <td><span class="alive-rate">{rate}%</span></td>
            <td>{bar(rate)}</td>
        </tr>"""

    # 域名排名
    domain_rows = ""
    for d, a, b, rate in stats["domains"][:10]:
        domain_rows += f"""<tr><td>{d}</td><td>{a+b}</td><td>{a}</td><td>{b}</td><td>{rate}%</td></tr>"""

    # 最近死亡
    death_rows = ""
    for email, days, prov, reason, ddate in stats["recent_deaths"]:
        cls = "ban" if reason == "封号" else "timeout" if reason == "超时" else ""
        death_rows += f"""<tr><td>{email}</td><td>{prov}</td><td>{days}d</td><td>{ddate}</td><td class="{cls}">{reason}</td></tr>"""

    # 长寿榜
    survivor_rows = ""
    for email, days, prov in stats["top_survivors"]:
        survivor_rows += f"""<tr><td>{email}</td><td>{prov}</td><td>{days}d</td></tr>"""

    # 生存曲线
    curve_bars = ""
    max_d = max(d for _, d in stats["curve"]) or 1
    for pct, days in stats["curve"]:
        w = int(days / max_d * 100)
        curve_bars += f"""<div class="curve-row"><span class="pct">{pct}%</span><div class="curve-bar"><div class="fill" style="width:{w}%"></div></div><span class="days">{days}d</span></div>"""

    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>账号存活观测报告</title>
<style>
:root{{--bg:#0d1117;--card:#161b22;--border:#30363d;--text:#c9d1d9;--muted:#8b949e;--green:#3fb950;--red:#f85149;--yellow:#d2991d;--blue:#58a6ff;--purple:#a371f7}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;line-height:1.6;padding:32px 24px}}
header{{text-align:center;padding:24px 0;border-bottom:1px solid var(--border);margin-bottom:32px}}
header h1{{font-size:1.8em;color:#f0f6fc}}
.meta{{color:var(--muted);font-size:.85em;margin-top:6px}}
h2{{font-size:1.3em;color:#f0f6fc;margin:28px 0 12px;padding-bottom:6px;border-bottom:1px solid var(--border)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:16px 0}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:16px}}
.card .label{{font-size:.75em;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}}
.card .value{{font-size:1.8em;font-weight:700;color:#f0f6fc;margin:4px 0}}
.card .sub{{font-size:.8em;color:var(--muted)}}
table{{width:100%;border-collapse:collapse;margin:12px 0;font-size:.88em}}
th,td{{padding:8px 12px;text-align:left;border-bottom:1px solid var(--border)}}
th{{color:var(--muted);font-weight:600;font-size:.8em;text-transform:uppercase}}
.ban{{color:var(--red);font-weight:600}}
.timeout{{color:var(--yellow)}}
.alive-rate{{color:var(--green);font-weight:600}}
.bar{{display:inline-block;height:8px;background:var(--border);border-radius:4px;width:200px;vertical-align:middle}}
.bar .fill{{display:block;height:100%;background:var(--green);border-radius:4px;min-width:0}}
.curve-row{{display:flex;align-items:center;gap:8px;margin:4px 0;font-size:.82em}}
.curve-row .pct{{width:35px;text-align:right;color:var(--muted)}}
.curve-row .days{{width:40px;color:var(--muted)}}
.curve-bar{{flex:1;height:14px;background:var(--border);border-radius:7px;overflow:hidden}}
.curve-bar .fill{{height:100%;background:linear-gradient(90deg,var(--green),var(--yellow),var(--red));border-radius:7px}}
footer{{text-align:center;color:var(--muted);font-size:.8em;margin-top:40px;padding-top:20px;border-top:1px solid var(--border)}}
.two-col{{display:grid;grid-template-columns:1fr 1fr;gap:24px}}
@media(max-width:768px){{.two-col{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<header>
    <h1>📊 账号存活观测报告</h1>
    <div class="meta">更新时间: {now_str} CST &nbsp;|&nbsp; 每 6 小时自动刷新 &nbsp;|&nbsp; tokenfree.cc</div>
</header>

<h2>一、总览</h2>
<div class="grid">
    <div class="card"><div class="label">监测账号</div><div class="value">{stats["total"]}</div></div>
    <div class="card"><div class="label">存活</div><div class="value" style="color:var(--green)">{stats["alive"]}</div></div>
    <div class="card"><div class="label">死亡</div><div class="value" style="color:var(--red)">{stats["dead"]}</div></div>
    <div class="card"><div class="label">7 日死亡率</div><div class="value" style="color:var(--yellow)">{stats["death_rate_7d"]}%</div><div class="sub">近 7 日死亡 {stats["deaths_7d"]} 个</div></div>
    <div class="card"><div class="label">中位寿命</div><div class="value">{stats["median_lifespan_d"]} 天</div><div class="sub">封号力度指标</div></div>
</div>

<div class="two-col">
<div>
<h2>二、平台对比</h2>
<table>
    <tr><th>平台</th><th>总数</th><th>存活</th><th>死亡</th><th>存活率</th><th>分布</th></tr>
    {platform_rows}
</table>
</div>
<div>
<h2>三、域名抗封排名</h2>
<table>
    <tr><th>域名</th><th>总数</th><th>存活</th><th>死亡</th><th>存活率</th></tr>
    {domain_rows}
</table>
</div>
</div>

<h2>四、生存曲线</h2>
<div style="max-width:600px;margin:12px 0">
    {curve_bars}
</div>
<p style="color:var(--muted);font-size:.85em">纵轴: 存活比例 &nbsp; 横轴: 存活天数 — 曲线越靠右说明账号越长寿</p>

<div class="two-col">
<div>
<h2>五、最近死亡</h2>
<table>
    <tr><th>账号</th><th>平台</th><th>活了</th><th>死亡日期</th><th>死因</th></tr>
    {death_rows}
</table>
</div>
<div>
<h2>六、长寿榜 TOP10</h2>
<table>
    <tr><th>账号</th><th>平台</th><th>存活</th></tr>
    {survivor_rows}
</table>
</div>
</div>

<footer>tokenfree.cc 账号存活观测系统 &nbsp;|&nbsp; 每 6 小时运行 &nbsp;|&nbsp; 通过真实 LLM 调用验证</footer>
</body>
</html>"""


# ── 主流程 ──────────────────────────────────────────────
def main():
    now = datetime.now(timezone.utc)
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    print(f"[{now_str}] 开始存活观测...")

    # 1. 加载账号
    accounts = load_accounts()
    print(f"  加载 {len(accounts)} 个活跃账号")

    # 2. 逐一验证（并发 3）
    results = {}
    for i in range(0, len(accounts), CONCURRENCY):
        batch = accounts[i:i + CONCURRENCY]
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
            futures = {pool.submit(check_one, a): a for a in batch}
            for f in concurrent.futures.as_completed(futures):
                acc = futures[f]
                try:
                    alive, reason = f.result()
                except:
                    alive, reason = False, "验证异常"
                results[acc["email"]] = (alive, reason)
                status = "✅" if alive else "❌"
                print(f"  {status} {acc['email']:<40} {reason}")

    # 3. 更新数据库
    lifespan = load_lifespan()
    for acc in accounts:
        email = acc["email"]
        alive, reason = results.get(email, (False, "未验证"))
        upsert_lifespan(email, acc["provider"], acc["domain"], alive, reason, now_str)

    # 4. 统计
    lifespan = load_lifespan()
    stats = compute_stats(lifespan, now_str)
    print(f"\n  存活: {stats['alive']}  死亡: {stats['dead']}  中位寿命: {stats['median_lifespan_d']}d")

    # 5. 生成报表
    html = render_html(stats, now_str + " UTC")
    Path(REPORT).parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  报表: {REPORT}")

    print(f"[{now_str}] 观测完成")


if __name__ == "__main__":
    main()
