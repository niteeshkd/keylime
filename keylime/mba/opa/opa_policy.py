import json
import re
from typing import Optional, Set

from opa_client.errors import *
from opa_client.opa import OpaClient

from keylime import config, keylime_logging
from keylime.failure import Component, Failure

logger = keylime_logging.init_logging("mba_opa")


def policy_load(policy_path: Optional[str] = None) -> str:
    """
    Load (and validates) an actual policy file.
    :param policy_path: <optional> name of policy file to load
    :returns: a string defining the policy.
    Errors: if the policy file cannot be read, this function may cause exceptions.
    """
    try:
        if policy_path is None:
            policy_path = config.get("tenant", "mb_refstate")
        with open(policy_path, encoding="utf-8") as f:
            mb_policy_data = f.read()
            return mb_policy_data

    except Exception as e:
        raise ValueError from e


def policy_is_valid(mb_refstate: Optional[str]) -> bool:
    """
    Returns true if the policy argument is a nonempty valid policy in rego.
    """
    if not mb_refstate:
        return False

    # Return False if policy does not contain package name and 'allow' rule
    pkg_found: bool = False
    allow_rule_found: bool = False
    lines = re.split("\n", mb_refstate)
    for line in lines:
        if re.match(r"^\s*package\s*\S+", line):
            pkg_found = True
        if re.match(r"^\s*[default]*\s*allow\s*", line):
            allow_rule_found = True
        if pkg_found and allow_rule_found:
            break
    if not (pkg_found and allow_rule_found):
        return False

    return True


def bootlog_evaluate(
    mb_refstate_str: Optional[str],
    mb_measurement_data: Optional[str],
    pcrs_inquote: Set[int],
    agent_id: str,
    attestation_count: int,
) -> Failure:
    """
    Evaluating a measured boot event log against a policy
    :param policy_data: policy definition (aka "refstate") (as a string).
    :param measurement_data: parsed measured boot event log as produced by `parse_bootlog`
    :param pcrsInQuote: a set of PCRs provided by the quote.
    :param agent_id: the UUID of the keylime agent sending this data.
    :param attestation_count: number of times the measured boot attestation has been done.
    :returns: list of all failures encountered while evaluating the boot log against the policy.
    """
    failure = Failure(Component.MEASURED_BOOT)

    # Ger the information about the OPA server
    server_ip = config.get("verifier", "opa_server_ip", fallback="127.0.0.1")
    server_port = config.get("verifier", "opa_server_port", fallback="8181")
    server_cert = config.get("verifier", "opa_server_cert", fallback="")

    # OPA server connection
    if not server_cert:
        client = OpaClient(
            host=server_ip,
            port=int(server_port),
        )
    else:
        client = OpaClient(
            host="https://{}".format(server_ip),
            port=int(server_port),
            ssl=True,
            cert=server_cert,
        )

    # OPA requires to have unique mapping between policy name/id (created under v1/policies/)
    # and policy path (created under v1/data/ using the package name mentioned in the policy
    # file in rego) for each policy. Since, there is only one measured boot policy for an
    # agent node at any point of time, we can use the unique agent id for the package name
    # and also for the policy name.
    uniq_policy_name = "policy_" + agent_id.replace("-", "_")

    # Upload the policy to OPA server only during the first round of attestation.
    if attestation_count == 0:
        # Check connection to the OPA server
        try:
            client.check_connection()
        except ConnectionsError:
            logger.error("Could not connect to OPA server with IP = %s !", server_ip)
            failure.add_event("opa_server_connection_failed", f"Connection to the OPA server {server_ip} failed.", True)
            return failure

        # Modify the policy to have uniq package name.
        modified_policy_lines = policy_lines = re.split("\n", mb_refstate_str)
        for i in range(len(policy_lines)):
            m = re.match(r"^\s*package\s*(\S+)", policy_lines[i])
            if m:
                modified_policy_lines[i] = re.sub(
                    r"^\s*package\s*(\S+)", f"package {uniq_policy_name}", policy_lines[i]
                )
                break
        modified_policy_str = "\n".join(modified_policy_lines)

        # Upload the policy to the OPA server
        logger.info("Uploading the policy to the OPA server")
        try:
            client.update_opa_policy_fromstring(modified_policy_str, uniq_policy_name)
        except RegoParseError:
            logger.error(
                "Uploading the policy to the OPA server failed for agent %s, policy=%s",
                agent_id,
                modified_policy_str,
            )
            failure.add_event(
                "upload_opa_policy_failed",
                {
                    "context": "Uploading the policy to the OPA server",
                    "policy": modified_policy_str,
                },
                True,
            )

            return failure

    # Check the boot log against the policy on the OPA server
    logger.info("Checking the boot log against the policy")
    mb_data = {"input": mb_measurement_data}
    perm = client.check_permission(input_data=mb_data, policy_name=uniq_policy_name, rule_name="allow")
    if perm["result"] is not True:
        logger.error(
            "Boot log evaluation failed against OPA policy for agent %s, refstate=%s, reason=%s",
            agent_id,
            mb_refstate_str,
            perm["result"],
        )
        failure.add_event(
            "bootlog_evaluation_failed",
            {
                "context": "Bootlog evaluation against OPA policy",
                "refstate": mb_refstate_str,
                "reason": perm["result"],
            },
            True,
        )

    # Close the connection
    del client

    return failure
