# ADR 0007 — Docker Engine inside WSL2, not Docker Desktop

**Status:** Accepted · 17 August 2026
**Decider:** Claude, after Docker Desktop proved uninstallable from this session; flagged to Parul Bhoite for objection
**Amends:** [ADR 0006](0006-pgvector-via-official-docker-image.md) — the image and the outcome are unchanged; only the engine differs

## Context

ADR 0006 chose Docker Desktop plus the official `pgvector/pgvector` image. WSL2 with Ubuntu was installed successfully. Docker Desktop itself was not, for two independent reasons:

1. **`winget` hangs rather than failing.** It resolves the manifest, hands the download to Delivery Optimization, and DO transfers **0 bytes** indefinitely — no exception, no exit code, nothing in its event log. This happened three times on this machine (Python 3.12, PostgreSQL 17, Docker Desktop). Direct HTTPS to the same URLs returns 200 and downloads normally, so it is DO specifically, not the network.

2. **The installer needs UAC.** Proven earlier with the EnterpriseDB installer: `Start-Process` returns *"The requested operation requires elevation."* A UAC prompt in a non-interactive session hangs indefinitely.

Downloading the installer directly did work around (1) — but the resulting 629 MB file failed its Authenticode check with **`HashMismatch`**: correct Docker Inc certificate, byte count matching `Content-Length` exactly, but contents not matching what Docker signed. The resume had appended to a partial written by a killed process. It was deleted rather than run; a signature that does not verify is not a file to execute as administrator, and the matching size is precisely what makes that dangerous.

Meanwhile `wsl -d Ubuntu -u root` grants root **with no password and no UAC**.

## Decision

**Docker Engine and Compose v2, installed inside WSL2 Ubuntu via `apt`.**

Everything ADR 0006 specified is unchanged: the same `pgvector/pgvector:pg17` image, the same `docker-compose.yml`, the same init script creating `nexus_app` as `NOSUPERUSER NOBYPASSRLS`, the same healthcheck asserting the extension exists.

WSL2 forwards `localhost`, so the container on `127.0.0.1:5432` is reachable from Windows unchanged — `.env`, the DSN shape and every application module are untouched.

`scripts/lib/docker.ps1` routes `docker` through `wsl -d Ubuntu -u root`, translating `D:\…` to `/mnt/d/…`. `Get-DockerMode` returns `native` if Docker Desktop is ever installed, and every caller keeps working.

## Verified

```
vector 0.8.6 · pgcrypto 1.3
nexus_app super=false bypassrls=false
server = PostgreSQL 17.11 (Debian) reached from Windows at 127.0.0.1:5432
alembic 0006 (head) — all six migrations applied to a fresh volume
448 tests pass, including the M1 isolation suite
/health/ready → pgvector: ok, extension installed
```

The isolation suite passing here matters more than the extension: it proves RLS is genuinely enforced against this backend, and that the official image's superuser default was successfully avoided.

## Consequences

- **`docker` is not on the Windows PATH.** Anything invoking it must go through `scripts/lib/docker.ps1`. A direct `docker …` in a script will fail on this machine.
- **The daemon does not survive a WSL restart.** There is no systemd session by default, so `Start-DockerDaemon` is called by the scripts that need it.
- **No Docker Desktop GUI**, and no automatic start at login. Acceptable; the container is managed by script.
- Building this exposed a real bug worth recording: an earlier `Invoke-Docker` both printed output *and* returned an exit code, so `verify.ps1` captured the exit code as the health string and reported the **native cluster** while the container was serving. That is exactly the misreport the backend check exists to prevent. The interface is now split — `Invoke-Docker` prints and returns a code, `Get-DockerOutput` returns lines, `Get-DockerContainerHealth` returns a state.
- Docker Desktop remains a valid future choice; it needs one UAC click from an interactive terminal and a clean download with the signature verified before running.

## Revisit

If a Windows-native Docker is wanted (for a GUI, or for `docker` on PATH), or when a deployment target is chosen — the Compose file is already the starting point for it.
