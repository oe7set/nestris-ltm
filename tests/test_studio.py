"""Scene studio: settings and layout validation, migration 0007, layout API."""

from __future__ import annotations

import copy
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from nestris_ltm.api.app import create_app
from nestris_ltm.config import DatabaseSettings, load_settings
from nestris_ltm.core import overlay_layout as ol
from nestris_ltm.core import scene_settings as ss
from nestris_ltm.db.bootstrap import alembic_config, ensure_database, migrate
from nestris_ltm.db.models import Station
from nestris_ltm.runtime import Runtime

# ---------------------------------------------------------------- settings


def test_settings_default_to_nes_and_are_strict() -> None:
    assert ss.SceneSettings().style == "nes"
    stored = ss.from_client(
        {"style": "modern", "title": "  Finale  ", "theme": {"accent": "#FFaa00"}}
    ).stored()
    assert stored["style"] == "modern" and stored["title"] == "Finale"
    assert stored["theme"] == {"accent": "#FFaa00"}
    for bad in (
        {"bogus": 1},
        {"style": "neon"},
        {"theme": {"accent": "red"}},
        {"theme": {"unknown": "#000000"}},
        {"show": {"everything": False}},
        {"title": "x" * 65},
    ):
        with pytest.raises(ValueError):
            ss.from_client(bad)
    # A client never sets the replay; the scene's one is kept.
    kept = ss.from_client({"replay": {"game_id": 666}}, keep_replay={"game_id": 1})
    assert kept.replay == {"game_id": 1}
    assert "replay" not in kept.appearance()


def test_normalize_keeps_what_is_valid() -> None:
    settings, dropped = ss.normalize(
        {"style": "modern", "lang": "xx", "foo": True, "theme": {"accent": "#00ff00", "bad": "no"},
         "show": "nope", "camera_frames": True}
    )  # fmt: skip
    assert settings.style == "modern" and settings.lang == "de" and settings.camera_frames
    assert settings.theme.accent == "#00ff00" and settings.theme.bad is None
    assert sorted(dropped) == ["foo", "lang", "show", "theme.bad"]
    assert ss.normalize(None)[0].style == "nes"  # nothing stored: the NES standard


# ---------------------------------------------------------------- layout definitions

VALID: dict[str, Any] = {
    "schema": 1,
    "slots": 2,
    "pairs": [[0, 1]],
    "elements": [
        {"id": "cam0", "type": "camera", "slot": 0, "x": 0, "y": 0, "w": 400, "h": 900},
        {"id": "board0", "type": "board", "slot": 0, "x": 600, "y": 80, "w": 360, "h": 720},
        {"id": "score0", "type": "stat", "slot": 0, "x": 410, "y": 80, "w": 180, "h": 90,
         "props": {"field": "score"}},
        {"id": "board1", "type": "board", "slot": 1, "x": 980, "y": 80, "w": 360, "h": 720},
        {"id": "vs", "type": "versus", "pair": 0, "x": 760, "y": 820, "w": 400, "h": 200},
        {"id": "round", "type": "round", "pair": 0, "x": 860, "y": 10, "w": 200, "h": 50},
        {"id": "txt", "type": "text", "x": 10, "y": 1000, "w": 600, "h": 60,
         "props": {"text": "Retroverse 2026", "size": 32}},
    ],
}  # fmt: skip


def test_valid_definition_is_normalized() -> None:
    d = ol.parse(VALID)
    dumped = d.dump()
    assert dumped["schema"] == 1 and dumped["canvas"] == {"w": 1920, "h": 1080}
    score = next(e for e in dumped["elements"] if e["id"] == "score0")
    assert score["props"] == {"field": "score", "show_label": True, "align": "left"}
    assert ol.parse(dumped).dump() == dumped  # stable round trip
    layout = ol.to_layout("abc", "Test", "", d)
    assert layout.id == "custom:abc" and layout.slots == 2 and layout.pairs == ((0, 1),)


