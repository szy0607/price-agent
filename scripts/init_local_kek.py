"""Initialize a local development KEK without printing it."""

import base64
import json
import os
import re
import secrets
from pathlib import Path


def initialize(env_path: Path) -> bool:
    content = env_path.read_text(encoding="utf-8")
    has_ring = bool(re.search(r"^API_KEY_KEKS\s*=", content, re.MULTILINE))
    has_active = bool(re.search(r"^API_KEY_ACTIVE_KEK_VERSION\s*=", content, re.MULTILINE))
    if has_ring and has_active:
        return False
    if has_ring or has_active:
        raise RuntimeError("Incomplete API Key KEK configuration; resolve it manually")

    value = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
    ring = json.dumps({"v1": value}, separators=(",", ":"))
    with env_path.open("a", encoding="utf-8", newline="\n") as target:
        if content and not content.endswith(("\n", "\r")):
            target.write("\n")
        target.write(f"API_KEY_KEKS='{ring}'\nAPI_KEY_ACTIVE_KEK_VERSION=v1\n")
        target.flush()
        os.fsync(target.fileno())
    return True


if __name__ == "__main__":
    changed = initialize(Path(__file__).resolve().parents[1] / ".env")
    print("Local KEK initialized; restart the backend" if changed else "Local KEK already configured")
