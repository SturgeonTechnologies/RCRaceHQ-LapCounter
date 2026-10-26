"""Tests for library/ssm_hybrid_registration.py (SSM mocked with botocore Stubber).

Run from deploy/ansible (needs boto3 + ansible-core):
    python3 -m pytest roles/ssm_hybrid_node/tests -q
"""

import datetime
import importlib.util
import pathlib

import pytest

boto3 = pytest.importorskip("boto3")
from botocore.exceptions import ClientError  # noqa: E402
from botocore.stub import ANY, Stubber  # noqa: E402

MODULE = pathlib.Path(__file__).resolve().parents[1] / "library" / "ssm_hybrid_registration.py"
spec = importlib.util.spec_from_file_location("ssm_hybrid_registration", MODULE)
reg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reg)

MAC = "dc:a6:32:01:02:03"
NOW = datetime.datetime(2026, 10, 25, 12, 0, tzinfo=datetime.timezone.utc)
ROLE = "RaceDecoderSSMNode"
OLD, DUPE, GONE = "mi-0000000000000000a", "mi-0000000000000000b", "mi-0000000000000000c"
MI1, MI2 = "mi-00000000000000001", "mi-00000000000000002"


def params(**over):
    p = dict(region="us-west-2", mac_address=MAC, name="racedecoder-dca632010203",
             iam_role=ROLE, tags={"Role": "race-decoder"}, instance_id=None,
             replace_stale=True, expiration_minutes=60, delete_activation_id=None,
             state="present")
    p.update(over)
    return p


@pytest.fixture
def ssm():
    client = boto3.client("ssm", region_name="us-west-2",
                          aws_access_key_id="x", aws_secret_access_key="x")
    with Stubber(client) as stub:
        client.stub = stub
        yield client
        stub.assert_no_pending_responses()


def expect_mac_lookup(ssm, ids):
    ssm.stub.add_response(
        "describe_instance_information",
        {"InstanceInformationList": [{"InstanceId": i} for i in ids]},
        {"Filters": [{"Key": "tag:MacAddress", "Values": [MAC]}]},
    )


def expect_exists(ssm, instance_id, exists):
    ssm.stub.add_response(
        "describe_instance_information",
        {"InstanceInformationList": [{"InstanceId": instance_id}] if exists else []},
        {"Filters": [{"Key": "InstanceIds", "Values": [instance_id]}]},
    )


def expect_activation(ssm):
    ssm.stub.add_response(
        "create_activation",
        {"ActivationId": "act-0123456789abcdef", "ActivationCode": "secret-code-0123456789abcdef"},
        {
            "Description": ANY,
            "DefaultInstanceName": "racedecoder-dca632010203",
            "IamRole": ROLE,
            "RegistrationLimit": 1,
            "ExpirationDate": NOW + datetime.timedelta(minutes=60),
            "Tags": [
                {"Key": "MacAddress", "Value": MAC},
                {"Key": "Name", "Value": "racedecoder-dca632010203"},
                {"Key": "Role", "Value": "race-decoder"},
            ],
        },
    )


# ── normalize_mac ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw", ["DC:A6:32:01:02:03", "dc-a6-32-01-02-03",
                                 "dca6.3201.0203", "dca632010203"])
def test_normalize_mac_accepts_common_formats(raw):
    assert reg.normalize_mac(raw) == MAC


@pytest.mark.parametrize("raw", ["", "dc:a6:32", "zz:a6:32:01:02:03", None])
def test_normalize_mac_rejects_garbage(raw):
    with pytest.raises(ValueError):
        reg.normalize_mac(raw)


def test_desired_tags_identity_wins_over_extra():
    tags = reg.desired_tags(MAC, "n", {"MacAddress": "spoof", "Club": "rcclub"})
    assert tags == {"MacAddress": MAC, "Name": "n", "Club": "rcclub"}


# ── run(): new device ─────────────────────────────────────────────────────

def test_new_device_creates_one_use_activation(ssm):
    expect_mac_lookup(ssm, [])
    expect_activation(ssm)
    out = reg.run(ssm, params(), check_mode=False, now=NOW)
    assert out["needs_registration"] and out["changed"]
    assert (out["activation_id"], out["activation_code"]) == ("act-0123456789abcdef", "secret-code-0123456789abcdef")
    assert out["deregistered"] == []


def test_reimaged_device_replaces_stale_record(ssm):
    expect_mac_lookup(ssm, [OLD])
    ssm.stub.add_response("deregister_managed_instance", {}, {"InstanceId": OLD})
    expect_activation(ssm)
    out = reg.run(ssm, params(), check_mode=False, now=NOW)
    assert out["deregistered"] == [OLD]
    assert out["needs_registration"]


def test_stale_record_without_replace_fails(ssm):
    expect_mac_lookup(ssm, [OLD])
    with pytest.raises(RuntimeError, match="already registered as mi-0000000000000000a"):
        reg.run(ssm, params(replace_stale=False), check_mode=False, now=NOW)