def _broken(change: Any) -> dict[str, Any]:
    data = copy.deepcopy(VALID)
    change(data)
    return data


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d["elements"].append(dict(d["elements"][0])), "used twice"),
        (lambda d: d["elements"][1].update(slot=5), "does not exist"),
        (lambda d: d["elements"][1].pop("slot"), "needs a slot"),
        (lambda d: d["elements"][4].update(pair=3), "does not exist"),
        (lambda d: d["elements"][6].update(slot=0), "takes no slot"),
        (lambda d: d["elements"][2]["props"].update(field="money"), "field"),
        (lambda d: d["elements"][2]["props"].update(evil="<script>"), "evil"),
        (lambda d: d["elements"][0].update(x=5000), "x"),
        (lambda d: d["elements"][0].update(w=2), "w"),
        (lambda d: d.update(pairs=[[0, 1], [1, 0]]), "at most one pair"),
        (lambda d: d.update(pairs=[[0, 3]]), "beyond"),
        (lambda d: d.update(slots=9), "slots"),
        (lambda d: d.update(schema=2), "not supported"),
        (lambda d: d.update(canvas={"w": 1280, "h": 720}), "canvas"),
        (lambda d: d.update(extra=True), "extra"),
        (lambda d: d["elements"].extend(
            {"id": f"t{i}", "type": "text", "x": 0, "y": 0, "w": 10, "h": 10, "props": {"text": "x"}}
            for i in range(300)), "300"),
    ],
)  # fmt: skip
def test_invalid_definitions_are_rejected(change: Any, message: str) -> None:
    with pytest.raises(ValueError) as err:
        ol.parse(_broken(change))
    assert message in str(err.value)


# ---------------------------------------------------------------- migration 0007


@pytest.mark.db
async def test_migration_switches_every_scene_to_nes(fresh_db_settings: DatabaseSettings) -> None:
    await ensure_database(fresh_db_settings)
    engine = create_async_engine(fresh_db_settings.url())
    try:
        cfg = alembic_config()

        def upgrade_to(connection: Any, target: str) -> None:
            cfg.attributes["connection"] = connection
            command.upgrade(cfg, target)

        async with engine.begin() as conn:
            await conn.run_sync(upgrade_to, "0006")
            await conn.execute(text(
                "INSERT INTO scenes (slug, name, layout, settings) VALUES "
                "('a', 'A', '1v1', '{\"style\": \"modern\", \"lang\": \"en\"}'), "
                "('b', 'B', '1v1', '{}'), ('c', 'C', '4p', '{\"style\": \"nes\"}')"
            ))  # fmt: skip
        await migrate(engine)
        async with engine.connect() as conn:
            rows = dict((await conn.execute(text("SELECT slug, settings FROM scenes"))).all())
            audits = (await conn.execute(text(
                "SELECT entity_id, before->>'style' FROM audit_log WHERE actor = 'migration'"
            ))).all()  # fmt: skip
            width = await conn.scalar(text(
                "SELECT character_maximum_length FROM information_schema.columns "
                "WHERE table_name = 'scenes' AND column_name = 'layout'"
            ))  # fmt: skip
        assert {k: v["style"] for k, v in rows.items()} == {"a": "nes", "b": "nes", "c": "nes"}
        assert rows["a"]["lang"] == "en"  # everything else stays
        assert sorted(b for _, b in audits) == ["modern", "modern"]  # a and b changed, c not
        assert width == 64
    finally:
        await engine.dispose()


# ---------------------------------------------------------------- API


@pytest.fixture
async def runtime(tmp_path: Path, fresh_db_settings: DatabaseSettings) -> AsyncIterator[Runtime]:
    rt = Runtime(
        load_settings(tmp_path / "none.toml", database=fresh_db_settings, data_dir=tmp_path)
    )
    await rt.db.run_bootstrap()
    async with rt.db.session() as s, s.begin():
        s.add_all([Station(id=f"st-{i}") for i in range(1, 5)])
    try:
        yield rt
    finally:
        await rt.updates.github.close()
        await rt.devices.close()
        await rt.db.dispose()


@pytest.fixture
async def client(runtime: Runtime) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=create_app(runtime), client=("192.168.1.50", 5000))
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://t",
        headers={"X-NestrisLTM-Shell-Token": runtime.shell_token},
    ) as c:
        yield c


