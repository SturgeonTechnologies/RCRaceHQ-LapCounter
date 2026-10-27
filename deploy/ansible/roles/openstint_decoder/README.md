# openstint_decoder

Provisions a Raspberry Pi (64-bit Raspberry Pi OS, Trixie) with an RTL-SDR as
an [OpenStint](https://github.com/zsellera/openstint) RC lap-timing decoder:

- upstream `openstint` package from its (unsigned) apt repo, pinned so nothing
  else can be installed from that repo
- `/etc/openstint.conf` from role vars
- `/usr/local/bin/openstint-learn` (`files/openstint-learn`): learns one RC4
  transponder and names its `.rc4` file after the label number
- optional ufw rule limiting the unauthenticated ZeroMQ feed to one CIDR

Usage, variables and the learn workflow:
[`docs/provision_race_decoder.md`](../../docs/provision_race_decoder.md).
Defaults with comments: [`defaults/main.yml`](defaults/main.yml).

## Requirements

- Ansible >= 2.15, `community.general` (ufw step only)
- Target: arm64 Debian 13+, Pi 3 Model B+ or newer, RTL-SDR v3/v4 or HackRF
  (HackRF needs the unit's `ExecStart` switched; not handled here)

## Tests

`tests/test_openstint_learn.py` covers message parsing, the DONE decision, the
rename (never overwrites) and an end-to-end run against a fake ZeroMQ decoder.
