# race_hotspot

Optional event Wi-Fi on the lap counter Pi, with a captive portal.

1. The built-in radio (`wlan0`) runs an access point, open `RC Race Event` by
   default. DHCP and DNS come from **race_dns** (pulled in by `meta/main.yml`).
2. A new device's plain-HTTP requests are redirected to `http://race/`. That is
   what makes phones and laptops pop the "sign in to network" sheet. HTTPS and
   everything else is refused (fast reset) until then.
3. Opening `http://race/` adds the device to the nftables set `allowed` for
   `race_hotspot_access_timeout` (12 h). From then on it gets internet through
   the uplinks (`eth0`, plus `wlan1` if listed), NATed.

The open Wi-Fi can only reach DHCP, DNS and the web port on the Pi. SSH and the
decoder's ZeroMQ feed stay closed to it.

## Wired side (`race_hotspot_web_on_eth0`)

Off by default. When `true`, the event page is also served on `eth0` for a
laptop at the timing table or a TV in the pits:

- The web server listens on every interface, not only `10.77.0.1`.
- avahi publishes it as **`http://<pi hostname>.local/`** (e.g.
  `http://racedecoder.local/`). A bare `race` only resolves on the hotspot,
  because we don't control the track router's DNS.
- Clients that aren't on the hotspot subnet just get the page: no redirect to
  `http://race/` and no internet grant (they aren't routed through the Pi).
- With ufw on, port 80 and mDNS are allowed in on `eth0` from
  `race_hotspot_web_eth0_allowed_cidr` (`any` by default, since the track LAN isn't
  known when you provision; set a CIDR to narrow it). Setting
  `race_hotspot_web_on_eth0: false` again removes those rules and the mDNS record.

## Pieces

| File on the Pi | What |
|---|---|
| NetworkManager profile `race-hotspot` | AP on `wlan0`, static `10.77.0.1/24`, IPv6 off |
| `/etc/race/race-portal.nft` + `race-portal-firewall.service` | Own `inet race_portal` table: portal redirect, input lockdown, forward + NAT. Never flushes other tables (ufw is left alone). |
| `/usr/local/sbin/race-portal` + `race-portal.service` | Stdlib Python HTTP server on `10.77.0.1:80` (all interfaces with `race_hotspot_web_on_eth0`). Unprivileged (`DynamicUser`) with only `CAP_NET_ADMIN` + `CAP_NET_BIND_SERVICE`. |
| `/etc/sysctl.d/90-race-hotspot.conf` | `net.ipv4.ip_forward = 1` |
| `/etc/avahi/services/race-web.service` | Only with `race_hotspot_web_on_eth0`: mDNS `_http._tcp` record for the page |

When the lap counter web app lands it takes over the landing page on port 80
and does the same `nft add element inet race_portal allowed { <ip> timeout 12h }`
on a client's first visit; `race-portal` then goes away.

## Safety

- The role refuses to run if the Pi's default route is on the hotspot
  interface (you'd lose SSH and the uplink). Provision over Ethernet.
- It sets the Wi-Fi country (`raspi-config`) because Raspberry Pi OS keeps the
  radio blocked until one is set.
- If `openstint_decoder_manage_ufw` is on, it adds the ufw allow and route rules
  the hotspot needs.

## Vars

| Var | Default | |
|---|---|---|
| `race_hotspot_ssid` | `RC Race Event` | |
| `race_hotspot_passphrase` | `""` (open) | 8–63 chars for WPA2; vault it |
| `race_hotspot_uplinks` | `[eth0]` | add `wlan1` for the USB Wi-Fi uplink |
| `race_hotspot_access_timeout` | `12h` | also the DHCP lease time |
| `race_hotspot_country` | `US` | |
| `race_hotspot_band` / `_channel` | `bg` / `6` | |
| `race_hotspot_address` / `_prefix` / `_netmask` | `10.77.0.1` / `24` / `255.255.255.0` | keep the three consistent |
| `race_hotspot_hostname` / `_domain` | `race` / `lan` | |
| `race_hotspot_web_on_eth0` | `false` | also serve the event page on the wired side |
| `race_hotspot_web_eth0_interface` | `eth0` | |
| `race_hotspot_web_eth0_allowed_cidr` | `any` | ufw source for the wired page |

Turning it off later: set `race_hotspot_enabled: false` in the inventory to stop
the playbook applying it. That doesn't remove an existing hotspot; on the Pi run
`sudo nmcli connection delete race-hotspot && sudo systemctl disable --now race-portal race-portal-firewall`.

## Checks

```
nmcli connection show --active            # race-hotspot on wlan0
sudo nft list set inet race_portal allowed # who's been let through
journalctl -u race-portal -f               # "allowed 10.77.0.x for 12h"
```
Tests: `python3 -m pytest roles/race_hotspot/tests -q`
