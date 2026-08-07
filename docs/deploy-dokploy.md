# Deploying with Dokploy

How to stand up School Finance on a Dokploy-managed VPS. This is the **primary
deployment path** for the hosted web app; the `.exe`/tray packaging under
`packaging/` remains for single-office-PC installs.

## What you get

- A public HTTPS endpoint (Traefik + Let's Encrypt, via Dokploy's Domains tab)
- A named Docker volume (`school-finance-data`) holding the SQLite DB, uploads,
  and app-level backups — survives redeploys
- The app's in-app "Shut down" button disabled (`SCHOOL_FINANCE_DISABLE_SHUTDOWN=1`)
- Session cookies marked `Secure` behind HTTPS

## Architecture

`docker-compose.yml` (repo root) builds the image from `Dockerfile`
(python:3.11-slim, single uvicorn worker), mounts the named volume at `/data`,
and joins Dokploy's external `dokploy-network`. Traefik routes `https://<school>.<domain>` to the container on port 8000.

## Prerequisites

1. A VPS running [Dokploy](https://dokploy.com) (install: `curl -sSL https://dokploy.com/install.sh | sh`).
2. The `hgeesey.store` zone (or another domain you control) at your DNS provider.
3. The repo pushed to GitHub.

## DNS

Point a subdomain at the VPS's public IP. For a school using `Sunrise Primary`:

```
sunrise.hgeesey.store.  A  <VPS_PUBLIC_IP>
```

(Traefik needs the A record before it can issue a certificate.)

## Creating the service in Dokploy

1. **Project** → new project (e.g. `school-finance`).
2. **Service** → **Docker Compose**, source **GitHub**.
3. Select the `HassanGeesey/school-finance` repo, branch `main`.
4. Set **Compose Path** to `docker-compose.yml`.
5. Save, then **Deploy**. Watch the build logs for a clean exit.

The compose file already sets `SCHOOL_FINANCE_DATA=/data`,
`SCHOOL_FINANCE_DISABLE_SHUTDOWN=1`, the volume mount, and the network. **Do
not** add a `container_name`, and do not publish the port to the host — Traefik
routes to port `8000` over the network.

## Domain + HTTPS

1. Open the service → **Domains** tab.
2. **Add Domain**: `sunrise.hgeesey.store`, container port `8000`, HTTPS on.
3. Wait ~10s for the Let's Encrypt certificate, then visit the URL.
4. First visit runs the **setup wizard** — create the Admin account and the
   school name (this is the only bootstrapping step).

## Backups

Two layers, both independent of each other:

1. **App-level** (unchanged in Docker): automatic on every startup plus the
   "Backup now" button, writing rotated copies into `data/backups/` — which
   lives *inside* the named volume.
2. **Volume-level**: in Dokploy, configure a scheduled **Volume Backup** of
   `school-finance-data` (to the server disk or an S3 destination). This is the
   recovery point if the volume is ever lost.

## Verifying a deploy

```bash
# container healthy + single worker
docker ps --filter name=school-finance
docker logs <container>   # "Uvicorn running on http://0.0.0.0:8000"

# app boots, DB created inside the volume
docker exec <container> ls /data
```

## Operational notes

- **One uvicorn worker** by design — the app uses a single SQLite file; scaling
  it is a Postgres migration, out of scope.
- **Shutdown is disabled**: the Settings page hides it and `POST /system/shutdown`
  returns 403. Restart/stop the service from Dokploy instead.
- **Secure cookie**: set only when Traefik forwards `X-Forwarded-Proto: https`,
  so localhost/`.exe` installs are unaffected.
- **Fresh installs only**: the volume starts empty and the setup wizard runs on
  first visit. To later adopt an existing office-PC database, stop the service,
  copy `school_finance.db` into the volume's `data/` folder (via `docker cp` or
  a Dokploy file action), then start it — the app's startup backup will snapshot
  it immediately.

## Follow-ups (out of scope here)

- Brute-force login throttling/lockout — the app is public on the internet now;
  PBKDF2-600k is the only current deterrent.
- A healthcheck endpoint and Dokploy health checks for restart/liveness signals.
