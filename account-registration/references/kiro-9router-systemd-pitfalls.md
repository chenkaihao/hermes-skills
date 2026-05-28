# 9Router Systemd Deployment Pitfalls

Three issues encountered when upgrading 9Router from v0.4.20 to v0.4.31 (2026-05-12).
All are now resolved. Keep these patterns for future upgrades.

---

## 1. better-sqlite3 NODE_MODULE_VERSION Mismatch

**Symptom**: After building with one Node version, service logs show:
```
[DB] better-sqlite3 unavailable: NODE_MODULE_VERSION 127. This version requires NODE_MODULE_VERSION 109.
```

**Root cause**: The build step used Node v24 (via `npm run build` on dev machine) but systemd ran `/usr/bin/node` (v18.19.1). `better-sqlite3` is a native addon compiled against a specific Node ABI version.

**Fix**:
```bash
# 1. Find which Node the systemd service uses
grep ExecStart /etc/systemd/system/9router.service

# 2. Point ExecStart to the Node version used for building (or rebuild)
# Option A: Use nvm Node (matching build environment)
sed -i 's|ExecStart=/usr/bin/node|ExecStart=/root/.nvm/versions/node/v22.22.1/bin/node|' /etc/systemd/system/9router.service

# Option B: Rebuild for the runtime Node
cd /root/src/9router/.next/standalone/9router
npm rebuild better-sqlite3

# 3. Restart
systemctl daemon-reload && systemctl restart 9router
```

**After fix**: `[DB] Driver: better-sqlite3 | file: /root/src/9router-data/db/data.sqlite`

---

## 2. Proxy Test `toWellFormed` Error (File/Blob Polyfill)

**Symptom**: 9Router Web UI proxy pool health check shows:
```
Last tested: ... · a.toWellFormed is not a function
```

**Root cause**: webpack/Next.js strips the `File` global during build. Undici v6+ uses `File.toWellFormed()` internally for FormData handling. The polyfill must provide both `Blob` and `File` classes with `toWellFormed()` methods.

**Polyfill** (`/root/src/9router/.next/standalone/9router/preload.js`):
```js
// Polyfill Blob
if (typeof globalThis.Blob === "undefined") {
  globalThis.Blob = class Blob {
    constructor(parts = [], options = {}) {
      this._parts = Array.isArray(parts) ? parts : [parts];
      this.type = options.type || "";
      this.size = this._parts.reduce((sum, p) => {
        if (typeof p === "string") return sum + Buffer.byteLength(p);
        if (p instanceof ArrayBuffer || ArrayBuffer.isView(p)) return sum + p.byteLength;
        if (p instanceof Blob) return sum + p.size;
        return sum;
      }, 0);
    }
    arrayBuffer() { /* ... */ return Promise.resolve(buf.buffer); }
    slice(start, end, contentType) { return new Blob([], { type: contentType || this.type }); }
    stream() { return new ReadableStream({ start(c) { c.close(); } }); }
    text() { return Promise.resolve(this._parts.map(p => typeof p === "string" ? p : "").join("")); }
    toWellFormed() { return this; }
  };
}

// Polyfill File (extends Blob)
if (typeof globalThis.File === "undefined") {
  globalThis.File = class File extends globalThis.Blob {
    constructor(bits, name, options = {}) {
      super(bits, options);
      this.name = name || "";
      this.lastModified = options.lastModified ?? Date.now();
    }
    toWellFormed() {
      return new File([], this.name, { type: this.type, lastModified: this.lastModified });
    }
  };
}
```

---

## 3. Systemd `--require` Quoting Trap ⚠️

**Symptom**: Node process fails to start with `--require requires an argument` when using quotes in systemd ExecStart.

**Wrong** (systemd passes literal quotes to Node):
```ini
ExecStart=/usr/bin/node --require "/root/path/preload.js" /root/path/server.js
```

**Also wrong** (bare path, but systemd splits whitespace unpredictably):
```ini
ExecStart=/usr/bin/node --require /root/path/preload.js /root/path/server.js
```

**Right** — Use `NODE_OPTIONS` environment variable:
```ini
[Service]
Environment="NODE_OPTIONS=--require /root/path/preload.js"
ExecStart=/usr/bin/node /root/path/server.js
```

Systemd's `Environment=` handles the value literally — no shell parsing. The `=` between `VAR` and value is the assignment operator; everything after is the value. So `NODE_OPTIONS=--require /path` sets the env var correctly.

**Verification**: The env var is visible in the process:
```bash
PID=$(systemctl show 9router -p MainPID --value)
cat /proc/$PID/environ | tr '\0' '\n' | grep NODE_OPTIONS
# → NODE_OPTIONS=--require /root/path/preload.js
```

---

## Complete Working systemd Unit (as of 2026-05-12)

```ini
[Unit]
Description=9Router - Universal AI API Router
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/src/9router/.next/standalone/9router
ExecStart=/root/.nvm/versions/node/v22.22.1/bin/node /root/src/9router/.next/standalone/9router/server.js
Restart=always
RestartSec=5

Environment=NODE_ENV=production
Environment="NODE_OPTIONS=--require /root/src/9router/.next/standalone/9router/preload.js"
Environment=PORT=9000
Environment=HOSTNAME=0.0.0.0
Environment=DATA_DIR=/root/src/9router-data
# ... other env vars ...

[Install]
WantedBy=multi-user.target
```

---

## Recurrence Prevention

When upgrading 9Router in the future:
1. **Rebuild better-sqlite3** with the systemd Node (`npm rebuild better-sqlite3` in standalone dir)
2. **Verify preload.js exists** and has both `Blob` and `File` with `toWellFormed()`
3. **Use NODE_OPTIONS**, never `--require` in ExecStart
4. **Check `NODE_MODULE_VERSION`** in logs after restart — `better-sqlite3` line is the canary
