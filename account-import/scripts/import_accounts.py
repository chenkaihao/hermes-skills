#!/usr/bin/env python3
"""
9Router Account Import Tool v1.0.0
===================================
将账号批量导入 9Router 系统。
跨平台：Windows / macOS / Linux，仅需 Python 3.8+，零外部依赖。

用法:
  # 仅导出验证后的 JSON（不推送）
  python import_accounts.py --input accounts.json --export result.json

  # 直接推送到服务器
  python import_accounts.py --input accounts.json --push

  # 指定平台类型 + API 密钥
  python import_accounts.py --input accounts.csv --platform codex --api-key sk-xxx

  # 预览模式（不实际导入）
  python import_accounts.py --input accounts.json --dry-run

输入格式（任一即可）:
  1. 9Router 导出格式:   {"providerConnections": [...]}
  2. 按平台分组格式:     {"kiro": [...], "codex": [...]}
  3. 扁平列表格式:       [{"email": "...", "accessToken": "..."}, ...]
  4. CSV 格式:           email,accessToken,refreshToken,platform,...

支持平台: kiro, codex, chatgpt, claude
"""

import json, csv, io, os, sys, re, uuid, hashlib, time as time_module
from datetime import datetime, timezone
from pathlib import Path
from urllib import request, error as urllib_error

# ── 配置 ──────────────────────────────────────────────────
API_ENDPOINT = "https://tokenfree.cc/import/api/upload"
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
SUPPORTED_PLATFORMS = {"kiro", "codex", "chatgpt", "claude"}

# ── 颜色输出 ──────────────────────────────────────────────
class Color:
    """跨平台安全颜色：Windows 无 ANSI 支持时自动降级"""
    @staticmethod
    def _supported():
        return sys.platform != "win32" or os.environ.get("TERM")

    @staticmethod
    def green(s):  return f"\033[32m{s}\033[0m" if Color._supported() else s
    @staticmethod
    def red(s):    return f"\033[31m{s}\033[0m" if Color._supported() else s
    @staticmethod
    def yellow(s): return f"\033[33m{s}\033[0m" if Color._supported() else s
    @staticmethod
    def blue(s):   return f"\033[34m{s}\033[0m" if Color._supported() else s
    @staticmethod
    def bold(s):   return f"\033[1m{s}\033[0m" if Color._supported() else s
    @staticmethod
    def dim(s):    return f"\033[2m{s}\033[0m" if Color._supported() else s

# ── 字段映射表 ────────────────────────────────────────────
# 自动识别常见字段名，映射到标准字段
FIELD_ALIASES = {
    "email":       ["email", "mail", "username", "account", "login", "user"],
    "accessToken": ["accessToken", "access_token", "token", "key", "apiKey", "api_key", "accessKey"],
    "refreshToken":["refreshToken", "refresh_token", "refresh", "rt"],
    "expiresAt":   ["expiresAt", "expires", "expiry", "expiration", "expireDate", "expire_date", "validUntil"],
    "name":        ["name", "accountName", "account_name", "displayName", "display_name", "label", "title"],
    "platform":    ["platform", "provider", "type", "source"],
    "clientId":    ["clientId", "client_id", "clientID", "cid"],
    "clientSecret":["clientSecret", "client_secret", "secret", "cs"],
    "idToken":     ["idToken", "id_token", "idToken"],
}

def map_field(record, target_field):
    """根据别名表自动查找字段值"""
    for alias in FIELD_ALIASES.get(target_field, [target_field]):
        if alias in record:
            return record[alias]
    return None

def detect_platforms(accounts):
    """确定性平台检测：优先 provider 字段 → token 格式 → email 域名"""
    kiro_count = 0
    codex_count = 0
    for acc in accounts:
        # 1. 优先使用 provider/platform 字段（最准确）
        plat = str(map_field(acc, "platform") or "").lower()
        if plat in ("kiro", "codex"):
            if plat == "kiro": kiro_count += 1
            else: codex_count += 1
            continue

        rt = str(map_field(acc, "refreshToken") or "")
        at = str(map_field(acc, "accessToken") or "")
        email = str(map_field(acc, "email") or "").lower()

        # 2. Token 格式检测
        # Kiro AWS Builder ID: rt.1.AAA... (以 rt.1. 开头)
        if re.match(r'^rt\.[1-4]\.A', rt):
            kiro_count += 1
            continue
        # Codex GitHub OAuth: rt_XXXXX.tXXXXX（rt_ 开头 + 含 .t 分隔符）
        if rt.startswith("rt_") and ".t" in rt:
            codex_count += 1
            continue
        # accessToken 是 JWT 格式 → 通常是 Codex/ChatGPT
        if re.match(r'^eyJ', at):
            codex_count += 1
            continue

        # 3. 域名辅助判断
        if "qhvip.cc" in email or "8bit-scholar" in email or "github" in email:
            codex_count += 1
        elif "kiro" in email:
            kiro_count += 1

    detected = []
    if kiro_count > len(accounts) * 0.2:
        detected.append("kiro")
    if codex_count > len(accounts) * 0.2:
        detected.append("codex")
    return detected if detected else ["codex"]  # 默认 codex


