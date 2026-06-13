from remote_ssh_desktop.common.protocol import FRAME_CONTROL, FLAG_JSON, decode_message, pack_frame, unpack_frame
from remote_ssh_desktop.common.files import join_remote_jail, normalize_remote_rel


def test_json_frame_roundtrip():
    raw = pack_frame(FRAME_CONTROL, {"t": "ping", "ts": 1})
    frame = unpack_frame(raw)
    assert frame.kind == FRAME_CONTROL
    assert frame.flags & FLAG_JSON
    assert decode_message(frame.payload) == {"t": "ping", "ts": 1}


def test_remote_jail_normalization():
    assert normalize_remote_rel("../../etc/passwd") == "etc/passwd"
    assert join_remote_jail("/home/alice/Shared", "../report.pdf") == "/home/alice/Shared/report.pdf"
