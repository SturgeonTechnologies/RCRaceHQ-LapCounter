# RCRaceHQ-LapCounter

Offline-first RC lap counter that runs on a Raspberry Pi at the track and syncs to
[RC Race HQ](https://www.rcracehq.com). Decoding is done by
[OpenStint](https://github.com/zsellera/openstint) with an RTL-SDR; this repo holds
the services and web UI around it.

The Pi is provisioned by `SturgeonTechnologies/OPS_ansible` (`provision_race_decoder.yml`).

See [docs/design.md](docs/design.md) for the architecture.
