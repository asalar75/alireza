import pytest
from core.scope import normalize_origin, is_in_scope

def test_normalize_origin():
    assert normalize_origin("https://Example.COM/") == "https://example.com"

def test_reject_path():
    with pytest.raises(ValueError):
        normalize_origin("https://example.com/admin")

def test_exact_origin_scope():
    assert is_in_scope("https://example.com", ["https://example.com"])
    assert not is_in_scope("https://sub.example.com", ["https://example.com"])

def test_reject_credentials():
    with pytest.raises(ValueError):
        normalize_origin("https://user:pass@example.com")

def test_reject_bad_port():
    with pytest.raises(ValueError):
        normalize_origin("https://example.com:99999")
