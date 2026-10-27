# register_race_decoder

Registers race-decoder Pis with **AWS Systems Manager** as hybrid managed nodes,
using each Pi's **Ethernet MAC address** as its identity, and installs the
**CloudWatch agent** for a heartbeat and basic health metrics. Run
`provision_race_decoder.yml` first; this playbook adds remote access on top.

Why SSM: the Pi only makes outbound HTTPS calls, so you get a shell
(Session Manager), Run Command and inventory on a track's Wi-Fi or a phone
hotspot, with no port forwarding, VPN or SSH keys.

## What it does

1. **Identity.** Reads the MAC of the first wired NIC (`eth*`/`end*`/`enx*`/`enp*`,
   or `ssm_hybrid_node_interface`) and looks it up in `ssm_hybrid_node_devices`.
   A listed MAC gets its registry name and tags; an unlisted one becomes
   `racedecoder-<mac>` (or is refused when `ssm_hybrid_node_require_known_mac: true`).
2. **Reconcile with SSM (on the controller).** Finds managed nodes tagged
   `MacAddress=<mac>`.
   - Pi already registered (`/var/lib/amazon/ssm/registration` exists and the
     `mi-` ID is still in SSM): only fixes missing tags. No changes otherwise.
   - Pi not registered, or re-imaged: deregisters the old `mi-` record for that
     MAC, then creates a **one-use activation** (limit 1, expires in 1 hour)
     carrying the name and tags.
3. **Register (on the Pi).** Downloads `ssm-setup-cli` from the Region (it
   checks the agent's signature itself), installs the agent and registers.
   The tool is deleted afterwards, as AWS asks. The activation code only
   appears in `no_log` tasks.
4. **Clean up.** Tags the new node and deletes the used activation.
5. **Agent config.** `/etc/amazon/ssm/amazon-ssm-agent.json`: shares the role's
   short-lived credentials with root's default profile (for the CloudWatch
   agent) and rotates the Pi's private key every 30 days.
6. **CloudWatch agent.** Downloads the arm64 `.deb`, checks its GPG signature
   against AWS's pinned key fingerprint (`937616F3…3B789C72`), installs it, and
   runs it in `onPremise` mode publishing to namespace `RaceDecoder`, every 60 s:
   CPU, memory, root disk, swap, and the number of `openstint_*` processes.
   Every metric has a `Device=<name>` dimension, so a re-imaged Pi keeps its
   series.

## One-time AWS setup (us-west-2)

The Pi assumes a service role named **`RaceDecoderSSMNode`**. It doesn't
exist yet. Create it from the repo root, with an admin profile:

```bash
aws iam create-role --role-name RaceDecoderSSMNode \
  --assume-role-policy-document file://docs/iam/race-decoder-ssm-node-trust.json \
  --description "Race-decoder Pis registered via SSM hybrid activation"
aws iam attach-role-policy --role-name RaceDecoderSSMNode \
  --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
aws iam put-role-policy --role-name RaceDecoderSSMNode \
  --policy-name RaceDecoderMetrics \
  --policy-document file://docs/iam/race-decoder-ssm-node-metrics.json
```

Check it:

```bash
aws iam get-role --role-name RaceDecoderSSMNode --query 'Role.AssumeRolePolicyDocument'
aws iam list-attached-role-policies --role-name RaceDecoderSSMNode
aws iam list-role-policies --role-name RaceDecoderSSMNode
```

You should see `ssm.amazonaws.com` with the account/ARN conditions,
`AmazonSSMManagedInstanceCore`, and `RaceDecoderMetrics`.

- **Trust** (`race-decoder-ssm-node-trust.json`): only SSM in this account and
  Region can hand out this role.
- **Metrics** (`race-decoder-ssm-node-metrics.json`): `PutMetricData` only into
  the `RaceDecoder` namespace. No log shipping yet, so no Logs permissions.

**Who runs the playbook** needs the permissions in
`docs/iam/race-decoder-registrar.json`: create/delete activations, look up and
tag nodes, deregister only nodes tagged `Role=race-decoder`, and pass only this
role, only to SSM. An admin profile on your laptop already covers it. Attach it
to a dedicated IAM user/role if this ever runs from CI.

## Run it

