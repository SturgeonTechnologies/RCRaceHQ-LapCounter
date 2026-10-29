# Lap counter app

Python package `lapcounter`: the services that run next to OpenStint on the Pi.
See [../docs/design.md](../docs/design.md) for the full design. Built so far:
lapd + SQLite + live page + local admin (step 1) and transponder learning
([../docs/learning.md](../docs/learning.md)).

| Service | Command | What it does now |
|---|---|---|
| `web` | `gunicorn … 'lapcounter.web:create_app()'` | First-run admin setup, admin sign-in, public live view (SSE), Admin → Transponders (learn + record) |
| `lapd` | `python -m lapcounter.lapd` | Subscribes to OpenStint's ZeroMQ feed (`:5556`), stores passings, decoder stats and every learning (`L`) line in SQLite |

Both share `/var/lib/lapcounter/lapcounter.db` (WAL). Not built yet: heats and
laps, lineup builder, the learning pad's RF relay, syncd, announcer, captive-portal grants
(the placeholder `race-portal` from `race_hotspot` still owns port 80).

## Run

```
docker compose up --build        # web on :8080, lapd talks to 127.0.0.1:5556
```

Without Docker:

```
pip install -e '.[test]'
LAPCOUNTER_DB=./dev.db python -m lapcounter.lapd &
LAPCOUNTER_DB=./dev.db flask --app 'lapcounter.web:create_app()' run -p 8080
```

Open `http://<pi>:8080/`. The first visit goes to **Set up the lap counter**.
Transponders are at `/transponders` once you're signed in.

## Environment

| Variable | Default |
|---|---|
| `LAPCOUNTER_DB` | `/var/lib/lapcounter/lapcounter.db` |
| `OPENSTINT_ZMQ` | `tcp://127.0.0.1:5556` |
| `LAPCOUNTER_DECODER_STALE_S` | `5` (seconds without an `S` line before the decoder shows offline) |
| `OPENSTINT_RC4_DIR` | `/var/lib/openstint` (OpenStint's `.rc4` folder; the web container needs it mounted read-write, see [learning](../docs/learning.md#permissions)) |

## Test

```
pip install -e '.[test]' && pytest
```

## Image and deploy

CI builds a `linux/arm64` image and pushes it to GHCR
(`ghcr.io/sturgeontechnologies/rcracehq-lapcounter`,
`:sha-<7>` from `main`, `:vX.Y.Z` from tags): [../docs/build.md](../docs/build.md).
The Pi runs it through `deploy_lapcounter_app.yml` in
[RCRaceHQ-LapCounter-Deploy](https://github.com/SturgeonTechnologies/RCRaceHQ-LapCounter-Deploy).
