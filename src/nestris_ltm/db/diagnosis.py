"""What is wrong with the database, in terms an operator can act on.

``classify`` turns whatever the bootstrap raised (asyncpg, OS, Alembic or
our own errors, possibly wrapped by SQLAlchemy) into a short, stable state
code. The admin UI translates the code into a title and solution steps
(i18n keys ``db.state.<code>.*``); the tray and the CLI use the German texts
in ``HINTS`` because they run without the UI.

Permanent problems (wrong password, schema newer than the app, ...) do not
go away by waiting, so the manager retries them slowly; transient ones
(server not running yet) are retried with a short backoff.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import asyncpg

from nestris_ltm.db.pgprobe import ProbeError, probe_login

if TYPE_CHECKING:
    from nestris_ltm.config import DatabaseSettings

# State codes (also used by the API and the admin UI).
CONNECTING = "connecting"
READY = "ready"
UNREACHABLE = "unreachable"
AUTH_FAILED = "auth_failed"
AUTH_REJECTED = "auth_rejected"
NO_CREATE_PERMISSION = "no_create_permission"
SCHEMA_TOO_NEW = "schema_too_new"
MIGRATION_FAILED = "migration_failed"
RESTORING = "restoring"
UNKNOWN = "unknown"

PERMANENT_STATES = frozenset(
    {AUTH_FAILED, AUTH_REJECTED, NO_CREATE_PERMISSION, SCHEMA_TOO_NEW, MIGRATION_FAILED}
)
# The app must not write anything in these states; the tray shows red.
BLOCKING_STATES = frozenset({SCHEMA_TOO_NEW, MIGRATION_FAILED})


class SchemaTooNewError(RuntimeError):
    """The database was migrated by a newer NestrisLTM than this one."""

    def __init__(self, db_revision: str, app_head: str | None, migrated_by: str | None) -> None:
        by = f" by NestrisLTM {migrated_by}" if migrated_by else ""
        super().__init__(
            f"database schema {db_revision}{by} is newer than this app knows (latest {app_head})"
        )
        self.db_revision = db_revision
        self.app_head = app_head
        self.migrated_by = migrated_by


class MigrationFailedError(RuntimeError):
    """An Alembic upgrade failed (its transaction was rolled back)."""

    def __init__(self, from_revision: str | None, to_revision: str | None, cause: BaseException):
        super().__init__(
            f"migration {from_revision or 'empty'} -> {to_revision} failed: "
            f"{type(cause).__name__}: {cause}"
        )
        self.from_revision = from_revision
        self.to_revision = to_revision


@dataclass(frozen=True)
class DbProblem:
    state: str
    detail: str
    permanent: bool
    # State-specific facts for the UI (schema revisions, ...).
    extra: dict[str, Any] = field(default_factory=dict)


def _chain(exc: BaseException) -> list[BaseException]:
    """The exception and everything it wraps (SQLAlchemy ``orig``, causes)."""
    seen: list[BaseException] = []
    todo: list[BaseException | None] = [exc]
    while todo:
        cur = todo.pop(0)
        if cur is None or any(cur is s for s in seen):
            continue
        seen.append(cur)
        todo.extend([getattr(cur, "orig", None), cur.__cause__, cur.__context__])
    return seen


def _detail(exc: BaseException) -> str:
    text = str(exc).strip() or type(exc).__name__
    return f"{type(exc).__name__}: {text}"


def classify(exc: BaseException) -> DbProblem:
    chain = _chain(exc)

    def find[E: BaseException](kind: type[E]) -> E | None:
        return next((e for e in chain if isinstance(e, kind)), None)

    if (too_new := find(SchemaTooNewError)) is not None:
        return DbProblem(
            SCHEMA_TOO_NEW,
            str(too_new),
            True,
            {
                "db_revision": too_new.db_revision,
                "app_head": too_new.app_head,
                "migrated_by": too_new.migrated_by,
            },
        )
    if (failed := find(MigrationFailedError)) is not None:
        return DbProblem(
            MIGRATION_FAILED,
            str(failed),
            True,
            {"db_revision": failed.from_revision, "app_head": failed.to_revision},
        )
    # 28P01 is a subclass of 28000, so check the password first.
    if (pw := find(asyncpg.InvalidPasswordError)) is not None:
        return DbProblem(AUTH_FAILED, _detail(pw), True)
    if (rejected := find(asyncpg.InvalidAuthorizationSpecificationError)) is not None:
        return DbProblem(AUTH_REJECTED, _detail(rejected), True)
    if (priv := find(asyncpg.InsufficientPrivilegeError)) is not None:
        return DbProblem(NO_CREATE_PERMISSION, _detail(priv), True)
    if (starting := find(asyncpg.CannotConnectNowError)) is not None:
        return DbProblem(UNREACHABLE, _detail(starting), False)
    # Refused, timeout, unknown host name: all OSError subclasses.
    if (os_error := find(OSError)) is not None:
        return DbProblem(UNREACHABLE, _detail(os_error), False)
    return DbProblem(UNKNOWN, _detail(exc), False)


# The server closed the connection during the login: on a German Windows
# install that is how asyncpg reports a rejected login (see db/pgprobe.py).
_AMBIGUOUS = (asyncpg.ConnectionDoesNotExistError, ConnectionResetError)
_LOGIN_STATES = {"28P01": AUTH_FAILED, "28000": AUTH_REJECTED}


async def diagnose(exc: BaseException, settings: DatabaseSettings) -> DbProblem:
    """``classify``, plus a login probe when the failure is ambiguous."""
    problem = classify(exc)
    if problem.state != UNREACHABLE or not any(isinstance(e, _AMBIGUOUS) for e in _chain(exc)):
        return problem
    try:
        result = await probe_login(
            settings.host,
            settings.port,
            settings.user,
            settings.password.get_secret_value(),
            limit_s=settings.connect_timeout_s,
        )
    except ProbeError:
        return problem
    state = _LOGIN_STATES.get(result.sqlstate or "")
    if state is None:
        return problem
    return DbProblem(state, f"{result.sqlstate}: {result.message}", True)


# German texts for the tray and the CLI (the admin UI has its own, de + en).
HINTS: dict[str, tuple[str, list[str]]] = {
    CONNECTING: ("verbinde ...", []),
    READY: ("ok", []),
    UNREACHABLE: (
        "PostgreSQL nicht erreichbar",
        [
            "Läuft der Dienst? Dienste (services.msc) -> postgresql-x64-18 -> Starten.",
            "Stimmen Host und Port in der Konfiguration (Standard 127.0.0.1:5432)?",
            "Belegt ein anderes Programm (Docker, zweite PostgreSQL-Installation) den Port?",
        ],
    ),
    AUTH_FAILED: (
        "Passwort falsch",
        [
            "Das richtige Passwort des Datenbank-Benutzers eintragen:"
            " nestris-ltm configure --db-password <pw> (oder im Admin-Fenster).",
            "Passwort vergessen: siehe docs/OPERATIONS.md, Abschnitt"
            " 'PostgreSQL-Passwort vergessen'.",
        ],
    ),
    AUTH_REJECTED: (
        "Anmeldung abgelehnt",
        [
            "Gibt es den Benutzer? Darf er sich von diesem Rechner anmelden (pg_hba.conf)?",
            "Benutzername in der Konfiguration prüfen: nestris-ltm configure --db-user <name>.",
        ],
    ),
    NO_CREATE_PERMISSION: (
        "keine Rechte, die Datenbank anzulegen",
        [
            "Die Datenbank einmal als Superuser anlegen (CREATE DATABASE ...)"
            " oder dem Benutzer CREATEDB erlauben.",
            "Oder einen Benutzer mit diesen Rechten eintragen (z.B. postgres).",
        ],
    ),
    SCHEMA_TOO_NEW: (
        "Datenbank ist neuer als diese App",
        [
            "Die neuere NestrisLTM-Version wieder installieren (Updates), oder",
            "ein Backup von vor dem Update wiederherstellen (Admin-Fenster -> Datenbank).",
            "Bis dahin speichert NestrisLTM nichts; Ergebnisse der Stationen bleiben im Spool.",
        ],
    ),
    MIGRATION_FAILED: (
        "Datenbank-Update fehlgeschlagen",
        [
            "Die Änderung wurde zurückgerollt, die Daten sind unverändert.",
            "Details stehen im Log (Admin-Fenster -> Diagnose oder logs-Ordner).",
            "Neuere Version installieren oder ein Backup wiederherstellen.",
        ],
    ),
    RESTORING: ("Backup wird wiederhergestellt ...", []),
    UNKNOWN: (
        "unbekannter Datenbankfehler",
        ["Details im Log ansehen; NestrisLTM versucht es weiter."],
    ),
}


def title(state: str) -> str:
    return HINTS.get(state, HINTS[UNKNOWN])[0]


def steps(state: str) -> list[str]:
    return HINTS.get(state, HINTS[UNKNOWN])[1]
