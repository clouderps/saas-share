# -*- coding: utf-8 -*-
"""Outbound endpoint policy for the direct provider path.

Cloud providers are reachable only on fixed, hard-coded hostnames — there
is no free-form endpoint field for them. The single configurable URL
(``ai.provider.config.local_llm_endpoint``) is accepted only when an admin
turned on ``ab_ai_base.allow_local_llm`` AND every address the host
resolves to is loopback / private (RFC1918, ULA). Link-local (cloud
metadata 169.254.169.254) and public addresses are refused.

Residual risk: DNS can change between this check and the request
(rebinding). Use an IP literal or ``localhost`` for the local endpoint.
"""

import ipaddress
import socket
from urllib.parse import urlsplit

PROVIDER_HOSTS = frozenset({
    'api.openai.com',
    'api.anthropic.com',
    'generativelanguage.googleapis.com',
})


class EndpointNotAllowed(ValueError):
    """Raised when an outbound AI URL violates the policy."""


def check_cloud_url(url):
    parts = urlsplit(url or '')
    if parts.scheme != 'https' or (parts.hostname or '').lower() not in PROVIDER_HOSTS:
        raise EndpointNotAllowed('host not in provider allow-list')
    return url


def _addr_ok(addr):
    ip = ipaddress.ip_address(addr.split('%', 1)[0])
    if ip.is_link_local or ip.is_multicast or ip.is_unspecified:
        return False
    return ip.is_loopback or ip.is_private


def check_local_url(url, resolver=socket.getaddrinfo):
    parts = urlsplit(url or '')
    host = parts.hostname
    if parts.scheme not in ('http', 'https') or not host:
        raise EndpointNotAllowed('invalid local endpoint')
    try:
        infos = resolver(host, parts.port or (443 if parts.scheme == 'https' else 80))
    except (socket.gaierror, UnicodeError) as exc:
        raise EndpointNotAllowed('local endpoint does not resolve') from exc
    addrs = {info[4][0] for info in infos}
    if not addrs or not all(_addr_ok(a) for a in addrs):
        raise EndpointNotAllowed('local endpoint must be loopback or private')
    return url
