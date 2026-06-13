from __future__ import annotations

import argparse
import os
import shlex
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa


def generate_keypair(kind: str = "ed25519", bits: int = 3072):
    if kind == "ed25519":
        private_key = ed25519.Ed25519PrivateKey.generate()
    elif kind == "rsa":
        if bits < 2048:
            raise ValueError("RSA keys must be at least 2048 bits")
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=bits)
    else:
        raise ValueError(f"unsupported key kind: {kind}")
    return private_key, private_key.public_key()


def private_key_bytes(private_key, passphrase: str | None = None) -> bytes:
    encryption = (
        serialization.BestAvailableEncryption(passphrase.encode("utf-8"))
        if passphrase
        else serialization.NoEncryption()
    )
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=encryption,
    )


def public_key_bytes(public_key, comment: str | None = None) -> bytes:
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    )
    if comment:
        raw += b" " + comment.encode("utf-8")
    return raw


def save_keypair(
    output_dir: Path,
    name: str,
    kind: str,
    passphrase: str | None = None,
    bits: int = 3072,
    comment: str = "remote-ssh-desktop",
) -> tuple[Path, Path]:
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    private_key, public_key = generate_keypair(kind=kind, bits=bits)
    private_path = output_dir / name
    public_path = output_dir / f"{name}.pub"
    if private_path.exists() or public_path.exists():
        raise FileExistsError(f"key already exists: {private_path} or {public_path}")
    private_path.write_bytes(private_key_bytes(private_key, passphrase=passphrase))
    os.chmod(private_path, 0o600)
    public_path.write_bytes(public_key_bytes(public_key, comment=comment) + b"\n")
    os.chmod(public_path, 0o644)
    return private_path, public_path


def authorized_keys_line(public_key_path: Path) -> str:
    return public_key_path.expanduser().read_text(encoding="utf-8").strip()


def authorized_keys_helper(public_key_path: Path) -> str:
    key = authorized_keys_line(public_key_path)
    return "mkdir -p ~/.ssh && chmod 700 ~/.ssh && " + f"printf '%s\\n' {shlex.quote(key)} >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate SSH key pairs for Remote SSH Desktop")
    parser.add_argument("--kind", choices=["ed25519", "rsa"], default="ed25519")
    parser.add_argument("--bits", type=int, default=3072)
    parser.add_argument("--output-dir", default=str(Path.home() / ".ssh"))
    parser.add_argument("--name", default="id_remote_ssh_desktop")
    parser.add_argument("--passphrase", default="")
    parser.add_argument("--comment", default="remote-ssh-desktop")
    args = parser.parse_args()

    private_path, public_path = save_keypair(
        Path(args.output_dir),
        args.name,
        args.kind,
        passphrase=args.passphrase or None,
        bits=args.bits,
        comment=args.comment,
    )
    print(f"private_key={private_path}")
    print(f"public_key={public_path}")
    print(authorized_keys_helper(public_path))


if __name__ == "__main__":
    main()
