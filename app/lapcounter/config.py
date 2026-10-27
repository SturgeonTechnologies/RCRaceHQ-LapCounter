"""Runtime settings, all from environment variables (set by compose / the role)."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    db_path: str = "/var/lib/lapcounter/lapcounter.db"
    decoder_url: str = "tcp://127.0.0.1:5556"
    # How long the decoder can be silent before the UI calls it offline. OpenStint
    # sends an S line every second, so a few missed ones means it's gone.
    decoder_stale_s: float = 5.0

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Config":
        env = os.environ if env is None else env
        return cls(
            db_path=env.get("LAPCOUNTER_DB", cls.db_path),
            decoder_url=env.get("OPENSTINT_ZMQ", cls.decoder_url),
            decoder_stale_s=float(env.get("LAPCOUNTER_DECODER_STALE_S", cls.decoder_stale_s)),
        )