def test_new_device_needs_iam_role(ssm):
    expect_mac_lookup(ssm, [])
    with pytest.raises(RuntimeError, match="iam_role"):
        reg.run(ssm, params(iam_role=None), check_mode=False, now=NOW)


def test_check_mode_makes_no_write_calls(ssm):
    expect_mac_lookup(ssm, [OLD])  # Stubber fails on any unexpected call
    out = reg.run(ssm, params(), check_mode=True, now=NOW)
    assert out["changed"] and out["needs_registration"]
    assert out["deregistered"] == [OLD] and out["activation_code"] is None


# ── run(): already registered ─────────────────────────────────────────────

def test_registered_device_with_tags_is_a_no_op(ssm):
    expect_mac_lookup(ssm, [MI1])
    expect_exists(ssm, MI1, True)
    ssm.stub.add_response(
        "list_tags_for_resource",
        {"TagList": [{"Key": "MacAddress", "Value": MAC},
                     {"Key": "Name", "Value": "racedecoder-dca632010203"},
                     {"Key": "Role", "Value": "race-decoder"}]},
        {"ResourceType": "ManagedInstance", "ResourceId": MI1},
    )
    out = reg.run(ssm, params(instance_id=MI1), check_mode=False, now=NOW)
    assert not out["changed"] and not out["needs_registration"]
    assert out["instance_id"] == MI1


def test_hand_registered_device_gets_missing_tags(ssm):
    expect_mac_lookup(ssm, [])  # registered by hand: no MacAddress tag yet
    expect_exists(ssm, MI1, True)
    ssm.stub.add_response("list_tags_for_resource", {"TagList": []},
                          {"ResourceType": "ManagedInstance", "ResourceId": MI1})
    ssm.stub.add_response(
        "add_tags_to_resource", {},
        {"ResourceType": "ManagedInstance", "ResourceId": MI1, "Tags": [
            {"Key": "MacAddress", "Value": MAC},
            {"Key": "Name", "Value": "racedecoder-dca632010203"},
            {"Key": "Role", "Value": "race-decoder"}]},
    )
    out = reg.run(ssm, params(instance_id=MI1), check_mode=False, now=NOW)
    assert out["changed"] and out["instance_id"] == MI1


def test_registered_device_drops_duplicate_with_same_mac(ssm):
    expect_mac_lookup(ssm, [MI1, DUPE])
    expect_exists(ssm, MI1, True)
    ssm.stub.add_response("deregister_managed_instance", {}, {"InstanceId": DUPE})
    ssm.stub.add_response(
        "list_tags_for_resource",
        {"TagList": [{"Key": "MacAddress", "Value": MAC},
                     {"Key": "Name", "Value": "racedecoder-dca632010203"},
                     {"Key": "Role", "Value": "race-decoder"}]},
        {"ResourceType": "ManagedInstance", "ResourceId": MI1},
    )
    out = reg.run(ssm, params(instance_id=MI1), check_mode=False, now=NOW)
    assert out["deregistered"] == [DUPE] and out["instance_id"] == MI1


def test_local_id_deregistered_in_aws_registers_again(ssm):
    expect_mac_lookup(ssm, [])
    expect_exists(ssm, GONE, False)
    expect_activation(ssm)
    out = reg.run(ssm, params(instance_id=GONE), check_mode=False, now=NOW)
    assert out["needs_registration"] and out["instance_id"] is None


# ── run(): cleanup / decommission ─────────────────────────────────────────

def test_delete_used_activation_tolerates_already_gone(ssm):
    ssm.stub.add_client_error("delete_activation", service_error_code="InvalidActivation",
                              expected_params={"ActivationId": "act-0123456789abcdef"})
    expect_mac_lookup(ssm, [MI1])
    expect_exists(ssm, MI1, True)
    ssm.stub.add_response(
        "list_tags_for_resource",
        {"TagList": [{"Key": "MacAddress", "Value": MAC},
                     {"Key": "Name", "Value": "racedecoder-dca632010203"},
                     {"Key": "Role", "Value": "race-decoder"}]},
        {"ResourceType": "ManagedInstance", "ResourceId": MI1},
    )
    out = reg.run(ssm, params(instance_id=MI1, delete_activation_id="act-0123456789abcdef"),
                  check_mode=False, now=NOW)
    assert out["instance_id"] == MI1


def test_delete_activation_other_errors_raise(ssm):
    ssm.stub.add_client_error("delete_activation", service_error_code="AccessDenied",
                              expected_params={"ActivationId": "act-0123456789abcdef"})
    with pytest.raises(ClientError):
        reg.run(ssm, params(delete_activation_id="act-0123456789abcdef"), check_mode=False, now=NOW)


def test_absent_deregisters_every_node_for_the_mac(ssm):
    expect_mac_lookup(ssm, [MI1, MI2])
    ssm.stub.add_response("deregister_managed_instance", {}, {"InstanceId": MI1})
    ssm.stub.add_response("deregister_managed_instance", {}, {"InstanceId": MI2})
    out = reg.run(ssm, params(state="absent"), check_mode=False, now=NOW)
    assert out["deregistered"] == [MI1, MI2] and out["changed"]
