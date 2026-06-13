from __future__ import annotations

import argparse
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa


def generate_keypair(kind: str = "ed25519", bits: int = 3072):
    if kind == "ed25519":
        private_key = ed25519.Ed25519PrivateKey.generate()
    elif kind == "rsa":
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


def public_key_bytes(public_key) -> bytes:
    return public_key.public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    )


def save_keypair(
    output_dir: Path,
    name: str,
    kind: str,
    passphrase: str | None = None,
    bits: int = 3072,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    private_key, public_key = generate_keypair(kind=kind, bits=bits)
    private_path = output_dir / name
    public_path = output_dir / f"{name}.pub"
    private_path.write_bytes(private_key_bytes(private_key, passphrase=passphrase))
    os.chmod(private_path, 0o600)
    public_path.write_bytes(public_key_bytes(public_key) + b"\n")
    return private_path, public_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate SSH key pairs for the remote desktop app")
    parser.add_argument("--kind", choices=["ed25519", "rsa"], default="ed25519")
    parser.add_argument("--bits", type=int, default=3072)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--name", default="id_remote_ssh_desktop")
    parser.add_argument("--passphrase", default="")
    args = parser.parse_args()

    private_path, public_path = save_keypair(
        Path(args.output_dir),
        args.name,
        args.kind,
        passphrase=args.passphrase or None,
        bits=args.bits,
    )
    print(private_path)
    print(public_path)
    print(f"cat {public_path} >> ~/.ssh/authorized_keys")


if __name__ == "__main__":
    main()