def read_input(filepath):
    """读取输入文件：自动检测 JSON/CSV + BOM"""
    path = Path(filepath)
    if not path.exists():
        raise SystemExit(f"文件不存在: {filepath}")

    if path.stat().st_size > MAX_FILE_SIZE:
        raise SystemExit(f"文件过大: {path.stat().st_size} bytes (最大 50MB)")

    raw = path.read_bytes()

    # 移除 UTF-8 BOM (Windows Excel 产物)
    if raw[:3] == b"\xef\xbb\xbf":
        raw = raw[3:]

    content = raw.decode("utf-8", errors="replace")
    ext = path.suffix.lower()

    if ext == ".csv":
        return _parse_csv(content)
    elif ext == ".json" or ext == ".jsonl":
        return _parse_json(content)
    else:
        # 自动尝试 JSON
        try:
            return _parse_json(content)
        except:
            return _parse_csv(content)


def _parse_json(content):
    data = json.loads(content)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # 9Router 导出格式: {"providerConnections": [...]}
        if "providerConnections" in data:
            return data["providerConnections"]
        # 按平台分组: {"kiro": [...], "codex": [...]}
        if any(k in SUPPORTED_PLATFORMS for k in data):
            return data
    raise ValueError("无法识别的 JSON 格式")


def _parse_csv(content):
    reader = csv.DictReader(io.StringIO(content))
    data = [row for row in reader]
    if not data:
        raise ValueError("CSV 文件为空或无表头")
    return data


def validate_account(acc, platform):
    """验证单个账号字段"""
    errors = []

    email = map_field(acc, "email")
    if not email or "@" not in str(email):
        errors.append("缺少有效邮箱")

    rt = map_field(acc, "refreshToken")
    at = map_field(acc, "accessToken")
    if not rt and not at:
        errors.append("缺少 accessToken 或 refreshToken")

    expires = map_field(acc, "expiresAt")
    if expires:
        try:
            # 尝试多种日期格式
            for fmt in [
                "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%S.%f%z",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d",
            ]:
                try:
                    if fmt.endswith("%z"):
                        datetime.strptime(str(expires).replace("Z", "+00:00"), fmt)
                    else:
                        datetime.strptime(str(expires)[:10], "%Y-%m-%d")
                    break
                except ValueError:
                    continue
            else:
                errors.append(f"无法解析过期日期: {expires}")
        except:
            errors.append(f"日期格式无效: {expires}")

    # 平台特定校验
    if platform == "kiro":
        cid = map_field(acc, "clientId")
        cs = map_field(acc, "clientSecret")
        if cid and cs:
            if len(str(cid)) < 10:
                errors.append("clientId 过短")
    elif platform == "codex":
        rt_val = str(rt or "")
        # Codex: rt_ 前缀 + 至少 30 字符 或 JWT accessToken
        if rt_val and not rt_val.startswith("rt_") and not rt_val.startswith("eyJ"):
            errors.append("refreshToken 格式异常（Codex token 应以 rt_ 或 eyJ 开头）")

    return errors


def normalize_account(acc, platform):
    """将任意格式账号标准化为 9Router 格式"""
    email = str(map_field(acc, "email") or "").strip().lower()
    name = str(map_field(acc, "name") or email.split("@")[0])
    rt = str(map_field(acc, "refreshToken") or "")
    at = str(map_field(acc, "accessToken") or "")
    expires = str(map_field(acc, "expiresAt") or "1970-01-01T00:00:00.000Z")

    normalized = {
        "email": email,
        "name": name,
        "refreshToken": rt,
        "accessToken": at,
        "expiresAt": expires,
    }

    if platform == "kiro":
        normalized["clientId"] = str(map_field(acc, "clientId") or "")
        normalized["clientSecret"] = str(map_field(acc, "clientSecret") or "")

    return normalized


def detect_duplicates(accounts):
    """检测账号池内重复邮箱"""
    emails = {}
    dupes = []
    for i, acc in enumerate(accounts):
        email = acc.get("email", "").lower()
        if email in emails:
            dupes.append((email, emails[email], i))
        else:
            emails[email] = i
    return dupes


