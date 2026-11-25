from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "ip6-localhost",
    "ip6-loopback",
}

BLOCKED_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
    ".arpa",
)


class UnsafeURLError(ValueError):
    """Raised when a URL fails scheme or SSRF safety checks."""


def _is_public_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str.split("%", 1)[0])
    except ValueError:
        return False

    return (
        ip.is_global
        and not ip.is_private
        and not ip.is_loopback
        and not ip.is_link_local
        and not ip.is_multicast
        and not ip.is_reserved
        and not ip.is_unspecified
    )


def validate_url(url: str, resolve_dns: bool = True) -> str:
    """Validate that a URL is http/https and does not point to a private/internal host."""
    cleaned = (url or "").strip()
    if not cleaned:
        raise UnsafeURLError("Empty URL")

    parts = urlsplit(cleaned)
    scheme = (parts.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise UnsafeURLError("Only http and https URLs are allowed")

    hostname = (parts.hostname or "").strip().lower().rstrip(".")
    if not hostname:
        raise UnsafeURLError("URL is missing a hostname")

    if hostname in BLOCKED_HOSTNAMES or any(
        hostname.endswith(suffix) for suffix in BLOCKED_SUFFIXES
    ):
        raise UnsafeURLError("Blocked local or internal hostname")

    # If hostname is an IP literal, validate it directly.
    try:
        ipaddress.ip_address(hostname.split("%", 1)[0])
        is_literal_ip = True
    except ValueError:
        is_literal_ip = False

    if is_literal_ip:
        if not _is_public_ip(hostname):
            raise UnsafeURLError("Blocked private or non-public IP address")
        return cleaned

    if resolve_dns:
        port = parts.port or (443 if scheme == "https" else 80)
        try:
            addr_info = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise UnsafeURLError(f"Could not resolve hostname: {hostname}") from exc

        resolved_ips = {info[4][0] for info in addr_info if info[4]}
        if not resolved_ips:
            raise UnsafeURLError(f"No IP addresses resolved for {hostname}")

        for ip_addr in resolved_ips:
            if not _is_public_ip(ip_addr):
                raise UnsafeURLError("Blocked private or internal IP address")

    return cleaned
