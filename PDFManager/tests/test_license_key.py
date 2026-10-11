import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from pdfmanager.licensing.license_key import (
    LicenseKeyError,
    generate_license_key,
    verify_license_key,
)


@pytest.fixture
def real_private_key(test_signing_key) -> Ed25519PrivateKey:
    return test_signing_key


@pytest.mark.parametrize("months", [3, 6, 12, 24])
def test_generated_key_verifies_with_correct_duration(real_private_key, months):
    key = generate_license_key(real_private_key, months)
    result = verify_license_key(key)
    assert result.months == months


def test_two_keys_for_same_duration_are_different(real_private_key):
    key_a = generate_license_key(real_private_key, 6)
    key_b = generate_license_key(real_private_key, 6)
    assert key_a != key_b  # losowy nonce -> różne klucze, nawet dla tego samego okresu


def test_generate_rejects_unsupported_duration(real_private_key):
    with pytest.raises(ValueError):
        generate_license_key(real_private_key, 7)


def test_verify_rejects_garbage_string():
    with pytest.raises(LicenseKeyError):
        verify_license_key("to-nie-jest-prawidlowy-klucz")


def test_verify_rejects_tampered_key(real_private_key):
    key = generate_license_key(real_private_key, 12)
    # Zmieniamy jeden znak w środku (nie separator) — podpis powinien przestać się zgadzać.
    chars = list(key)
    for i, ch in enumerate(chars):
        if ch != "-":
            chars[i] = "A" if ch != "A" else "B"
            break
    tampered = "".join(chars)
    with pytest.raises(LicenseKeyError):
        verify_license_key(tampered)


def test_verify_accepts_lowercase_and_extra_whitespace(real_private_key):
    key = generate_license_key(real_private_key, 3)
    messy = "  " + key.lower() + "  "
    result = verify_license_key(messy)
    assert result.months == 3


def test_verify_rejects_key_signed_with_wrong_key():
    other_key = Ed25519PrivateKey.generate()
    forged = generate_license_key(other_key, 24)
    with pytest.raises(LicenseKeyError):
        verify_license_key(forged)
