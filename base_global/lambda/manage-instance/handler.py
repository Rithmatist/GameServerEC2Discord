import json
import logging
import os
from typing import Any, Dict, Optional
from urllib import error, request

import boto3
from botocore.client import BaseClient
from botocore.exceptions import ClientError

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)

DISCORD_APP_ID = os.environ["DISCORD_APP_ID"]
DISCORD_BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
DISCORD_BASE_URL = "https://discord.com/api/v10"


def _get_ec2_client(region: str) -> BaseClient:
    return boto3.client("ec2", region_name=region)


def _find_instance(ec2_client: BaseClient, server_id: str) -> Optional[Dict[str, Any]]:
    response = ec2_client.describe_instances(
        Filters=[
            {
                "Name": "tag:GameServerEC2Discord:ServerId",
                "Values": [server_id],
            }
        ]
    )

    for reservation in response.get("Reservations", []):
        for instance in reservation.get("Instances", []):
            return instance
    return None


def _get_tag(tags: Optional[list], tag_key: str) -> Optional[str]:
    if not tags:
        return None
    for tag in tags:
        if tag.get("Key") == tag_key:
            return tag.get("Value")
    return None


def _format_address_message(instance: Dict[str, Any]) -> str:
    public_dns = instance.get("PublicDnsName")
    public_ip = instance.get("PublicIpAddress")
    tags = instance.get("Tags")
    hostname = _get_tag(tags, "GameServerEC2Discord:Hostname")
    main_port = _get_tag(tags, "GameServerEC2Discord:MainPort")

    lines = ["Addresses:"]
    if public_ip:
        lines.append(f"- **`{public_ip}:{main_port}`**")
    if public_dns:
        lines.append(f"- `{public_dns}:{main_port}`")
    if hostname:
        lines.append(f"- `{hostname}:{main_port}`")

    return "\n".join(lines)


def _send_ec2_command(
    server_id: str, region: str, command: str
) -> str:
    LOGGER.info(
        "Executing command %s for server %s in region %s",
        command,
        server_id,
        region,
    )
    ec2_client = _get_ec2_client(region)
    instance = _find_instance(ec2_client, server_id)

    if not instance or not instance.get("InstanceId"):
        return f"Instance with server ID {server_id} not found on region {region}"

    instance_id = instance["InstanceId"]

    try:
        if command == "start":
            ec2_client.start_instances(InstanceIds=[instance_id])
            return "Starting..."
        if command == "stop":
            ec2_client.stop_instances(InstanceIds=[instance_id])
            return "Stopping..."
        if command == "restart":
            ec2_client.reboot_instances(InstanceIds=[instance_id])
            return "Rebooting..."
        if command == "status":
            state = instance.get("State", {}).get("Name", "unknown")
            return f"State: {state}"
        if command == "ip":
            return _format_address_message(instance)
    except ClientError as exc:
        LOGGER.exception("EC2 command failed")
        return f"Error executing command:\n```\n{exc}\n```"

    return "Unknown command"


def _parse_sns_message(event: Dict[str, Any]) -> Dict[str, Any]:
    record = (event.get("Records") or [{}])[0]
    payload = record.get("Sns", {}).get("Message", "{}")
    return json.loads(payload)


def _patch_interaction(interaction_token: str, content: str) -> None:
    url = f"{DISCORD_BASE_URL}/webhooks/{DISCORD_APP_ID}/{interaction_token}/messages/@original"
    data = json.dumps({"content": content}).encode("utf-8")
    headers = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json",
    }

    req = request.Request(url, data=data, headers=headers, method="PATCH")
    try:
        with request.urlopen(req) as response:
            LOGGER.info("Discord response status: %s", response.status)
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        LOGGER.warning(
            "Discord API error (%s): %s",
            exc.code,
            body,
        )
    except error.URLError:
        LOGGER.exception("Failed to call Discord API")


def handler(event: Dict[str, Any], _context: Any) -> None:
    message = _parse_sns_message(event)
    command = message.get("command")
    interaction_token = message.get("interactionToken")
    server_id = message.get("serverId")
    region = message.get("instanceRegion")

    if not all([command, interaction_token, server_id, region]):
        LOGGER.warning("Incomplete SNS message payload: %s", message)
        return

    ec2_message = _send_ec2_command(server_id, region, command)

    LOGGER.info("Updating Discord interaction with message:\n%s", ec2_message)
    _patch_interaction(interaction_token, ec2_message)


__all__ = ["handler"]
