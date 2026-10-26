# ssm_hybrid_node

Registers a non-EC2 Linux device with AWS Systems Manager as a hybrid managed
node, using its Ethernet MAC address as the device identity, and installs the
CloudWatch agent (signature-checked) in on-prem mode.

- `library/ssm_hybrid_registration.py`: controller-side module (boto3). Finds
  nodes by `MacAddress` tag, replaces stale records, creates one-use
  activations, tags, deletes used activations, and deregisters (`state: absent`).
- `files/cwagent-fetch`: downloads the CloudWatch agent `.deb` and verifies
  its GPG signature against AWS's pinned fingerprint.
- `templates/`: SSM agent config (shared creds, key rotation), CloudWatch
  agent credentials + metrics config.

Usage, IAM setup and variables:
[`docs/register_race_decoder.md`](../../docs/register_race_decoder.md).

## Requirements

- Controller: Ansible >= 2.15, boto3, AWS credentials with
  `docs/iam/race-decoder-registrar.json`
- Target: 64-bit Debian / Raspberry Pi OS, outbound HTTPS to AWS

## Tests

`tests/test_ssm_hybrid_registration.py` covers MAC normalisation and every
reconcile path (new, re-imaged, hand-registered, duplicate, deregistered in
AWS, check mode, cleanup, decommission) with SSM stubbed by botocore's Stubber.
