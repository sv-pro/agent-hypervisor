# Localhost Bridge

## Why a local service?

The Chrome extension could run the policy engine inside the browser. The standalone
extension at `browser-demo/extension-standalone/` does exactly that. But this demo
makes a different point:

**Policy decisions must not run in the same trust boundary as the content being evaluated.**

If the policy engine runs in the extension alongside the page content, a sufficiently
sophisticated attack might influence it (JavaScript injection, prototype pollution,
shared storage manipulation). Hosting the governance kernel as a separate process on
localhost creates a **process boundary** — the page's JavaScript cannot reach the
service's Python process.

This mirrors the architecture of the full Agent Hypervisor:

```
web content    →  extension (thin client)  →  local service (kernel)
(untrusted)        (reports + displays)       (decides, traces, enforces)
```

---

## Configurable port model

The service **never assumes a fixed port**. Port 7777 is intentionally avoided.

### Default binding
- Host: `127.0.0.1` (loopback only — not accessible from the network)
- Port: `17841`

### How to change the port

**Via config.yaml:**
```yaml
host: 127.0.0.1
port: 19999
```

**Via environment variable:**
```bash
AH_PORT=19999 python -m app.main
```

**Via .env file (if using python-dotenv):**
```
AH_PORT=19999
```

The priority order is: env vars > config file > built-in defaults.

---

## Bootstrap discovery

The extension does not hardcode `127.0.0.1:17841`. Instead it uses a discovery flow:

### Step 1 — Try last-known config

On startup, the background service worker reads `chrome.storage.local` for a previously
discovered `hypervisor_service_config`. If found, it tries `GET /bootstrap` on that URL.

### Step 2 — Try default URL

If no stored config or if it's unreachable, try `http://127.0.0.1:17841/bootstrap`.

### Step 3 — Bootstrap endpoint response

`GET /bootstrap` requires **no authentication**. It returns:

```json
{
  "host": "127.0.0.1",
  "port": 17841,
  "base_url": "http://127.0.0.1:17841",
  "session_token": "demo-local-token",
  "version": "0.1.0"
}
```

### Step 4 — Store and use

The extension stores the discovered config in `chrome.storage.local` and uses the
`session_token` for all subsequent authenticated requests.

### Failure mode

If the service is unreachable, the extension shows a clear "disconnected" state and
refuses to claim that any policy evaluation succeeded. The UI displays instructions
for starting the service.

---

## Security considerations for localhost

Even on localhost, some minimal protections are in place:

- **Binds to 127.0.0.1 only** — not `0.0.0.0`. The service is unreachable from other machines.
- **Session token** — all non-bootstrap endpoints require `X-Session-Token` header.
  The token prevents random local processes from injecting fake events.
- **CORS** — only `chrome-extension://` origins and known localhost origins are allowed.
- **No shell execution** — the service has no endpoint that runs arbitrary commands.

These are MVP-level protections for a local demo, not production hardening.
