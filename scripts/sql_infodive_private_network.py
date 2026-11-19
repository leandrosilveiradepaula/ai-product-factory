"""No-LLM, no-token private route verification for SQL-InfoDive.

Only a manual workflow on exact Factory/main may call the CLI. An approved
WireGuard peer must already be provisioned by a private network administrator.
"""
from __future__ import annotations
import argparse
import base64
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import subprocess
from urllib.parse import urlsplit
from ai_product_factory.private_chat_provider import PrivateChatConfig, PrivateModelError

REPO = "leandrosilveiradepaula/ai-product-factory"
IFACE = "factory-ibm"
SHA = re.compile(r"[0-9a-f]{40}\Z")
ENDPOINT_HOST = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?\Z")

def config(env):
    if env.get("FACTORY_SQL_INFODIVE_ENABLED") != "true":
        raise PrivateModelError("private route preflight disabled")
    return PrivateChatConfig(
        base_url=env.get("FACTORY_SQL_INFODIVE_BASE_URL", ""),
        model_id=env.get("FACTORY_SQL_INFODIVE_MODEL", ""),
        host_header=env.get("FACTORY_SQL_INFODIVE_HTTP_HOST") or None,
        allow_private_http=env.get("FACTORY_SQL_INFODIVE_ALLOW_PRIVATE_HTTP") == "true",
    )

def target(env):
    url = urlsplit(config(env).base_url)
    address = ipaddress.ip_address(url.hostname or "")
    if address.version != 4:
        raise PrivateModelError("private network target invalid")
    return str(address), url.port or (80 if url.scheme == "http" else 443)

def key(value):
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, TypeError):
        raise PrivateModelError("WireGuard key invalid") from None
    if len(decoded) != 32 or len(value) != 44:
        raise PrivateModelError("WireGuard key invalid")
    return value

def endpoint(value):
    if not isinstance(value, str) or not value or any(ch.isspace() for ch in value):
        raise PrivateModelError("WireGuard endpoint invalid")
    try:
        url = urlsplit("//" + value)
        hostname, port = url.hostname, url.port
    except (TypeError, ValueError):
        raise PrivateModelError("WireGuard endpoint invalid") from None
    if (not hostname or not port or not ENDPOINT_HOST.fullmatch(hostname)
            or ".." in hostname or url.path or url.query or url.fragment
            or url.username or url.password):
        raise PrivateModelError("WireGuard endpoint invalid")
    return value

def prepare(env, path: Path):
    dest, _ = target(env)
    private_key = key(env.get("FACTORY_INFODIVE_WG_CLIENT_PRIVATE_KEY"))
    peer_key = key(env.get("FACTORY_INFODIVE_WG_PEER_PUBLIC_KEY"))
    peer_endpoint = endpoint(env.get("FACTORY_INFODIVE_WG_ENDPOINT"))
    try:
        address = ipaddress.ip_interface(env.get("FACTORY_INFODIVE_WG_CLIENT_ADDRESS", ""))
    except ValueError:
        raise PrivateModelError("WireGuard client address invalid") from None
    if (address.version != 4 or not address.ip.is_private or
            address.ip.is_loopback or address.ip.is_link_local or
            address.ip.is_reserved or address.network.prefixlen < 24):
        raise PrivateModelError("WireGuard client address invalid")
    if path.name != IFACE + ".conf":
        raise PrivateModelError("WireGuard file name invalid")
    contents = (
        f"[Interface]\nPrivateKey = {private_key}\nAddress = {address}\n"
        f"[Peer]\nPublicKey = {peer_key}\nAllowedIPs = {dest}/32\n"
        f"Endpoint = {peer_endpoint}\nPersistentKeepalive = 25\n"
    )
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(contents)
    except Exception:
        path.unlink(missing_ok=True)
        raise

def route_of(ip):
    try:
        run = subprocess.run(["ip", "-json", "route", "get", ip],
                             capture_output=True, text=True, timeout=8, check=False)
        if run.returncode != 0:
            raise ValueError
        return json.loads(run.stdout)
    except (ValueError, OSError, subprocess.TimeoutExpired):
        raise PrivateModelError("private route cannot be confirmed") from None

def dial(ip, port):
    try:
        with socket.create_connection((ip, port), timeout=5):
            pass
    except (OSError, TimeoutError):
        raise PrivateModelError("private API TCP route cannot be confirmed") from None

def probe(env, *, route_reader=None, connector=None):
    ip, port = target(env)
    sha = env.get("GITHUB_SHA", "")
    if not SHA.fullmatch(sha):
        raise PrivateModelError("exact-SHA preflight unavailable")
    data = (route_reader or route_of)(ip)
    if (not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict)
            or data[0].get("dev") != IFACE):
        raise PrivateModelError("network path bypasses isolated WireGuard interface")
    (connector or dial)(ip, port)
    return {
        "schema": "factory-private-llm-network-v1",
        "provider": "infodive_ibm_cloud",
        "status": "network_route_verified_only",
        "head_sha": sha,
        "interface": IFACE,
        "model_invoked": False,
        "api_key_read": False,
        "sql_executed": False,
        "credential_verified": False,
        "pricing_verified": False,
    }

def require_manual_main(env):
    if (env.get("GITHUB_REPOSITORY") != REPO or
            env.get("GITHUB_REF") != "refs/heads/main" or
            env.get("GITHUB_EVENT_NAME") != "workflow_dispatch"):
        raise PrivateModelError("manual main-only authorization required")

def main(argv=None):
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prepare")
    modes.add_argument("--probe")
    args = parser.parse_args(argv)
    try:
        env = os.environ
        require_manual_main(env)
        if args.prepare:
            prepare(env, Path(args.prepare))
            print("WIREGUARD_CONFIG_PREPARED")
        else:
            receipt = probe(env)
            fd = os.open(Path(args.probe), os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                json.dump(receipt, out, sort_keys=True)
            print("PRIVATE_NETWORK_VERIFIED_ONLY")
        return 0
    except (PrivateModelError, OSError):
        print("PRIVATE_NETWORK_PREFLIGHT_BLOCKED")
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