@pytest.mark.db
async def test_scene_settings_api(runtime: Runtime, client: httpx.AsyncClient) -> None:
    r = await client.post("/api/scenes", json={"slug": "buehne", "name": "Bühne", "layout": "1v1_cam",
                                               "settings": {"camera_frames": True}})  # fmt: skip
    assert r.status_code == 201, r.text
    scene = r.json()
    assert scene["settings"]["style"] == "nes" and scene["settings"]["camera_frames"]
    bad = await client.post("/api/scenes", json={"slug": "x", "name": "X", "layout": "1v1",
                                                 "settings": {"script": "<b>"}})  # fmt: skip
    assert bad.status_code == 422
    assert (
        await client.post("/api/scenes", json={"slug": "y", "name": "Y", "layout": "custom:nope"})
    ).status_code == 422

    # The replay of a scene survives an edit of its look.
    async with runtime.db.session() as s, s.begin():
        await s.execute(
            text(
                "UPDATE scenes SET settings = settings || '{\"replay\": {\"game_id\": 7}}' WHERE slug = 'buehne'"
            )
        )
    r = await client.patch(f"/api/scenes/{scene['id']}", json={"settings": {"style": "modern"}})
    assert r.status_code == 200 and r.json()["settings"]["replay"] == {"game_id": 7}
    assert r.json()["settings"]["style"] == "modern"

    # Optimistic locking.
    stale = await client.patch(f"/api/scenes/{scene['id']}", json={"name": "Neu",
                                                                  "expected_updated_at": scene["updated_at"]})  # fmt: skip
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "stale"
    current = r.json()["updated_at"]
    ok = await client.patch(
        f"/api/scenes/{scene['id']}", json={"name": "Neu", "expected_updated_at": current}
    )
    assert ok.status_code == 200

    # Duplicate: new URL, same look and stations, no replay.
    await client.patch(
        f"/api/scenes/{scene['id']}", json={"slots": [{"slot": 0, "station_id": "st-1"}]}
    )
    dup = await client.post(f"/api/scenes/{scene['id']}/duplicate", json={})
    assert dup.status_code == 201
    d = dup.json()
    assert d["slug"] == "buehne-kopie" and d["name"] == "Neu (Kopie)"
    assert d["settings"]["style"] == "modern" and "replay" not in d["settings"]
    assert d["slots"][0]["station_id"] == "st-1"
    assert (await client.post(f"/api/scenes/{scene['id']}/duplicate", json={})).json()[
        "slug"
    ] == "buehne-kopie-2"


@pytest.mark.db
async def test_layout_api(runtime: Runtime, client: httpx.AsyncClient) -> None:
    r = await client.post("/api/overlay-layouts", json={"name": "Mein 1v1", "definition": VALID})
    assert r.status_code == 201, r.text
    layout = r.json()
    key, lid = layout["key"], layout["id"]
    assert key == f"custom:{lid}" and layout["version"] == 1 and layout["slots"] == 2

    bad = _broken(lambda d: d["elements"][1].update(slot=7))
    r = await client.post("/api/overlay-layouts", json={"name": "x", "definition": bad})
    assert r.status_code == 422 and r.json()["detail"]["errors"][0]["element"] is not None

    # Listed next to the built-in layouts; usable by a scene; public for the overlay.
    layouts = (await client.get("/api/scenes/layouts")).json()
    assert any(item["id"] == key and item["custom"] for item in layouts)
    r = await client.post("/api/scenes", json={"slug": "eigen", "name": "Eigen", "layout": key,
                                               "slots": [{"slot": i, "station_id": f"st-{i + 1}"} for i in range(4)]})  # fmt: skip
    assert r.status_code == 201
    assert len(r.json()["slots"]) == 2  # the layout has two slots
    await runtime.scenes.load()
    state = runtime.scenes.compute_state(runtime.scenes.scenes["eigen"])
    assert state["scene"]["layout"] == key and state["scene"]["layout_rev"] == f"{lid}:1"
    assert state["scene"]["pairs"] == [[0, 1]] and [g["group"] for g in state["groups"]] == [0]
    async with httpx.AsyncClient(
        transport=client._transport, base_url="http://t"
    ) as public:  # no admin
        assert (await public.get(f"/api/overlay-layouts/{lid}")).status_code == 200
        assert (await public.get("/api/overlay-layouts")).status_code == 401

    # Saving: optimistic locking, then a new revision for the overlays.
    changed = copy.deepcopy(VALID)
    changed["elements"][1]["x"] = 620
    r = await client.put(
        f"/api/overlay-layouts/{lid}", json={"expected_version": 1, "definition": changed}
    )
    assert r.status_code == 200 and r.json()["version"] == 2
    stale = await client.put(
        f"/api/overlay-layouts/{lid}", json={"expected_version": 1, "name": "x"}
    )
    assert stale.status_code == 409 and stale.json()["detail"]["version"] == 2
    assert (
        runtime.scenes.compute_state(runtime.scenes.scenes["eigen"])["scene"]["layout_rev"]
        == f"{lid}:2"
    )
    # Fewer slots than a scene uses: refused.
    one = {**VALID, "slots": 1, "pairs": [], "elements": [VALID["elements"][0]]}
    r = await client.put(
        f"/api/overlay-layouts/{lid}", json={"expected_version": 2, "definition": one}
    )
    assert r.status_code == 409

    # Duplicate, and no delete while a scene uses it.
    dup = await client.post(f"/api/overlay-layouts/{lid}/duplicate", json={})
    assert dup.status_code == 201 and dup.json()["name"] == "Mein 1v1 (Kopie)"
    r = await client.delete(f"/api/overlay-layouts/{lid}")
    assert r.status_code == 409 and r.json()["detail"]["scenes"] == ["eigen"]
    assert (await client.delete(f"/api/overlay-layouts/{dup.json()['id']}")).status_code == 200
    listing = (await client.get("/api/overlay-layouts")).json()
    assert [x["used_by"] for x in listing] == [["eigen"]]


