from remote_ssh_desktop.common.protocol import FRAME_CONTROL, decode_message, pack_frame, unpack_frame
from remote_ssh_desktop.common.files import join_remote_jail

raw = pack_frame(FRAME_CONTROL, {"t": "ping", "ts": 1})
frame = unpack_frame(raw)
assert decode_message(frame.payload)["t"] == "ping"
assert join_remote_jail("/tmp/shared", "../../etc/passwd") == "/tmp/shared/etc/passwd"
print("tests ok")
