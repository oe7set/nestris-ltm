"""Pure helpers for updates: version ordering, checksum files, signatures.

The release convention (all Retroverse repositories, see docs/UPDATES.md):
tags ``v<semver>``, a ``SHA256SUMS.txt`` (``<sha256>  <file>`` per line) and
``SHA256SUMS.txt.sig`` (base64 Ed25519 signature of the checksum file's
bytes, made with the release key whose public half is listed here).
"""

from __future__ import annotations

import base64
import binascii
import re
from dataclasses import dataclass, field

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

# Accepted release-signing public keys (raw Ed25519, base64). A list so a new
# key can be added before the old one is retired (docs/UPDATES.md).
RELEASE_PUBLIC_KEYS: tuple[str, ...] = ("CQqYvIf/DIFS0ctwZaWQEK2wCdG7Oy3jN+YkF7nRgNQ=",)

_SEMVER = re.compile(
    r"^v?(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<pre>[0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$"
)


# Python packages write pre-releases the PEP 440 way: 1.2.0a1, 1.2.0b2, 1.2.0rc1.
_PEP440 = re.compile(
    r"^v?(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:[-.]?(?P<kind>a|alpha|b|beta|c|rc|pre|preview)[-.]?(?P<num>\d+)?)?$",
    re.IGNORECASE,
)
_KIND = {"a": "alpha", "alpha": "alpha", "b": "beta", "beta": "beta", "c": "rc", "rc": "rc",
         "pre": "rc", "preview": "rc"}  # fmt: skip


@dataclass(frozen=True, order=False)
class Version:
    """A release version: semver (``1.2.0-beta.1``) or PEP 440 (``1.2.0b1``).

    Both spellings of the same version compare equal; ``str()`` gives the
    spelling it was parsed from (it names the release's files).
    """

    major: int
    minor: int
    patch: int
    pre: tuple[int | str, ...] = ()  # empty = a release
    text: str = field(default="", compare=False)

    @classmethod
    def parse(cls, text: str) -> Version | None:
        raw = text.strip()
        clean = raw[1:] if raw[:1] in "vV" else raw
        m = _SEMVER.match(raw)
        if m is not None:
            pre: tuple[int | str, ...] = ()
            if m["pre"]:
                pre = tuple(int(p) if p.isdigit() else p.lower() for p in m["pre"].split("."))
                # "beta1" / "rc1" spelled as one identifier: same as beta.1 / rc.1
                if len(pre) == 1 and isinstance(pre[0], str):
                    pm = re.fullmatch(r"(alpha|beta|rc|a|b|c)(\d+)", pre[0])
                    if pm:
                        pre = (_KIND[pm[1]], int(pm[2]))
                elif pre and isinstance(pre[0], str) and pre[0] in _KIND:
                    pre = (_KIND[pre[0]], *pre[1:])
            return cls(int(m["major"]), int(m["minor"]), int(m["patch"]), pre, clean)
        m = _PEP440.match(raw)
        if m is None:
            return None
        pre = ()
        if m["kind"]:
            pre = (_KIND[m["kind"].lower()], int(m["num"] or 0))
        return cls(int(m["major"]), int(m["minor"]), int(m["patch"]), pre, clean)

    @property
    def is_prerelease(self) -> bool:
        return bool(self.pre)

    def _key(self) -> tuple[object, ...]:
        # semver precedence: a pre-release sorts before its release; numeric
        # identifiers sort before alphanumeric ones.
        pre_key = tuple((0, p, "") if isinstance(p, int) else (1, 0, p) for p in self.pre)
        return (self.major, self.minor, self.patch, 0 if self.pre else 1, pre_key)

    def __lt__(self, other: Version) -> bool:
        return self._key() < other._key()

    def __le__(self, other: Version) -> bool:
        return self._key() <= other._key()

    def __gt__(self, other: Version) -> bool:
        return self._key() > other._key()

    def __ge__(self, other: Version) -> bool:
        return self._key() >= other._key()

    def __str__(self) -> str:
        if self.text:
            return self.text
        core = f"{self.major}.{self.minor}.{self.patch}"
        return core + ("-" + ".".join(str(p) for p in self.pre) if self.pre else "")


def parse_sums(text: str) -> dict[str, str]:
    """``SHA256SUMS.txt`` -> {file name: lowercase sha256}. Bad lines are skipped."""
    sums: dict[str, str] = {}
    for line in text.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            continue
        sums[parts[1].lstrip("*").strip()] = parts[0].lower()
    return sums


def verify_signature(
    data: bytes, signature_text: str, public_keys: tuple[str, ...] = RELEASE_PUBLIC_KEYS
) -> bool:
    """True if ``signature_text`` (base64) signs ``data`` with one of the keys."""
    try:
        signature = base64.b64decode(signature_text.strip(), validate=True)
    except (binascii.Error, ValueError):
        return False
    for key in public_keys:
        try:
            Ed25519PublicKey.from_public_bytes(base64.b64decode(key)).verify(signature, data)
        except (InvalidSignature, ValueError):
            continue
        return True
    return False