# ---------------------------------------------------------------- export / import


async def _import(client: httpx.AsyncClient, file: dict[str, Any], **kw: Any) -> httpx.Response:
    return await client.post("/api/studio/import", json={"file": file, **kw})


@pytest.mark.db
async def test_export_import_round_trip(runtime: Runtime, client: httpx.AsyncClient) -> None:
    lay = (await client.post("/api/overlay-layouts", json={"name": "Eigen", "definition": VALID})).json()
    a = (await client.post("/api/scenes", json={
        "slug": "buehne", "name": "Bühne", "layout": lay["key"],
        "settings": {"style": "nes", "theme": {"accent": "#ff00ff"}},
        "slots": [{"slot": 0, "station_id": "st-1", "name_override": "Erv"}],
    })).json()  # fmt: skip
    b = (await client.post("/api/scenes", json={"slug": "vier", "name": "Vier", "layout": "2x1v1_cam"})).json()
    async with runtime.db.session() as s, s.begin():
        await s.execute(text("UPDATE scenes SET settings = settings || '{\"replay\": {\"game_id\": 1}}' WHERE slug = 'buehne'"))

    r = await client.get(f"/api/studio/export?scenes={a['id']}")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    file = r.json()
    assert file["format"] == "nestrisltm/scenes" and [s["slug"] for s in file["scenes"]] == ["buehne"]
    assert [x["id"] for x in file["layouts"]] == [lay["id"]]  # its own layout travels along
    scene = file["scenes"][0]
    assert "replay" not in scene["settings"] and "slots" not in scene  # only the look
    assert scene["settings"]["theme"] == {"accent": "#ff00ff"}
    everything = (await client.get("/api/studio/export")).json()
    assert {s["slug"] for s in everything["scenes"]} == {"buehne", "vier"}

    # Into an empty installation: everything new, the layout keeps its id.
    await client.delete(f"/api/scenes/{a['id']}")
    await client.delete(f"/api/scenes/{b['id']}")
    await client.delete(f"/api/overlay-layouts/{lay['id']}")
    dry = (await _import(client, file)).json()
    assert dry["ok"] and dry["scenes"][0]["status"] == "new" and dry["layouts"][0]["status"] == "new"
    assert (await client.get("/api/scenes")).json() == []  # a dry run changes nothing
    done = await _import(client, file, dry_run=False)
    assert done.status_code == 200, done.text
    scenes = (await client.get("/api/scenes")).json()
    assert [(s["slug"], s["layout"]) for s in scenes] == [("buehne", lay["key"])]
    assert scenes[0]["slots"] == [] and scenes[0]["settings"]["theme"] == {"accent": "#ff00ff"}

    # Again: the scene is in conflict (default: a renamed copy), the layout identical.
    dry = (await _import(client, file)).json()
    assert dry["scenes"][0]["status"] == "conflict" and dry["scenes"][0]["suggested_slug"] == "buehne-2"
    assert dry["layouts"][0]["status"] == "same"
    await _import(client, file, dry_run=False)
    assert sorted(s["slug"] for s in (await client.get("/api/scenes")).json()) == ["buehne", "buehne-2"]
    assert len((await client.get("/api/overlay-layouts")).json()) == 1

    # Overwrite keeps the stations of the existing scene.
    target = next(s for s in (await client.get("/api/scenes")).json() if s["slug"] == "buehne")
    await client.patch(f"/api/scenes/{target['id']}", json={"settings": {"style": "modern"},
                                                            "slots": [{"slot": 0, "station_id": "st-2"}]})  # fmt: skip
    await _import(client, file, dry_run=False, scenes={"buehne": "overwrite"}, layouts={lay["id"]: "keep"})
    target = next(s for s in (await client.get("/api/scenes")).json() if s["slug"] == "buehne")
    assert target["settings"]["style"] == "nes" and target["slots"][0]["station_id"] == "st-2"


