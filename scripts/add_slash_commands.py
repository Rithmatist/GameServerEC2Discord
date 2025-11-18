import json
import os
import sys
from pathlib import Path
from typing import Dict, List

import requests

BASE_URL = "https://discord.com/api/v10"
SCRIPTS_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPTS_DIR.parent
SERVERS_PATH = SCRIPTS_DIR / "servers.json"
ENV_FILE = ROOT_DIR / ".env"


def _load_env_file() -> None:
    if not ENV_FILE.exists():
        return

    with ENV_FILE.open("r", encoding="utf-8") as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        print(f"Missing required environment variable: {name}", file=sys.stderr)
        sys.exit(1)
    return value


def _load_servers() -> List[Dict[str, str]]:
    if not SERVERS_PATH.exists():
        print(
            f"{SERVERS_PATH} not found. Copy scripts/servers.example.json and edit it.",
            file=sys.stderr,
        )
        sys.exit(1)

    with SERVERS_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def _build_command_payload(servers: List[Dict[str, str]]) -> List[Dict[str, object]]:
    server_choices = [
        {
            "name": server["choiceDisplayName"],
            "value": f"{server['region']}|{server['gameServerId']}",
        }
        for server in servers
    ]

    server_option = {
        "type": 3,
        "name": "server",
        "name_localizations": {"pt-BR": "servidor"},
        "description": "Which server to run the command for",
        "description_localizations": {
            "pt-BR": "Para qual servidor executar o comando"
        },
        "required": True,
        "choices": server_choices,
    }

    commands = [
        {
            "name": "start",
            "name_localizations": {"pt-BR": "iniciar"},
            "description": "Starts a server",
            "description_localizations": {"pt-BR": "Inicia um servidor"},
            "include_option": True,
        },
        {
            "name": "stop",
            "name_localizations": {"pt-BR": "parar"},
            "description": "Stops a server, if it's online",
            "description_localizations": {
                "pt-BR": "Desliga um servidor, se estiver online"
            },
            "include_option": True,
        },
        {
            "name": "restart",
            "name_localizations": {"pt-BR": "reiniciar"},
            "description": "Restarts a server, if it's online",
            "description_localizations": {
                "pt-BR": "Reinicia um servidor, se estiver online"
            },
            "include_option": True,
        },
        {
            "name": "ip",
            "description": "Shows the server IP address",
            "description_localizations": {
                "pt-BR": "Exibe o endereço IP do servidor"
            },
            "include_option": True,
        },
        {
            "name": "status",
            "description": "Shows server host status",
            "description_localizations": {
                "pt-BR": "Exibe o estado do host do servidor"
            },
            "include_option": True,
        },
    ]

    payload = []

    for command in commands:
        payload_item = {
            "type": 1,
            "name": command["name"],
            "description": command["description"],
            "description_localizations": command["description_localizations"],
        }
        if "name_localizations" in command:
            payload_item["name_localizations"] = command["name_localizations"]
        if command.get("include_option"):
            option_payload = dict(server_option)
            option_payload["choices"] = list(server_option["choices"])
            payload_item["options"] = [option_payload]
        payload.append(payload_item)

    return payload


def _overwrite_guild_commands(
    session: requests.Session, app_id: str, bot_token: str, guild_id: str, commands: List[Dict[str, object]]
) -> None:
    url = f"{BASE_URL}/applications/{app_id}/guilds/{guild_id}/commands"
    response = session.put(
        url,
        headers={
            "Authorization": f"Bot {bot_token}",
            "Content-Type": "application/json",
        },
        data=json.dumps(commands),
        timeout=15,
    )

    if response.status_code >= 400:
        raise RuntimeError(
            f"Discord API error ({response.status_code}): {response.text}"
        )

    print(f"Updated commands for guild {guild_id}")


def main() -> None:
    _load_env_file()
    app_id = _require_env("DISCORD_APP_ID")
    bot_token = _require_env("DISCORD_APP_BOT_TOKEN")
    servers = _load_servers()

    guilds: Dict[str, List[Dict[str, str]]] = {}
    for server in servers:
        guilds.setdefault(server["discordGuildId"], []).append(server)

    if not guilds:
        print("No servers found in servers.json", file=sys.stderr)
        sys.exit(1)

    session = requests.Session()
    for guild_id, guild_servers in guilds.items():
        commands = _build_command_payload(guild_servers)
        _overwrite_guild_commands(session, app_id, bot_token, guild_id, commands)
        print(f"Done guild {guild_id}\n")


if __name__ == "__main__":
    main()
