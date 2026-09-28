import base64
import json
import secrets
import unittest
from types import SimpleNamespace

from app.core.api_key_crypto import (
    EncryptedBlob,
    KeyConfigurationError,
    KeyDecryptionError,
    KeyRing,
    decrypt_api_key,
    encrypt_api_key,
    new_dek,
    unwrap_dek,
    wrap_dek,
)


def ring() -> KeyRing:
    return KeyRing({"v1": base64.b64encode(secrets.token_bytes(32)).decode()}, "v1")


class ApiKeyCryptoTests(unittest.TestCase):
    def test_encryption_round_trip_and_fresh_nonces(self):
        keys = ring()
        dek = new_dek()
        first = encrypt_api_key(dek, b"sk-example-secret", 7, "OpenAI", 1)
        second = encrypt_api_key(dek, b"sk-example-secret", 7, "openai", 1)
        wrapped = wrap_dek(keys, dek, 7, 1)
        self.assertNotEqual(first.nonce, second.nonce)
        self.assertNotEqual(first.ciphertext, second.ciphertext)
        self.assertEqual(len(base64.b64decode(first.nonce)), 12)
        self.assertEqual(len(base64.b64decode(first.tag)), 16)
        self.assertEqual(unwrap_dek(keys, wrapped, 7, 1, "v1", 1), dek)
        self.assertEqual(decrypt_api_key(dek, first, 7, "openai", 1, 1), b"sk-example-secret")
        self.assertNotIn("sk-example-secret", repr(first))

    def test_wrong_ownership_version_and_tampering_are_rejected(self):
        keys = ring()
        dek = new_dek()
        wrapped = wrap_dek(keys, dek, 7, 1)
        encrypted = encrypt_api_key(dek, b"sk-example-secret", 7, "openai", 1)
        for user, provider, dek_version, format_version in (
            (8, "openai", 1, 1),
            (7, "anthropic", 1, 1),
            (7, "invalid provider!", 1, 1),
            (7, "openai", 2, 1),
            (7, "openai", 1, 2),
        ):
            with self.assertRaises(KeyDecryptionError):
                decrypt_api_key(dek, encrypted, user, provider, dek_version, format_version)
        for altered in (
            EncryptedBlob("AAAA", encrypted.nonce, encrypted.tag),
            EncryptedBlob(encrypted.ciphertext, base64.b64encode(secrets.token_bytes(12)).decode(), encrypted.tag),
            EncryptedBlob(encrypted.ciphertext, encrypted.nonce, base64.b64encode(secrets.token_bytes(16)).decode()),
        ):
            with self.assertRaises(KeyDecryptionError):
                decrypt_api_key(dek, altered, 7, "openai", 1, 1)
        for args in ((8, 1, "v1", 1), (7, 2, "v1", 1), (7, 1, "v1", 2)):
            with self.assertRaises(KeyDecryptionError):
                unwrap_dek(keys, wrapped, *args)

    def test_key_ring_configuration_does_not_echo_secret(self):
        secret = "bad-key-material"
        for encoded, active in (({}, "v1"), ({"v1": secret}, "v1"), ({"v1": "AAAA"}, "v2")):
            with self.assertRaises(KeyConfigurationError) as raised:
                KeyRing(encoded, active)
            self.assertNotIn(secret, str(raised.exception))
        valid = ring()
        with self.assertRaises(KeyConfigurationError):
            valid.key_for("unknown")

        class Secret:
            def get_secret_value(self):
                return '{"v1":"AAAA","v1":"BBBB"}'

        with self.assertRaises(KeyConfigurationError):
            KeyRing.from_settings(SimpleNamespace(api_key_keks=Secret(), api_key_active_kek_version="v1"))

    def test_rewrap_allows_retiring_the_old_kek(self):
        encoded = {
            "v1": base64.b64encode(secrets.token_bytes(32)).decode(),
            "v2": base64.b64encode(secrets.token_bytes(32)).decode(),
        }

        class Secret:
            def get_secret_value(self):
                return json.dumps(encoded)

        keys = KeyRing.from_settings(SimpleNamespace(api_key_keks=Secret(), api_key_active_kek_version="v2"))
        dek = new_dek()
        old = wrap_dek(keys, dek, 7, 1, "v1")
        replacement = wrap_dek(keys, unwrap_dek(keys, old, 7, 1, "v1", 1), 7, 1, "v2")
        new_only = KeyRing({"v2": encoded["v2"]}, "v2")
        self.assertEqual(unwrap_dek(new_only, replacement, 7, 1, "v2", 1), dek)
        with self.assertRaises(KeyConfigurationError):
            unwrap_dek(new_only, old, 7, 1, "v1", 1)


if __name__ == "__main__":
    unittest.main()
