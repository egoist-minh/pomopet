# ADR-0002: Production sidecar runtime and Windows packaging

- Status: Accepted
- Date: 2026-10-21

## Context

The development application expected a separately started FastAPI server at a fixed port.
That made the Electron build unusable on a machine without Python and left the local API
open to unrelated local processes. SQLite databases and logs also defaulted to the source
tree, which is not writable after a normal per-user installation.

## Decision

- Package FastAPI as `pomopet-backend.exe` with PyInstaller one-file mode.
- Let Electron allocate a free loopback port and generate a 256-bit token for each run.
- Pass the token only in the child environment. Pass port, Electron parent PID and the
  Electron `userData` directory as explicit sidecar arguments.
- Bind FastAPI to `127.0.0.1`. Require `X-PomoPet-Token` on API and health requests when a
  runtime token is configured.
- Expose only `{ apiBaseUrl, token }` to the renderer through the isolated preload bridge.
- Wait for authenticated health before creating the production window. Restart an
  unexpectedly exited sidecar at most three times and terminate its process tree on quit.
- Store the application database, agent checkpoint and rotating logs under `userData`.
- Package the static Next.js export and sidecar with electron-builder, producing an NSIS
  per-user installer. User data is retained on uninstall.

Development may connect to an externally managed loopback backend through
`POMOPET_BACKEND_URL`. An empty runtime token remains supported for browser-only development;
packaged production always creates a random token.

## Security boundaries

The runtime token is local process isolation, not user authentication. A process running as
the same OS user may still inspect another process. The bridge therefore exposes no generic
IPC primitive, validates its sender and arguments, and the backend never logs the token,
provider keys or request bodies. Custom-protocol paths are resolved beneath `out/`; external
navigation and popup creation are denied.

Next.js static export emits inline React hydration payloads. After each renderer build, the
pipeline hashes those payloads and adds their SHA-256 sources to each page's CSP. Arbitrary
inline scripts remain blocked; `unsafe-inline` is not enabled.

## Consequences

- End users do not need Python, Conda or a terminal.
- Port collisions no longer prevent startup.
- The one-file sidecar has a measurable extraction cost during cold start and must be killed
  as a process tree on Windows.
- Code signing and auto-update remain separate release tasks.
