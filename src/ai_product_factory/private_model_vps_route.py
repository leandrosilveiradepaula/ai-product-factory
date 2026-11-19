"""VPS-local, read-only verification of an existing WireGuard route.

Factory -> native Python VPS worker -> wg-ibm -> private IBM Cloud API.
This module never invokes a model, reads secrets, creates tunnels or changes
routing tables. A wrong/default route blocks requests before reading bearer.
"""
from __future__ import annotations

import ipaddress
import json
import re
import socket
import subprocess
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit


class PrivateVpsRouteError(RuntimeError):
    """Sanitized failure. No destination, host or credential details."""


RouteReader = Callable[[str], Any]
TcpDialer = Callable[[str, int], None]
_INTERFACE = re.compile(r"wg-[a-z0-9][a-z0-9-]{0,13}\Z")


def private_target(base_url: str) -> tuple[str, int]:
    try:
        parts = urlsplit(base_url)
        address = ipaddress.ip_address(parts.hostname or "")
        port = parts.port or (80 if parts.scheme == "http" else 443)
    except (ValueError, TypeError):
        raise PrivateVpsRouteError("private model endpoint invalid") from None
    if (parts.scheme not in ("http", "https") or address.version != 4
            or not address.is_private or address.is_loopback or
            address.is_link_local or address.is_reserved or
            address.is_multicast or address.is_unspecified or not 1 <= port <= 65535):
        raise PrivateVpsRouteError("private model endpoint not authorized")
    return str(address), port


def _route(ip: str):
    try:
        result = subprocess.run(["ip", "-json", "route", "get", ip],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                timeout=5, check=False, text=True)
        if result.returncode != 0:
            raise ValueError
        return json.loads(result.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise PrivateVpsRouteError("private WireGuard route unavailable") from None


def _tcp(ip: str, port: int) -> None:
    try:
        with socket.create_connection((ip, port), timeout=5):
            pass
    except (OSError, TimeoutError):
        raise PrivateVpsRouteError("private model TCP unavailable") from None


def verify_existing_vps_route(
    base_url: str, *,
    interface: str = "wg-ibm",
    tcp: bool = False,
    route_reader: RouteReader | None = None,
    tcp_dialer: TcpDialer | None = None,
) -> dict[str, str | bool]:
    """Fail closed if the host does not route via the approved EXISTING VPN.

    tcp=True performs a TCP handshake only, without HTTP, prompts or tokens.
    Successful TCP does not prove the model's API/auth/cost availability.
    """
    if not isinstance(interface, str) or not _INTERFACE.fullmatch(interface):
        raise PrivateVpsRouteError("private WireGuard interface invalid")
    ip, port = private_target(base_url)
    routes = (route_reader or _route)(ip)
    if (not isinstance(routes, list) or len(routes) != 1 or
            not isinstance(routes[0], dict) or routes[0].get("dev") != interface):
        raise PrivateVpsRouteError("private route is not the authorized WireGuard interface")
    if tcp:
        (tcp_dialer or _tcp)(ip, port)
    return {
        "schema": "factory-vps-private-route-v1",
        "status": "network_route_verified_only" if tcp else "route_verified_only",
        "interface": interface,
        "model_invoked": False,
        "api_key_read": False,
        "sql_executed": False,
    }
