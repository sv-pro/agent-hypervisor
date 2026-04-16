# Configuration

## Configuration sources (priority order)

1. **Environment variables** (highest priority)
2. **config.yaml** in the working directory (`service/config.yaml`)
3. **~/.agent-hypervisor/config.yaml** (user-level config)
4. **Built-in defaults** (lowest priority)

---

## All configuration options

| Key                  | Env var               | Default                               | Description                          |
|----------------------|-----------------------|---------------------------------------|--------------------------------------|
| `host`               | `AH_HOST`             | `127.0.0.1`                           | Bind address (keep loopback for demo)|
| `port`               | `AH_PORT`             | `17841`                               | Listen port                          |
| `session_token`      | `AH_SESSION_TOKEN`    | `demo-local-token`                    | Token for X-Session-Token header     |
| `bootstrap_enabled`  | —                     | `true`                                | Write bootstrap.json on startup      |
| `bootstrap_path`     | `AH_BOOTSTRAP_PATH`   | `~/.agent-hypervisor/bootstrap.json`  | Where to write bootstrap.json        |
| `trace_store_path`   | `AH_TRACE_STORE_PATH` | `./data/traces.jsonl`                 | Trace log file (JSONL)               |
| `memory_store_path`  | `AH_MEMORY_STORE_PATH`| `./data/memory.json`                  | Memory store file (JSON)             |

---

## config.yaml example

```yaml
host: 127.0.0.1
port: 17841
session_token: demo-local-token
bootstrap_enabled: true
trace_store_path: ./data/traces.jsonl
memory_store_path: ./data/memory.json
```

---

## .env example

```bash
AH_HOST=127.0.0.1
AH_PORT=17841
AH_SESSION_TOKEN=demo-local-token
```

Load with:
```bash
# Using python-dotenv (installed by default)
# The service auto-loads .env if present in the working directory.
```

Or manually:
```bash
export AH_PORT=17841
python -m app.main
```

---

## How to change the port

### Option A: Edit config.yaml
```yaml
port: 19999
```

### Option B: Environment variable
```bash
AH_PORT=19999 python -m app.main
```

After changing the port, restart the service. The extension will rediscover the
new port automatically on the next reconnect (via the bootstrap flow).

If the extension has a stale config, click **Reconnect** in the popup or side panel.
The extension will try the stored URL first, then fall back to the default
`127.0.0.1:17841`.

---

## Bootstrap file

When the service starts, it writes:

```
~/.agent-hypervisor/bootstrap.json
```

Content:
```json
{
  "host": "127.0.0.1",
  "port": 17841,
  "base_url": "http://127.0.0.1:17841",
  "session_token": "demo-local-token",
  "version": "0.1.0"
}
```

This file is removed when the service shuts down cleanly.

The bootstrap file is primarily for documentation and debugging. The extension
uses the `GET /bootstrap` HTTP endpoint (not direct file reading) for discovery.

---

## Data directory

The `service/data/` directory holds:

- `traces.jsonl` — append-only log of all evaluation decisions
- `memory.json` — simulated memory store (not yet wired to full memory operations)

Both files are created automatically on first use. They are not cleaned up on restart.
To reset, delete the files manually.
