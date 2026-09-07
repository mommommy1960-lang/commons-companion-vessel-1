from miguel.core import MiguelCore
import pytest

from miguel.continuity import snapshot_memory
from miguel.persistence import EnvelopeError, decode_snapshot, encode_snapshot

KEY = b"simulation-test-key"


def make_blob():
    core = MiguelCore()
    snapshot = snapshot_memory(core, key_id="k1", key_epoch=2)
    return encode_snapshot(snapshot, key=KEY, snapshot_id="s1", sequence=7)


def test_round_trip_is_one_authenticated_image():
    snapshot, meta = decode_snapshot(make_blob(), key=KEY)
    assert meta == {"snapshot_id": "s1", "sequence": 7}
    assert snapshot["key_epoch"] == 2


@pytest.mark.parametrize("cut", [0, 1, 4, 11, 12, -33, -1])
def test_truncation_fails_closed(cut):
    blob = make_blob()
    damaged = blob[:cut] if cut >= 0 else blob[:cut]
    with pytest.raises(EnvelopeError):
        decode_snapshot(damaged, key=KEY)


def test_trailing_bytes_fail_closed():
    with pytest.raises(EnvelopeError):
        decode_snapshot(make_blob() + b"valid-looking-tail", key=KEY)


def test_wrong_key_fails_closed():
    with pytest.raises(EnvelopeError):
        decode_snapshot(make_blob(), key=b"wrong-key")


def test_body_substitution_fails_authentication():
    blob = bytearray(make_blob())
    blob[20] ^= 1
    with pytest.raises(EnvelopeError):
        decode_snapshot(bytes(blob), key=KEY)
