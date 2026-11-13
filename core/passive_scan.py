from typing import Callable, Optional
from urllib.parse import urlparse
from .scope import normalize_origin, is_in_scope
from .operations import CancelToken

USER_AGENT = "AegisSec-Enterprise/0.3 authorized-assessment"
TIMEOUT_S = 12.0


class Response:
    """Minimal response shape the checks need (decouples checks from the HTTP library)."""
    def __init__(self, status_code: int, headers: dict, is_redirect: bool):
        self.status_code, self.headers, self.is_redirect = status_code, headers, is_redirect


def httpx_fetch(origin: str) -> Response:
    """One ordinary GET: TLS verified, redirects NOT followed, finite timeout."""
    import httpx  # imported lazily so core logic is testable without the dependency
    with httpx.Client(timeout=TIMEOUT_S, follow_redirects=False, verify=True,
                      headers={"User-Agent": USER_AGENT}) as client:
        r = client.get(origin)
    return Response(r.status_code, {k.lower(): v for k, v in r.headers.items()}, r.is_redirect)

CHECKS = [
 ("strict-transport-security", "HSTS header not observed", "Low"),
 ("content-security-policy", "Content-Security-Policy header not observed", "Low"),
 ("x-content-type-options", "X-Content-Type-Options header not observed", "Low"),
 ("referrer-policy", "Referrer-Policy header not observed", "Info"),
 ("permissions-policy", "Permissions-Policy header not observed", "Info"),
]

def run_passive_check(target: str, allowed_origins: list[str], *,
                      fetch: Optional[Callable[[str], Response]] = None,
                      cancel: Optional[CancelToken] = None) -> list[dict]:
    origin = normalize_origin(target)
    if not is_in_scope(origin, allowed_origins):
        raise PermissionError("Target origin is not in the approved scope")
    if urlparse(origin).scheme != "https":
        raise ValueError("Passive checks require HTTPS")
    if cancel:
        cancel.raise_if_cancelled()
    response = (fetch or httpx_fetch)(origin)
    if cancel:
        cancel.raise_if_cancelled()
    headers = {k.lower(): v for k, v in response.headers.items()}
    out = []
    for key, title, severity in CHECKS:
        if key not in headers:
            out.append(dict(title=title, severity=severity, confidence="Low",
                url=origin, status="Needs review",
                evidence=f"HTTP {response.status_code}; response header '{key}' was absent.",
                remediation=f"Review the application architecture and configure {key} where appropriate.",
                reference="OWASP Secure Headers Project"))
    if "server" in headers:
        out.append(dict(title="Server response header disclosed", severity="Info",
            confidence="High", url=origin, status="Needs review",
            evidence=f"Server response header: {headers['server']}",
            remediation="Consider reducing unnecessary product/version disclosure.",
            reference="Information disclosure review"))
    if response.is_redirect:
        out.append(dict(title="Redirect observed; destination not followed", severity="Info",
            confidence="High", url=origin, status="Needs review",
            evidence=f"HTTP {response.status_code}; Location={headers.get('location','(none)')}",
            remediation="Confirm the destination is separately authorized before assessing it.",
            reference="Scope control"))
    return out