@pytest.mark.db
async def test_import_conflicts_and_errors(runtime: Runtime, client: httpx.AsyncClient) -> None:
    lay = (await client.post("/api/overlay-layouts", json={"name": "Eigen", "definition": VALID})).json()
    await client.post("/api/scenes", json={"slug": "eigen", "name": "Eigen", "layout": lay["key"]})
    file = (await client.get("/api/studio/export")).json()

    # The local layout changed meanwhile: conflict. "copy" adds a new layout and
    # the imported scene uses the copy.
    changed = copy.deepcopy(VALID)
    changed["elements"][1]["x"] = 700
    await client.put(f"/api/overlay-layouts/{lay['id']}", json={"expected_version": 1, "definition": changed})
    dry = (await _import(client, file)).json()
    assert dry["layouts"][0]["status"] == "conflict"
    r = await _import(client, file, dry_run=False, layouts={lay["id"]: "copy"})
    assert r.status_code == 200, r.text
    layouts = {x["name"]: x for x in (await client.get("/api/overlay-layouts")).json()}
    assert set(layouts) == {"Eigen", "Eigen (Import)"}
    copy_key = layouts["Eigen (Import)"]["key"]
    assert {s["slug"]: s["layout"] for s in (await client.get("/api/scenes")).json()}["eigen-2"] == copy_key
    # "replace" overwrites the local layout instead.
    r = await _import(client, file, dry_run=False, scenes={"eigen": "skip"}, layouts={lay["id"]: "replace"})
    assert r.status_code == 200
    replaced = (await client.get(f"/api/overlay-layouts/{lay['id']}")).json()
    assert replaced["definition"]["elements"][1]["x"] == VALID["elements"][1]["x"] and replaced["version"] == 3

    # Not allowed for the status: refused, nothing changes.
    before = len((await client.get("/api/scenes")).json())
    r = await _import(client, file, dry_run=False, scenes={"eigen": "create"})
    assert r.status_code == 409
    assert len((await client.get("/api/scenes")).json()) == before

    # Broken files.
    assert (await _import(client, {"format": "other"})).status_code == 422
    assert (await _import(client, {**file, "version": 9})).status_code == 422
    bad = copy.deepcopy(file)
    bad["scenes"][0]["settings"] = {"style": "neon"}
    bad["layouts"][0]["definition"]["elements"][0]["slot"] = 7
    dry = (await _import(client, bad)).json()
    assert not dry["ok"] and dry["scenes"][0]["errors"] and dry["layouts"][0]["errors"]
    r = await _import(client, bad, dry_run=False)
    assert r.status_code == 409 and len((await client.get("/api/scenes")).json()) == before
    huge = {**file, "layouts": [], "scenes": [{**file["scenes"][0], "name": "x" * 100}] * 20000}
    assert (await _import(client, huge)).status_code in (413, 422)
    missing = copy.deepcopy(file)
    missing["layouts"] = []
    missing["scenes"][0]["layout"] = "custom:00000000-0000-4000-8000-000000000000"
    assert "neither built in" in (await _import(client, missing)).json()["scenes"][0]["errors"][0]