def preview(accounts_by_platform, dupes, validation_errors):
    """打印导入预览"""
    total = sum(len(v) for v in accounts_by_platform.values())
    print()
    print(Color.bold("═══ 导入预览 ═══"))
    print(f"平台: {', '.join(k for k, v in accounts_by_platform.items() if v)}")
    print(f"账号总数: {total}")

    for platform, accs in accounts_by_platform.items():
        if accs:
            valid = sum(1 for e in validation_errors.values() if not e and e is not None)
            invalid = sum(1 for a in accs if a.get("email", "") in validation_errors and validation_errors.get(a.get("email", "")))
            print(f"  {Color.blue(platform)}: {len(accs)} 个", end="")
            if invalid:
                print(f" ({Color.red(f'{invalid} 个有错误')})")
            else:
                print()

    if dupes:
        print(f"\n{Color.yellow('⚠ 检测到重复邮箱:')}")
        for email, i, j in dupes[:5]:
            print(f"  - {email} (行 {i+1} 和 {j+1})")
        if len(dupes) > 5:
            print(f"  ... 还有 {len(dupes)-5} 个重复")

    # 显示有错误的账号
    has_errors = {k: v for k, v in validation_errors.items() if v}
    if has_errors:
        print(f"\n{Color.red('✗ 以下账号有验证错误:')}")
        for email, errs in list(has_errors.items())[:10]:
            print(f"  - {email}: {', '.join(errs)}")

    print()


def build_request_body(accounts_by_platform):
    """构建 API 请求体"""
    body = {}
    for platform in SUPPORTED_PLATFORMS:
        if platform in accounts_by_platform and accounts_by_platform[platform]:
            body[platform] = accounts_by_platform[platform]
    return body


def push_to_server(body, api_key=None):
    """将数据推送到 9Router 导入服务"""
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    data = json.dumps(body).encode("utf-8")
    req = request.Request(API_ENDPOINT, data=data, headers=headers, method="POST")

    try:
        with request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())
            return result
    except urllib_error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(body_text)
            return {"error": detail.get("error", detail.get("message", str(e)))}
        except:
            return {"error": f"HTTP {e.code}: {body_text[:200]}"}
    except urllib_error.URLError as e:
        return {"error": f"网络错误: {e.reason}"}
    except Exception as e:
        return {"error": str(e)}


def poll_status(initial_result, api_key=None):
    """轮询导入状态"""
    if initial_result.get("error"):
        return initial_result

    print()
    print(Color.blue("⏳ 服务器正在验证账号..."))

    status_url = "https://tokenfree.cc/import/api/status"
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    dots = 0
    for _ in range(60):  # 最多等 5 分钟
        try:
            req = request.Request(status_url, headers=headers)
            with request.urlopen(req, timeout=10) as resp:
                status = json.loads(resp.read())
        except:
            time_module.sleep(5)
            continue

        running = status.get("running", False)
        phase = status.get("phase", "")
        progress = status.get("progress", 0)
        total = status.get("total", 0)
        valid = status.get("valid_count", 0)

        if not running:
            print(f"\r{Color.green('✅ 验证完成')}: {valid}/{total} 可用                    ")
            return status

        current = status.get("current_account", "")
        dots = (dots + 1) % 4
        bar = f"[{'=' * (progress * 20 // max(total, 1))}{' ' * (20 - progress * 20 // max(total, 1))}]"
        line = f"\r{bar} {progress}/{total}  通过 {valid}  {'.' * dots}"
        if current:
            line += f"  {Color.dim(current[:40])}"
        print(line + "  ", end="")
        time_module.sleep(5)

    print()
    return {"error": "验证超时（超过 5 分钟）"}


