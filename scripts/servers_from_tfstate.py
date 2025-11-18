import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

SCRIPTS_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPTS_DIR.parent
SERVERS_FILE = SCRIPTS_DIR / "servers.json"
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


def _run_terraform_show() -> Dict[str, Any]:
    cmd = ["terraform", "show", "-json", "-no-color"]
    state_path = os.getenv("TF_STATE_PATH")
    if state_path:
        cmd.append(state_path)

    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        print(exc.stderr or exc.stdout, file=sys.stderr)
        raise SystemExit(exc.returncode)

    return json.loads(result.stdout)


def _is_server_module(module: Dict[str, Any]) -> bool:
    for child in module.get("child_modules", []):
        for resource in child.get("resources", []):
            tags = resource.get("values", {}).get("tags") or {}
            if (
                resource.get("type") == "aws_spot_instance_request"
                and tags.get("GameServerEC2Discord:ServerId")
            ):
                return True
    return False


def _extract_tags(module: Dict[str, Any]) -> Dict[str, Any]:
    for child in module.get("child_modules", []):
        for resource in child.get("resources", []):
            if resource.get("type") != "aws_spot_instance_request":
                continue
            tags = resource.get("values", {}).get("tags")
            if tags and tags.get("GameServerEC2Discord:ServerId"):
                return tags
    raise RuntimeError(f"No spot instance request found in module {module.get('address')}")


def _build_config(modules: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    config = []
    for module in modules:
        tags = _extract_tags(module)
        config.append(
            {
                "region": tags["GameServerEC2Discord:Region"],
                "gameServerId": tags["GameServerEC2Discord:ServerId"],
                "discordGuildId": "<Discord Guild ID here>",
                "choiceDisplayName": tags["GameServerEC2Discord:ServerId"],
            }
        )
    return config


def main() -> None:
    _load_env_file()
    print("Retrieving terraform state")
    state = _run_terraform_show()
    child_modules = state.get("values", {}).get("root_module", {}).get("child_modules", [])

    print(f"Child modules found: {len(child_modules)}")
    server_modules = [module for module in child_modules if _is_server_module(module)]

    print("Server modules found:")
    for module in server_modules:
        print(f"- {module.get('address')}")

    server_config = _build_config(server_modules)
    SERVERS_FILE.write_text(json.dumps(server_config, indent=2), encoding="utf-8")
    print(f"{SERVERS_FILE} created")


if __name__ == "__main__":
    main()
