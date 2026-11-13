"""normalize_origin / is_in_scope: IPv4, IPv6 (brackets kept), ports, invalid input, exact matching."""
import pytest

from core.scope import is_in_scope, normalize_origin


# ---- IPv4 / domains --------------------------------------------------------------------
def test_ipv4_without_and_with_port():
    assert normalize_origin("https://192.0.2.10") == "https://192.0.2.10"
    assert normalize_origin("http://192.0.2.10:8080") == "http://192.0.2.10:8080"


def test_domain_with_port_and_case_and_idna():
    assert normalize_origin("https://Example.COM:8443") == "https://example.com:8443"
    assert normalize_origin("example.com") == "https://example.com"
    assert normalize_origin("https://bücher.example") == "https://xn--bcher-kva.example"


# ---- IPv6 ------------------------------------------------------------------------------
def test_ipv6_without_port_keeps_brackets():
    assert normalize_origin("https://[::1]") == "https://[::1]"
    assert normalize_origin("https://[::1]/") == "https://[::1]"
    assert normalize_origin("[2001:db8::1]") == "https://[2001:db8::1]"


def test_ipv6_with_port_keeps_brackets_and_port():
    assert normalize_origin("https://[::1]:8443") == "https://[::1]:8443"
    assert normalize_origin("http://[2001:db8::1]:8080") == "http://[2001:db8::1]:8080"


def test_ipv6_default_port_is_dropped():
    assert normalize_origin("https://[::1]:443") == "https://[::1]"
    assert normalize_origin("http://[::1]:80") == "http://[::1]"
    # a non-default port for the other scheme is kept
    assert normalize_origin("http://[::1]:443") == "http://[::1]:443"


def test_ipv6_is_canonicalised_so_equivalent_spellings_match():
    a = normalize_origin("https://[2001:0DB8:0000:0000:0000:0000:0000:0001]")
    assert a == "https://[2001:db8::1]"
    assert is_in_scope("https://[2001:db8::1]:443", ["https://[2001:DB8:0:0:0:0:0:1]"])


@pytest.mark.parametrize("bad", [
    "https://[::1",            # unbalanced bracket
    "https://::1",             # un-bracketed IPv6 is not a valid origin
    "https://[gggg::1]",       # not hex
    "https://[1:2:3:4:5:6:7:8:9]",  # too many groups
    "https://[::1%25eth0]",    # zone id
    "https://[]",
    "https://[::1]x",
])
def test_invalid_ipv6_rejected(bad):
    with pytest.raises(ValueError):
        normalize_origin(bad)


def test_ipv6_invalid_port_rejected():
    for bad in ("https://[::1]:99999", "https://[::1]:abc", "https://[::1]:-1"):
        with pytest.raises(ValueError):
            normalize_origin(bad)


# ---- ports -----------------------------------------------------------------------------
@pytest.mark.parametrize("bad", ["https://example.com:99999", "https://example.com:abc",
                                 "https://example.com:-5", "https://example.com:65536"])
def test_invalid_port_rejected(bad):
    with pytest.raises(ValueError):
        normalize_origin(bad)


def test_default_ports_dropped_for_domains():
    assert normalize_origin("https://example.com:443") == "https://example.com"
    assert normalize_origin("http://example.com:80") == "http://example.com"
    assert normalize_origin("http://example.com:443") == "http://example.com:443"


# ---- path / query / fragment / credentials / scheme ------------------------------------
@pytest.mark.parametrize("bad", [
    "https://example.com/admin", "https://example.com/?a=1", "https://example.com?a=1",
    "https://example.com#frag", "https://[::1]/admin", "https://[::1]?x=1", "https://[::1]#f",
    "https://192.0.2.10/a",
])
def test_path_query_fragment_rejected(bad):
    with pytest.raises(ValueError):
        normalize_origin(bad)


@pytest.mark.parametrize("bad", ["ftp://example.com", "https://u:p@example.com", "https://u@[::1]", "", "   ",
                                 "https://"])
def test_other_invalid_inputs_rejected(bad):
    with pytest.raises(ValueError):
        normalize_origin(bad)


# ---- exact matching / no scope widening ------------------------------------------------
def test_exact_origin_match_only():
    allowed = ["https://example.com"]
    assert is_in_scope("https://example.com:443", allowed)
    assert not is_in_scope("http://example.com", allowed)          # other scheme
    assert not is_in_scope("https://example.com:8443", allowed)    # other port
    assert not is_in_scope("https://sub.example.com", allowed)     # subdomain
    assert not is_in_scope("https://example.com.evil.test", allowed)
    assert not is_in_scope("https://evilexample.com", allowed)


def test_ipv6_scope_does_not_widen():
    allowed = ["https://[2001:db8::1]"]
    assert is_in_scope("https://[2001:db8::1]", allowed)
    assert not is_in_scope("https://[2001:db8::2]", allowed)
    assert not is_in_scope("https://[2001:db8::1]:8443", allowed)
    assert not is_in_scope("http://[2001:db8::1]", allowed)
    assert not is_in_scope("https://[::1]", allowed)
    assert not is_in_scope("https://2001:db8::1", allowed)          # malformed -> out of scope


def test_loopback_and_private_are_not_implicitly_in_scope():
    allowed = ["https://example.com"]
    for u in ("https://[::1]", "https://127.0.0.1", "https://localhost", "https://10.0.0.1"):
        assert not is_in_scope(u, allowed)


def test_invalid_input_or_invalid_allowed_entry_is_out_of_scope():
    assert not is_in_scope("not a url ::", ["https://example.com"])
    assert not is_in_scope("https://example.com", [])
    assert not is_in_scope("https://example.com", ["https://example.com/path"])  # bad entry never matches
