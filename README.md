# RCRaceHQ-LapCounter

Offline-first RC lap counter that runs on a Raspberry Pi at the track and syncs to
[RC Race HQ](https://www.rcracehq.com). Decoding is done by
[OpenStint](https://github.com/zsellera/openstint) with an RTL-SDR; this repo holds
the services and web UI around it.

The Pi is provisioned by the Ansible in [`deploy/ansible/`](deploy/ansible):

- [`provision_race_decoder.yml`](deploy/ansible/docs/provision_race_decoder.md): OpenStint decoder + `openstint-learn`
- [`register_race_decoder.yml`](deploy/ansible/docs/register_race_decoder.md): AWS SSM registration by Ethernet MAC + CloudWatch agent

The app itself (lapd + web UI, containerized) is in [`app/`](app).

See [docs/design.md](docs/design.md) for the architecture.
