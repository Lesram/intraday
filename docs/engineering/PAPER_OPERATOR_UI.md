# Persistent local paper operator interface

The paper Compose definition now includes a `frontend` service at
`http://127.0.0.1:5173`. The previous definition started only the trading API,
PostgreSQL and Redis; a successfully built dashboard did not make an operator
interface persistently available.

## Request path

The production browser defaults to its current origin for HTTP and Socket.IO.
The existing explicit `VITE_API_BASE_URL` and `VITE_WS_BASE_URL` overrides remain
available to development builds. Raw scanner and market-data websockets already
derive their default from the browser origin.

The local static server forwards `/api`, `/socket.io` and `/ws` to the existing
`api:8000` service. It preserves authentication and query parameters, supports
websocket upgrades, and periodically resolves Docker DNS so an API replacement
does not require a frontend restart. Failed API responses remain failed API
responses; the SPA fallback applies only to page routes. Refreshing a route such
as `/portfolio` serves the application; an absent asset returns 404.

## Deployment boundary

This change prepares the deployment; adding source files does not activate the
service on the installed paper stack. Use the reviewed release checkout, its
existing approved environment and the existing Compose project `intra` during
the paper deployment procedure. Build the frontend with `VCS_REF` set to that
release's full commit SHA. Start only the `frontend` service with `--no-deps`
when performing a frontend-only update; do not recreate API/database/Redis as a
side effect. The existing API must already be healthy and on the project's
`trading-network`.

The service binds only loopback port 5173, restarts with Docker, runs without root
or Linux capabilities, and has a read-only filesystem with bounded temporary
storage. It receives no broker keys, environment file, models, database mount or
Docker socket. Its dedicated build-context allowlist excludes environment files
and installed modules. Base images are pinned by digest and packages use the
lock file. The [upstream unprivileged NGINX documentation](https://github.com/nginx/docker-nginx-unprivileged)
describes its non-root port and temporary-file layout.

`/ui-version.json` identifies the frontend source used at build time.
`/ui-health` certifies only that the static service responds. Neither endpoint
certifies the trading backend, broker connection or strategy performance; use
the authenticated platform status for those observations. Access logs retain
paths and response status without authentication queries, headers or bodies.

## Acceptance and rollback

- Configuration checks preserve local-only access and credential isolation.
- Frontend tests verify both browser-origin defaults and explicit overrides.
- `scripts/ci/check_frontend_container.py` uses a private Docker network and a
  synthetic API to verify page refresh, HTTP forwarding, 503 propagation, all
  three websocket upgrade paths, failure visibility and recovery after the API
  receives a different address. It destroys only its own temporary resources.
- The proxy check is not an authentication or trading simulation. Separate
  source-bound auth/portfolio/Socket.IO tests use synthetic users and a
  disposable database; natural paper-session acceptance remains separate.
- Record the built image identity before activation. To roll back the UI,
  restore the previously accepted frontend image and restart only this service.
  Stopping the UI does not stop the trading API; entry control remains an
  authenticated platform operation, not a frontend-container side effect.

Known dependency exposure is tracked in the platform audit. This deployment
addition does not unpark the legacy dependency/CI cleanup or claim that every
browser dependency is free of vulnerabilities.
