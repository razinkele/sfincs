"""Client IP for audit rows: trust X-Forwarded-For only from configured proxies."""

from __future__ import annotations

import ipaddress


def get_client_ip(scope: dict, trusted_proxies: list[str]) -> str:
    """Rightmost-untrusted walk of X-Forwarded-For.

    nginx on this host appends the real client to X-Forwarded-For and connects
    from 127.0.0.1. Walking from the right, skip every address inside a
    trusted network and return the first one that is not; if all are trusted,
    return the leftmost. An untrusted peer's header is attacker-controlled and
    is ignored in favour of the socket peer.
    """
    client = scope.get("client")
    peer = client[0] if client else "unknown"
    if not trusted_proxies:
        return peer
    try:
        networks = [ipaddress.ip_network(c, strict=False) for c in trusted_proxies]
        peer_ip = ipaddress.ip_address(peer)
    except ValueError:
        return peer
    if not any(peer_ip in n for n in networks):
        return peer
    forwarded = b""
    for name, value in scope.get("headers", []):
        if name == b"x-forwarded-for":
            forwarded = value
            break
    hops = [h.strip() for h in forwarded.decode("latin-1").split(",") if h.strip()]
    if not hops:
        return peer
    for hop in reversed(hops):
        try:
            if not any(ipaddress.ip_address(hop) in n for n in networks):
                return hop
        except ValueError:
            return hop
    return hops[0]
