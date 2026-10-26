#!/usr/bin/python
# -*- coding: utf-8 -*-
"""Register a non-EC2 device with SSM, keyed by its Ethernet MAC address."""

from __future__ import annotations

DOCUMENTATION = r"""
module: ssm_hybrid_registration
short_description: MAC-keyed SSM hybrid activation for one device
description:
  - Treats the device's Ethernet MAC address as its stable identity. Managed
    nodes carry a C(MacAddress) tag, so a re-imaged Pi (same MAC, new
    C(mi-) ID) replaces its old record instead of piling up duplicates.
  - With I(instance_id) unset (device not registered yet), deregisters any
    node already tagged with this MAC (when I(replace_stale)) and creates a
    one-use activation (limit 1) that carries the device's name and tags.
  - With I(instance_id) set, makes sure that node carries the tags and
    deregisters any other node with the same MAC. If that node no longer
    exists in SSM, it behaves as if I(instance_id) were unset.
  - I(state=absent) deregisters every node tagged with this MAC.
  - Runs on the controller (delegate_to localhost) with boto3 default
    credentials.
options:
  region: {type: str, required: true}
  mac_address: {type: str, required: true}
  name: {type: str, required: true, description: DefaultInstanceName shown in Fleet Manager}
  iam_role: {type: str, description: Service role the device assumes. Needed to create an activation.}
  tags: {type: dict, default: {}}
  instance_id: {type: str, description: mi- ID from the device's registration file, if any}
  replace_stale: {type: bool, default: true}
  expiration_minutes: {type: int, default: 60}
  delete_activation_id: {type: str, description: Delete this (used) activation}
  state: {type: str, choices: [present, absent], default: present}
"""

RETURN = r"""
instance_id: {description: Registered mi- ID still valid in SSM, or null, type: str}
needs_registration: {description: True when the device must run ssm-setup-cli, type: bool}
activation_id: {type: str}
activation_code: {description: Secret. Use no_log on the task., type: str}
deregistered: {type: list}
"""

import datetime
import re

from ansible.module_utils.basic import AnsibleModule

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
except ImportError:  # reported via fail_json in main()
    boto3 = None

MAC_TAG = "MacAddress"
MAC_RE = re.compile(r"^([0-9a-f]{2}:){5}[0-9a-f]{2}$")


def normalize_mac(raw):
    """Lower-case, colon-separated; accepts '-' / '.' / no separators."""
    digits = re.sub(r"[^0-9a-fA-F]", "", raw or "").lower()
    mac = ":".join(digits[i:i + 2] for i in range(0, len(digits), 2))
    if not MAC_RE.match(mac):
        raise ValueError(f"not a MAC address: {raw!r}")
    return mac


def desired_tags(mac, name, extra):
    tags = {str(k): str(v) for k, v in (extra or {}).items()}
    tags.update({MAC_TAG: mac, "Name": name})
    return tags


def nodes_for_mac(ssm, mac):
    pages = ssm.get_paginator("describe_instance_information").paginate(
        Filters=[{"Key": f"tag:{MAC_TAG}", "Values": [mac]}]
    )
    return [n["InstanceId"] for page in pages for n in page["InstanceInformationList"]]


def node_exists(ssm, instance_id):
    resp = ssm.describe_instance_information(
        Filters=[{"Key": "InstanceIds", "Values": [instance_id]}]
    )
    return bool(resp["InstanceInformationList"])


def missing_tags(ssm, instance_id, wanted):
    resp = ssm.list_tags_for_resource(ResourceType="ManagedInstance", ResourceId=instance_id)
    have = {t["Key"]: t["Value"] for t in resp.get("TagList", [])}
    return {k: v for k, v in wanted.items() if have.get(k) != v}


def to_tag_list(tags):
    return [{"Key": k, "Value": v} for k, v in sorted(tags.items())]


def run(ssm, p, check_mode, now=None):
    """Pure decision + API logic; returns the result dict. Raises on API errors."""
    mac = normalize_mac(p["mac_address"])
    wanted = desired_tags(mac, p["name"], p["tags"])
    result = {"changed": False, "instance_id": None, "needs_registration": False,
              "activation_id": None, "activation_code": None, "deregistered": []}

    def deregister(ids):
        for node in ids:
            if not check_mode:
                ssm.deregister_managed_instance(InstanceId=node)
            result["deregistered"].append(node)
            result["changed"] = True

    if p.get("delete_activation_id"):
        if not check_mode:
            try:
                ssm.delete_activation(ActivationId=p["delete_activation_id"])
            except ClientError as err:  # already gone / expired is fine
                if err.response["Error"]["Code"] != "InvalidActivation":
                    raise
        result["changed"] = True

    found = nodes_for_mac(ssm, mac)

    if p["state"] == "absent":
        deregister(found)
        return result

    current = p.get("instance_id") or None
    if current and not node_exists(ssm, current):
        current = None  # deregistered behind our back: register again

    stale = [n for n in found if n != current]
    if stale and not p["replace_stale"]:
        raise RuntimeError(
            f"{mac} is already registered as {', '.join(stale)}; "
            "set replace_stale=true or deregister it first"
        )
    deregister(stale)

    if current:
        result["instance_id"] = current
        add = missing_tags(ssm, current, wanted)
        if add:
            if not check_mode:
                ssm.add_tags_to_resource(ResourceType="ManagedInstance",
                                         ResourceId=current, Tags=to_tag_list(add))
            result["changed"] = True
        return result

    if not p.get("iam_role"):
        raise RuntimeError("iam_role is required to create an activation")
    result["needs_registration"] = True
    result["changed"] = True
    if check_mode:
        return result
    now = now or datetime.datetime.now(datetime.timezone.utc)
    act = ssm.create_activation(
        Description=f"One-use registration for {p['name']} ({mac})",
        DefaultInstanceName=p["name"],
        IamRole=p["iam_role"],
        RegistrationLimit=1,
        ExpirationDate=now + datetime.timedelta(minutes=p["expiration_minutes"]),
        Tags=to_tag_list(wanted),
    )
    result["activation_id"] = act["ActivationId"]
    result["activation_code"] = act["ActivationCode"]
    return result


def main():
    module = AnsibleModule(
        argument_spec=dict(
            region=dict(type="str", required=True),
            mac_address=dict(type="str", required=True),
            name=dict(type="str", required=True),
            iam_role=dict(type="str"),
            tags=dict(type="dict", default={}),
            instance_id=dict(type="str"),
            replace_stale=dict(type="bool", default=True),
            expiration_minutes=dict(type="int", default=60),
            delete_activation_id=dict(type="str"),
            state=dict(type="str", choices=["present", "absent"], default="present"),
        ),
        supports_check_mode=True,
    )
    if boto3 is None:
        module.fail_json(msg="boto3 is required on the controller")
    ssm = boto3.client("ssm", region_name=module.params["region"])
    try:
        result = run(ssm, module.params, module.check_mode)
    except (ValueError, RuntimeError) as err:
        module.fail_json(msg=str(err))
    except (BotoCoreError, ClientError) as err:
        module.fail_json(msg=f"SSM API error: {err}")
    module.exit_json(**result)


if __name__ == "__main__":
    main()
