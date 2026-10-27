# Lap counter app

Python package `lapcounter`: the services that run next to OpenStint on the Pi.
See [../docs/design.md](../docs/design.md) for the full design; this is build
step 1 (lapd + SQLite + live page + local admin).

| Service | Command | What it does now |
|---|---|---|
| `web` | `gunicorn … 'lapcounter.web:create_app()'` | First-run admin setup, admin sign-in, public live view (SSE) |
| `lapd` | `python -m lapcounter.lapd` | Subscribes to OpenStint's ZeroMQ feed (`:5556`), stores passings, decoder stats and learning state in SQLite |

Both share `/var/lib/lapcounter/lapcounter.db` (WAL). Not built yet: heats and
laps, lineup builder, learning flow, syncd, announcer, captive-portal grants
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

## Environment

| Variable | Default |
|---|---|
| `LAPCOUNTER_DB` | `/var/lib/lapcounter/lapcounter.db` |
| `OPENSTINT_ZMQ` | `tcp://127.0.0.1:5556` |
| `LAPCOUNTER_DECODER_STALE_S` | `5` (seconds without an `S` line before the decoder shows offline) |

## Test

```
pip install -e '.[test]' && pytest
```
