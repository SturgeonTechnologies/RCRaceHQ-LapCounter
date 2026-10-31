# RCRaceHQ-LapCounter

Offline-first RC lap counter that runs on a Raspberry Pi 4 at the track and
syncs to [RC Race HQ](https://www.rcracehq.com). Decoding is done by
[OpenStint](https://github.com/zsellera/openstint) with an RTL-SDR; this repo
holds the services and web UI around it, and the hardware.

| Path | What |
|---|---|
| [`app/`](app) | The app: `lapd` (decoder feed → SQLite) + `web` (setup, admin, live view). Python, one container image |
| [`docs/design.md`](docs/design.md) | Architecture and build order |
| [`docs/club-sync.md`](docs/club-sync.md) | Club sync with RC Race HQ: pairing, event download, check-in, scoring, takeover |
| [`docs/linking.md`](docs/linking.md) | Linking a Pi to a club's track in RC Race HQ (Settings → Link) |
| [`docs/event-sync.md`](docs/event-sync.md) | Downloading the club's events (Events page), the event pack format, transponders to learn |
| [`docs/build.md`](docs/build.md) | Building the image, CI → GHCR (native arm64), releases |
| [`hardware/burst-detector-hat/`](hardware/burst-detector-hat) | Burst-detector HAT for the Pi (KiCad, fab files) |

## Where things live

- **This repo**: the code that runs as the service, and its image.
  CI tests every PR, builds `linux/arm64` on an arm64 runner, and on `main` /
  `v*` tags pushes to `ghcr.io/sturgeontechnologies/rcracehq-lapcounter`.
- **[RCRaceHQ-LapCounter-Deploy](https://github.com/SturgeonTechnologies/RCRaceHQ-LapCounter-Deploy)**:
  the Ansible. Provisions the Pi (OpenStint decoder, event hotspot + captive
  portal, SSM registration) and deploys a pinned image tag of this app with
  `deploy_lapcounter_app.yml`. It used to be `deploy/ansible/` here.

## Quick start

```bash
cd app
pip install -e '.[test]' && pytest       # tests
docker compose up --build                # web on :8080, lapd → 127.0.0.1:5556
```

Ship a version: merge to `main` (pushes `:sha-<7>`) or tag `vX.Y.Z` (pushes
`:vX.Y.Z`), then set `lapcounter_app_image_tag` in the deploy repo's inventory
and run its `deploy_lapcounter_app.yml`. Details in [docs/build.md](docs/build.md).
