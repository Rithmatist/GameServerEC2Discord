import base64
import json
import logging
import os
from typing import Any, Dict, Optional

import boto3
from botocore.client import BaseClient
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)

DISCORD_APP_PUBLIC_KEY = os.environ["DISCORD_APP_PUBLIC_KEY"]
MANAGER_INSTRUCTION_SNS_TOPIC_ARN = os.environ[
    "MANAGER_INSTRUCTION_SNS_TOPIC_ARN"
]

_sns_client: BaseClient = boto3.client("sns")

# Discord interaction constants we care about
PING_INTERACTION = 1
APPLICATION_COMMAND_INTERACTION = 2
DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE = 5


def _json_response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
    }


def _get_header(headers: Optional[Dict[str, str]], name: str) -> Optional[str]:
    if not headers:
        return None

    lowercase = name.lower()
    for key, value in headers.items():
        if key and key.lower() == lowercase:
            return value
    return None


def _get_body_bytes(event: Dict[str, Any]) -> bytes:
    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        return base64.b64decode(body)
    if isinstance(body, bytes):
        return body
    return body.encode("utf-8")


def _verify_request(event: Dict[str, Any], body_bytes: bytes) -> bool:
    signature = _get_header(event.get("headers"), "x-signature-ed25519")
    timestamp = _get_header(event.get("headers"), "x-signature-timestamp")

    if not signature or not timestamp:
        return False

    verify_key = VerifyKey(bytes.fromhex(DISCORD_APP_PUBLIC_KEY))

    try:
        verify_key.verify(
            timestamp.encode("utf-8") + body_bytes, bytes.fromhex(signature)
        )
        return True
    except BadSignatureError:
        return False


def _find_server_option_value(
    interaction: Dict[str, Any],
) -> Optional[str]:
    data = interaction.get("data", {})
    options = data.get("options") or []
    for option in options:
        if option.get("name") == "server":
            return option.get("value")
    return None


def _publish_sns_message(
    command: str,
    interaction_id: str,
    interaction_token: str,
    region: str,
    server_id: str,
) -> None:
    LOGGER.info(
        "Publishing %s command for server %s in region %s (interaction %s)",
        command,
        server_id,
        region,
        interaction_id,
    )

    _sns_client.publish(
        TopicArn=MANAGER_INSTRUCTION_SNS_TOPIC_ARN,
        Message=json.dumps(
            {
                "interactionId": interaction_id,
                "interactionToken": interaction_token,
                "command": command,
                "serverId": server_id,
                "region": region,
                "instanceRegion": region,
            }
        ),
    )


def handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    body_bytes = _get_body_bytes(event)

    if not _verify_request(event, body_bytes):
        LOGGER.warning("Invalid signature on incoming interaction")
        return _json_response(401, {"error": "Invalid signature"})

    try:
        interaction = json.loads(body_bytes.decode("utf-8"))
    except json.JSONDecodeError:
        LOGGER.exception("Unable to parse request body")
        return _json_response(400, {"error": "Invalid JSON body"})

    interaction_type = interaction.get("type")
    LOGGER.info("Interaction type: %s", interaction_type)

    if interaction_type == PING_INTERACTION:
        return _json_response(200, {"type": PING_INTERACTION})

    if interaction_type != APPLICATION_COMMAND_INTERACTION:
        LOGGER.warning("Unsupported interaction type: %s", interaction_type)
        return _json_response(400, {"error": "Unsupported interaction type"})

    server_value = _find_server_option_value(interaction)
    if not server_value or "|" not in server_value:
        LOGGER.warning("Missing server selection in interaction %s", interaction)
        return _json_response(400, {"error": "Missing server option"})

    command_name = interaction.get("data", {}).get("name")
    interaction_id = interaction.get("id")
    interaction_token = interaction.get("token")

    if not all([command_name, interaction_id, interaction_token]):
        LOGGER.error("Interaction missing required fields: %s", interaction)
        return _json_response(400, {"error": "Invalid interaction payload"})
    region, server_id = server_value.split("|", 1)

    _publish_sns_message(
        command=command_name,
        interaction_id=interaction_id,
        interaction_token=interaction_token,
        region=region,
        server_id=server_id,
    )

    return _json_response(
        200,
        {"type": DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE},
    )


__all__ = ["handler"]
