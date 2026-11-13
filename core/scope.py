import ipaddress
from urllib.parse import urlparse

def normalize_origin(value: str) -> str:
    value = value.strip()
    try:
        parsed = urlparse(value if "://" in value else "https://" + value)
    except ValueError as exc:  # e.g. unbalanced IPv6 brackets
        raise ValueError("Enter a valid http:// or https:// URL") from exc
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Enter a valid http:// or https:// URL")
    if parsed.username or parsed.password:
        raise ValueError("Do not embed credentials in target URLs")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("Enter an origin only: scheme, host and optional port")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Invalid port") from exc
    raw_host = parsed.hostname  # urlparse strips the [] around IPv6 literals
    if ":" in raw_host:
        # Only an IPv6 literal may contain ':'. Zone ids (%eth0) are rejected.
        if "%" in raw_host:
            raise ValueError("IPv6 zone identifiers are not allowed in an origin")
        try:
            addr = ipaddress.IPv6Address(raw_host)
        except ValueError as exc:
            raise ValueError("Invalid IPv6 address") from exc
        host = f"[{addr.compressed}]"  # keep the brackets: required in an origin
    else:
        host = raw_host.encode("idna").decode("ascii").lower()
    default = (parsed.scheme == "https" and port == 443) or (parsed.scheme == "http" and port == 80)
    return f"{parsed.scheme}://{host}" + (f":{port}" if port and not default else "")

def is_in_scope(url: str, allowed_origins: list[str]) -> bool:
    try:
        candidate = normalize_origin(url)
        allowed = {normalize_origin(x) for x in allowed_origins}
    except ValueError:
        return False
    return candidate in allowed