```bash
python3 -m pip install --user boto3   # the controller-side module uses boto3
AWS_PROFILE=<admin> ansible-playbook -i inventory/race_decoders.yml \
  playbooks/register_race_decoder.yml --check   # shows what it would do, no writes
AWS_PROFILE=<admin> ansible-playbook -i inventory/race_decoders.yml \
  playbooks/register_race_decoder.yml
```

Then:

```bash
aws ssm describe-instance-information --region us-west-2 \
  --filters Key=tag:Role,Values=race-decoder \
  --query 'InstanceInformationList[].[InstanceId,Name,PingStatus,IPAddress]' --output table
aws ssm start-session --region us-west-2 --target mi-xxxxxxxxxxxxxxxxx
```

`start-session` needs the Session Manager plugin for the AWS CLI on your laptop
(`yay -S aws-session-manager-plugin` on Omarchy).

## Registering a new Pi

1. Image it and run `provision_race_decoder.yml` (needs SSH on your LAN once).
2. On the Pi, `ip -br link` shows the MAC of `eth0`. Add it to
   `ssm_hybrid_node_devices` in `inventory/race_decoders.yml` with a name.
3. Run `register_race_decoder.yml`. From then on it's reachable through SSM
   wherever it is plugged in.

Re-imaging the same Pi and running both playbooks again replaces its old record
automatically (`ssm_hybrid_node_replace_stale`).

## Variables

| Var | Default | Notes |
| --- | --- | --- |
| `ssm_hybrid_node_region` | `us-west-2` | Activation, agent download and metrics Region |
| `ssm_hybrid_node_iam_role` | `RaceDecoderSSMNode` | Service role from the setup above |
| `ssm_hybrid_node_interface` | `""` | Force a NIC; empty = first wired one |
| `ssm_hybrid_node_devices` | `{}` | MAC → `{name, tags}` registry (any MAC format) |
| `ssm_hybrid_node_require_known_mac` | `false` | Refuse MACs not in the registry |
| `ssm_hybrid_node_name_prefix` | `racedecoder` | Unlisted devices: `<prefix>-<mac>` |
| `ssm_hybrid_node_tags` | `{Role: race-decoder}` | On every node; registry tags merge on top |
| `ssm_hybrid_node_replace_stale` | `true` | Deregister old records for the same MAC |
| `ssm_hybrid_node_key_rotate_days` | `30` | Pi private-key rotation; 0 = never |
| `ssm_hybrid_node_cloudwatch_enabled` | `true` | |
| `ssm_hybrid_node_cloudwatch_upgrade` | `false` | Reinstall latest agent each run |
| `ssm_hybrid_node_metrics_namespace` | `RaceDecoder` | Must match the metrics policy |
| `ssm_hybrid_node_procstat_exe` | `openstint_` | Regex for the decoder process count |

## Cost (checked 2026-10-25)

- Registering hybrid nodes: **free**, no per-node charge. AWS removed the paid
  advanced-instances tier on 2026-06-30.
- **Session Manager $0.05 per session, Run Command $0.002 per invocation** on
  hybrid nodes, billed since 2026-09-30.
- CloudWatch: 5 custom metrics × $0.30 ≈ **$1.50 per Pi per month**.

Sources: [SSM pricing](https://aws.amazon.com/systems-manager/pricing/),
[managed nodes / tier change](https://docs.aws.amazon.com/systems-manager/latest/userguide/fleet-manager-configure-instance-tiers.html).

## Decommission

```bash
# from the controller; deregisters every node tagged with that MAC
ansible localhost -m ssm_hybrid_registration -M roles/ssm_hybrid_node/library \
  -a "region=us-west-2 mac_address=dc:a6:32:01:02:03 name=x state=absent"
```

## Not done yet

- **Alarms.** Next step once real metric names show up in the console: a
  `procstat_lookup_pid_count` alarm with missing data = breaching catches both
  "decoder stopped" and "Pi offline".
- **Logs.** OpenStint logs to journald, which the CloudWatch agent can't read.
  Shipping `S`/`P` lines needs a file sink first.
- **State Manager association** that re-runs the provision playbook through
  `AWS-ApplyAnsiblePlaybooks`, for Pis that are never on your LAN again.
