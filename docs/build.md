# Building and releasing the app image

The lap counter app (`app/`) ships as **one container image** for
`linux/arm64` (Pi 4). The same image runs every service; compose picks the
command (`web` = gunicorn, `lapd` = `python -m lapcounter.lapd`).

Installing it on a Pi is done by
[RCRaceHQ-LapCounter-Deploy](https://github.com/SturgeonTechnologies/RCRaceHQ-LapCounter-Deploy)
(`deploy_lapcounter_app.yml`), which pulls a pinned tag from GHCR.

```
PR ──► CI: pytest + arm64 build (no push)
main ─► CI: pytest + arm64 build ─► GHCR :sha-<7 chars>
tag vX.Y.Z ─► CI: pytest + arm64 build ─► GHCR :vX.Y.Z
                                              │
         Deploy repo inventory: lapcounter_app_image_tag ─► Pi pulls it
```

Image: `ghcr.io/sturgeontechnologies/rcracehq-lapcounter` (GHCR names are
lowercase). It's a private package linked to this repo (the
`org.opencontainers.image.source` label), so it has the repo's visibility and
access.

**ARM**: the `image` job runs on GitHub's `ubuntu-24.04-arm` runner, so the
arm64 image is built natively; no QEMU, and about as fast as an x86 build.

**Tags don't change.** GHCR would let a tag be overwritten, so CI checks first
and never pushes a tag that already exists. A tag always means the same
image, so a Pi that has it never needs to pull it again.

## Components in the image

| Service | Command | Port | What |
|---|---|---|---|
| `web` | `gunicorn --worker-class gthread … 'lapcounter.web:create_app()'` (image default) | 80 | First-run setup, admin sign-in, public live view (SSE), `/healthz` |
| `lapd` | `python -m lapcounter.lapd` | — | Subscribes to OpenStint's ZeroMQ feed, writes passings + decoder stats to SQLite |

- Base `python:3.12-slim-bookworm`, two stages (wheel build, then install).
- Runs as `lapcounter` (uid 10001). `/var/lib/lapcounter` is the only
  writable path that matters (SQLite in WAL mode, shared by both services).
- Healthcheck: `GET http://127.0.0.1/healthz` every 30 s (disabled for
  `lapd`, which has no port).
- Env: `LAPCOUNTER_DB`, `OPENSTINT_ZMQ`, `LAPCOUNTER_DECODER_STALE_S`; see
  [app/README.md](../app/README.md#environment).

## Build locally

```bash
cd app
docker compose up --build                  # native arch, web on :80
docker buildx build --platform linux/arm64 -t lapcounter:dev .   # Pi arch (QEMU on x86, native on arm64)
```

Without Docker: see [app/README.md](../app/README.md#run).

## Release

- **Every merge to `main`** that touches `app/` pushes `:sha-<first 7 of the
  commit>`. Use these for testing on a Pi.
- **A release**: tag the commit and push the tag.

  ```bash
  git tag -a v0.1.0 -m "lapcounter v0.1.0" && git push origin v0.1.0
  ```

  CI pushes `:v0.1.0`. Bump `version` in `app/pyproject.toml` in the same PR
  so the package version matches.

Then in the deploy repo set `lapcounter_app_image_tag` (inventory) and run
`deploy_lapcounter_app.yml`. The run summary in GitHub Actions shows the exact
tag that was pushed.

List what's in GHCR (needs a token with `read:packages`; `gh auth refresh -s read:packages`):

```bash
gh api /orgs/SturgeonTechnologies/packages/container/rcracehq-lapcounter/versions \
  --jq '.[:10][] | [.metadata.container.tags, .created_at] | @tsv'
```

Or in the browser: the repo's **Packages** sidebar → `rcracehq-lapcounter`.

## One-time setup

Nothing to create: the first push from `main` creates the package, and the
workflow's `GITHUB_TOKEN` (`packages: write`) is the only credential CI uses.

After the first push, check the package is private and linked:
**Org → Packages → `rcracehq-lapcounter` → Package settings** shows
"Inherited access" from `RCRaceHQ-LapCounter`, visibility **Private**.

Push the first image: **Actions → app → Run workflow** on `main` (or
`gh workflow run app.yml -R SturgeonTechnologies/RCRaceHQ-LapCounter --ref main`).
It pushes `:sha-<7>` of the current `main`.

The Pis pull with a read-only token; setup is in the deploy repo's
[deploy_lapcounter_app.md](https://github.com/SturgeonTechnologies/RCRaceHQ-LapCounter-Deploy/blob/main/docs/deploy_lapcounter_app.md#ghcr-pull-token).