def main():
    import argparse

    p = argparse.ArgumentParser(
        description="9Router 账号导入工具 — 跨平台批量导入账号",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --input accounts.json --dry-run         # 预览模式
  %(prog)s --input accounts.json --push             # 导入预览后推送
  %(prog)s --input accounts.json --export out.json  # 导出验证后的 JSON
  %(prog)s --input accounts.csv --platform codex --push
        """
    )
    p.add_argument("--input", "-i", required=True, help="输入文件路径 (JSON/CSV)")
    p.add_argument("--platform", "-p", choices=sorted(SUPPORTED_PLATFORMS),
                   help="平台类型（不指定则自动检测）")
    p.add_argument("--push", action="store_true", help="推送到 9Router 服务器")
    p.add_argument("--export", "-o", help="导出验证后的 JSON 到文件")
    p.add_argument("--dry-run", action="store_true", help="预览模式（不导入）")
    p.add_argument("--api-key", help="API 密钥（如服务端需要认证）")
    p.add_argument("--endpoint", help="自定义 API 端点 URL")
    p.add_argument("--yes", "-y", action="store_true", help="跳过确认提示")

    args = p.parse_args()

    if args.endpoint:
        global API_ENDPOINT
        API_ENDPOINT = args.endpoint

    # ── Step 1: 读取文件 ──
    print(Color.dim(f"读取: {args.input}"))
    try:
        raw_data = read_input(args.input)
    except Exception as e:
        print(Color.red(f"✗ 读取失败: {e}"))
        sys.exit(1)

    # ── Step 2: 识别格式 ──
    if isinstance(raw_data, list):
        # 扁平列表 → 检测平台
        platforms = [args.platform] if args.platform else detect_platforms(raw_data)
        accounts_by_platform = {p: [] for p in SUPPORTED_PLATFORMS}
        for acc in raw_data:
            plat = map_field(acc, "platform") or platforms[0]
            accounts_by_platform.setdefault(plat, []).append(acc)
    elif isinstance(raw_data, dict):
        # 已分组格式
        accounts_by_platform = {p: raw_data.get(p, []) for p in SUPPORTED_PLATFORMS}
        # 也检查 providerConnections（9Router 导出）
        if not any(accounts_by_platform.values()) and "providerConnections" in raw_data:
            for conn in raw_data["providerConnections"]:
                p = conn.get("provider", "").lower()
                if p in SUPPORTED_PLATFORMS:
                    accounts_by_platform.setdefault(p, []).append(conn)
    else:
        print(Color.red("✗ 无法识别的数据格式"))
        sys.exit(1)

    # ── Step 3: 标准化 + 验证 ──
    normalized = {}
    validation_errors = {}
    for platform in SUPPORTED_PLATFORMS:
        normalized[platform] = []
        for acc in accounts_by_platform.get(platform, []):
            norm = normalize_account(acc, platform)
            errs = validate_account(acc, platform)
            if errs:
                validation_errors[norm["email"]] = errs
            normalized[platform].append(norm)

    # ── Step 4: 重复检测 ──
    all_accounts = []
    for plat_accs in normalized.values():
        all_accounts.extend(plat_accs)
    dupes = detect_duplicates(all_accounts)

    # ── Step 5: 预览 ──
    preview(normalized, dupes, validation_errors)
    total = sum(len(v) for v in normalized.values())

    if total == 0:
        print(Color.red("✗ 没有可导入的账号"))
        sys.exit(1)

    # ── Step 6: 导出模式 ──
    if args.export:
        body = build_request_body(normalized)
        with open(args.export, "w", encoding="utf-8") as f:
            json.dump(body, f, indent=2, ensure_ascii=False)
        print(Color.green(f"✅ 已导出到: {args.export}"))
        if not args.push:
            return

    # ── Step 7: 预览模式 ──
    if args.dry_run:
        print(Color.blue("🔍 预览模式 — 未实际导入"))
        return

    # ── Step 8: 确认 ──
    if not args.yes and args.push:
        response = input(f"\n确认推送到 {API_ENDPOINT}? [y/N] ")
        if response.lower() not in ("y", "yes"):
            print("已取消")
            return

    # ── Step 9: 推送 ──
    if args.push:
        body = build_request_body(normalized)
        print(Color.dim(f"推送中 → {API_ENDPOINT}"))
        result = push_to_server(body, args.api_key)

        if result.get("error"):
            print(Color.red(f"✗ 推送失败: {result['error']}"))
            sys.exit(1)

        print(Color.green(f"✅ 推送成功"))
        if "stats" in result:
            s = result["stats"]
            for plat in SUPPORTED_PLATFORMS:
                if plat in s:
                    ps = s[plat]
                    print(f"  {plat}: +{ps.get('new',0)} 新增, {ps.get('updated',0)} 更新")

        # 轮询验证结果
        time_module.sleep(2)
        final = poll_status(result, args.api_key)
        if not final.get("error") and final.get("results"):
            print()
            print(Color.bold("── 验证结果 ──"))
            for acc in final["results"][:20]:
                status = Color.green("✓") if acc.get("valid") else Color.red("✗")
                print(f"  {status} {acc['name']} ({acc['email']}): {acc.get('detail','')}")

    elif not args.export:
        print(Color.yellow("⚠ 使用 --push 推送到服务器，或 --export 导出 JSON"))


if __name__ == "__main__":
    main()
