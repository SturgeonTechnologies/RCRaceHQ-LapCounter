# provision_race_decoder

Turns a **Raspberry Pi + RTL-SDR** into an [OpenStint](https://github.com/zsellera/openstint)
lap-timing decoder for MYLAPS/AMB-style RC transponders, and installs
`openstint-learn`, which registers a pure RC4 transponder under the number on
its label in one command.

## What it does

On the target Pi (`become: true`):

- Checks the host is **64-bit Debian 13 (Trixie)** (the upstream package is
  arm64/Trixie only) and warns if the board is older than a Pi 3 Model B+.
- Adds upstream's apt repo (`repo.lapbeeps.com`). That repo is **unsigned**
  (`[trusted=yes]` is upstream's own line), so the role also writes
  `/etc/apt/preferences.d/openstint.pref`: only the `openstint` package may come
  from it; anything else it publishes is blocked (priority -1).
- Installs `openstint` (decoder, udev rules, `openstint.service`) and
  `python3-zmq`.
- Renders `/etc/openstint.conf` (gain, registry folder, ZeroMQ port).
- Adds the login user to `users`, so `.rc4` files in `/var/lib/openstint` can be
  renamed or deleted without sudo.
- Installs `/usr/local/bin/openstint-learn`.
- Enables + starts `openstint.service`; optionally locks the ZeroMQ port to one
  CIDR with `ufw`.
- Prints whether the service is active and whether an RTL-SDR is on USB.

## Prerequisites

Run everything below from `deploy/ansible/` in this repo (its `ansible.cfg`
sets the roles path and default inventory).


1. **Image the Pi** with Raspberry Pi Imager (on Omarchy the Flatpak build
   works): **Raspberry Pi OS Lite (64-bit)**, Trixie;
   hostname `racedecoder`; SSH with your public key; username `pi` (or change
   `ansible_user` in `inventory/race_decoders.yml`).
2. Plug the RTL-SDR into the Pi. The loop goes to the SDR's SMA jack.
3. `ansible-galaxy collection install -r requirements.yml` (only
   `community.general` is used, for the opt-in ufw step).

## Run it

```bash
ansible-playbook -i inventory/race_decoders.yml playbooks/provision_race_decoder.yml --syntax-check
ansible-playbook -i inventory/race_decoders.yml playbooks/provision_race_decoder.yml
```

Then on the Pi: `journalctl -u openstint -f` should show an `S` line every
second.

## Variables

| Var | Default | Notes |
| --- | --- | --- |
| `openstint_decoder_gain` | `20` | `-g`; ignored in direct sampling (RTL-SDR v3) |
| `openstint_decoder_registry_dir` | `/var/lib/openstint` | `-s`; the unit's `ReadWritePaths=` expects this path |
| `openstint_decoder_zmq_port` | `5556` | `-p` |
| `openstint_decoder_extra_args` | `""` | e.g. `-b` (bias-tee) or `-d <serial>` |
| `openstint_decoder_manage_ufw` | `false` | when true: allow SSH, allow ZeroMQ from the CIDR below, deny the rest |
| `openstint_decoder_zmq_allowed_cidr` | `192.168.0.0/24` | |
| `openstint_decoder_package_state` | `present` | `latest` upgrades; don't do it on race day |

## Learning a transponder

Learning needs one transponder sitting **still** on the loop for about 12 s
(25 s for an RC4 Hybrid), hands off. On the Pi:

```bash
openstint-learn 8954097
```

It listens to the running decoder (it doesn't touch the radio), shows the
frame rate live, waits for `L … DONE`, renames the auto-numbered `1000.rc4` to
`8954097.rc4`, then waits for one pass with that number to confirm it. The
decoder picks up the new name within a second; no restart, so you can learn a
late arrival mid-event.

Options: `--host` (run it from the laptop against the Pi's feed; then `--dir`
must be a local copy of the folder, so on the Pi is simpler), `--timeout`,
`--verify-timeout 0` to skip the pass check. Exit codes: 0 learned, 1 bad
input/file problem, 2 no DONE before the timeout, 3 already known under a
different number.

It refuses labels 1000–9999, because the decoder hands those out to newly
learned transponders.

## Tests

```bash
python3 -m pytest roles/openstint_decoder/tests -q   # needs pytest; pyzmq for the end-to-end test
```

## Roles used

- [`openstint_decoder`](../roles/openstint_decoder/README.md)
