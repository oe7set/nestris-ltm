"""Minimal PostgreSQL login probe: which SQLSTATE does the server answer?

Why: during the login the server sends its error text in its own message
encoding (``lc_messages``). On a German Windows install that is WIN1252, and
asyncpg then drops the connection ("connection was closed in the middle of
operation") instead of raising ``InvalidPasswordError``. A wrong password
would look like "server not reachable".

This probe speaks just enough of the wire protocol (startup, trust,
cleartext, md5 and SCRAM-SHA-256, no TLS) to read the server's error
response bytewise and return its SQLSTATE. It is only used to explain an
ambiguous failure, never to connect for real.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import secrets
import struct
from dataclasses import dataclass


@dataclass(frozen=True)
class ProbeResult:
    sqlstate: str | None  # None = the login succeeded
    message: str


class ProbeError(Exception):
    """The probe itself could not get an answer (network, unexpected message)."""


def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", "replace")


def _error_fields(payload: bytes) -> dict[str, str]:
    fields: dict[str, str] = {}
    for part in payload.split(b"\x00"):
        if part:
            fields[chr(part[0])] = _decode(part[1:])
    return fields


def _msg(kind: bytes, payload: bytes) -> bytes:
    return kind + struct.pack("!I", len(payload) + 4) + payload


class _Conn:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.reader = reader
        self.writer = writer

    async def send(self, data: bytes) -> None:
        self.writer.write(data)
        await self.writer.drain()

    async def recv(self) -> tuple[bytes, bytes]:
        header = await self.reader.readexactly(5)
        kind, length = header[:1], struct.unpack("!I", header[1:])[0]
        return kind, await self.reader.readexactly(length - 4)


def _scram_client_final(password: str, client_first_bare: str, server_first: str) -> str:
    attrs = dict(item.split("=", 1) for item in server_first.split(","))
    salt = base64.b64decode(attrs["s"])
    iterations = int(attrs["i"])
    nonce = attrs["r"]
    salted = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    client_key = hmac.new(salted, b"Client Key", hashlib.sha256).digest()
    stored_key = hashlib.sha256(client_key).digest()
    without_proof = f"c=biws,r={nonce}"
    auth_message = f"{client_first_bare},{server_first},{without_proof}".encode()
    signature = hmac.new(stored_key, auth_message, hashlib.sha256).digest()
    proof = bytes(a ^ b for a, b in zip(client_key, signature, strict=True))
    return f"{without_proof},p={base64.b64encode(proof).decode()}"


async def _login(conn: _Conn, user: str, password: str, database: str) -> ProbeResult:
    startup = (("user", user), ("database", database), ("application_name", "nestris-ltm-probe"))
    params = b"".join(k.encode() + b"\x00" + v.encode() + b"\x00" for k, v in startup)
    body = struct.pack("!I", 196608) + params + b"\x00"
    await conn.send(struct.pack("!I", len(body) + 4) + body)
    client_first_bare = ""
    while True:
        kind, payload = await conn.recv()
        if kind == b"E":
            fields = _error_fields(payload)
            return ProbeResult(fields.get("C", "XX000"), fields.get("M", ""))
        if kind != b"R":
            raise ProbeError(f"unexpected message {kind!r}")
        code = struct.unpack("!I", payload[:4])[0]
        if code == 0:  # AuthenticationOk
            return ProbeResult(None, "ok")
        if code == 3:  # cleartext
            await conn.send(_msg(b"p", password.encode() + b"\x00"))
        elif code == 5:  # md5
            salt = payload[4:8]
            inner = hashlib.md5((password + user).encode()).hexdigest()
            outer = hashlib.md5(inner.encode() + salt).hexdigest()
            await conn.send(_msg(b"p", f"md5{outer}".encode() + b"\x00"))
        elif code == 10:  # SASL: pick SCRAM-SHA-256
            mechanisms = payload[4:].split(b"\x00")
            if b"SCRAM-SHA-256" not in mechanisms:
                raise ProbeError("no supported SASL mechanism")
            client_first_bare = f"n=,r={base64.b64encode(secrets.token_bytes(18)).decode()}"
            first = f"n,,{client_first_bare}".encode()
            await conn.send(
                _msg(b"p", b"SCRAM-SHA-256\x00" + struct.pack("!I", len(first)) + first)
            )
        elif code == 11:  # SASLContinue
            final = _scram_client_final(password, client_first_bare, payload[4:].decode())
            await conn.send(_msg(b"p", final.encode()))
        elif code == 12:  # SASLFinal; AuthenticationOk follows
            continue
        else:
            raise ProbeError(f"unsupported authentication method {code}")


async def probe_login(
    host: str,
    port: int,
    user: str,
    password: str,
    database: str = "postgres",
    *,
    limit_s: float = 5,
) -> ProbeResult:
    try:
        async with asyncio.timeout(limit_s):
            reader, writer = await asyncio.open_connection(host, port)
            try:
                return await _login(_Conn(reader, writer), user, password, database)
            finally:
                writer.close()
    except (OSError, TimeoutError, asyncio.IncompleteReadError, ValueError, KeyError) as exc:
        raise ProbeError(f"{type(exc).__name__}: {exc}") from exc
