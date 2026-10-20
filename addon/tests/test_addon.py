import json
from pathlib import Path

import pytest
from gaddhub_agent.config import Settings
from gaddhub_agent.export import read_export
from gaddhub_agent.store import Store
from gaddhub_agent.sync import Engine, UploadResult
from lupa.lua51 import LuaRuntime

ADDON = Path(__file__).parents[1] / "GaddHub"


def load_addon(lua):
    for line in (ADDON / "GaddHub.toc").read_text().splitlines():
        if line and not line.startswith("#"):
            lua.execute(ADDON.joinpath(*line.split("\\")).read_text(encoding="utf-8"))


@pytest.fixture
def client():
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute(Path(__file__).with_name("fake_client.lua").read_text(encoding="utf-8"))
    load_addon(lua)
    return lua


def export(client):
    text = client.eval("'GuildSyncDB = ' .. TestSerialize(GuildSyncDB)")
    return text.encode("utf-8")


def snapshot(client):
    assert client.eval("GaddHub.Capture()")
    return json.loads(read_export(export(client))[0][1])


def test_metadata_and_lua_runtime_match_test_target(client):
    assert client.eval("_VERSION") == "Lua 5.1"
    toc = (ADDON / "GaddHub.toc").read_text()
    assert "## Interface: 16001" in toc
    assert f"## Version: {client.eval('GaddHub.version')}" in toc
    assert "## SavedVariables: GuildSyncDB" in toc


def test_real_lua_collectors_export_agent_compatible_snapshot(client):
    data = snapshot(client)
    assert data["character"]["character_id"] == "Player-Test-1"
    assert data["character"]["name"] == "Gäddkrigaren"
    assert data["captured_at"] == "2026-10-20T20:00:00Z"
    sections = data["sections"]
    assert sections["equipment"]["items"][0]["item_id"] == 123
    assert sections["talents"]["build"]["trees"][0]["talents"][0]["rank"] == 2
    assert sections["inventory"]["items"][0]["count"] == 3
    assert sections["professions"]["items"][0]["skill_line_id"] == 356
    assert sections["bank"]["status"] == "unavailable" and "items" not in sections["bank"]
    assert sections["recipes"]["status"] == "not_collected"


@pytest.mark.parametrize(
    ("code", "section"),
    [
        ("GetInventoryItemID = nil", "equipment"),
        ("GetTalentInfo = nil", "talents"),
        ("GetProfessionInfo = nil", "professions"),
        ("C_Container = nil", "inventory"),
        ("GaddHub.tradeOpen = true; C_TradeSkillUI = nil", "recipes"),
        ("GaddHub.bankOpen = true; BANK_CONTAINER = nil", "bank"),
    ],
)
def test_missing_capabilities_are_not_fake_empty_data(client, code, section):
    client.execute(code)
    result = snapshot(client)["sections"][section]
    assert result["status"] == "unsupported"
    assert result["reason"]
    assert "items" not in result and "build" not in result


def test_collector_exception_is_visible_and_does_not_destroy_other_sections(client):
    client.execute("function GetTalentInfo() error('test API failure') end")
    result = snapshot(client)["sections"]
    assert result["talents"]["status"] == "error"
    assert "test API failure" in result["talents"]["reason"]
    assert result["equipment"]["status"] == "available"
    assert "test API failure" in client.eval("table.concat(MESSAGES, '\\n')")


def test_bounded_error_reason_preserves_utf8_and_schema(client):
    client.execute('function GetTalentInfo() error(string.rep("ä", 300), 0) end')
    reason = snapshot(client)["sections"]["talents"]["reason"]
    assert reason.endswith("...")
    assert len(reason.encode("utf-8")) <= 512


def test_unavailable_identity_prevents_capture_without_inventing_an_id(client):
    client.execute("UnitGUID = nil")
    assert not client.eval("GaddHub.Capture()")
    assert client.eval("GuildSyncDB == nil")
    assert "character APIs unavailable" in client.eval("GaddHub.lastError")


def test_bank_capture_survives_close_and_logout_with_original_timestamp(client):
    client.execute("GaddHub.bankOpen = true")
    snapshot(client)
    client.execute("GaddHub.bankOpen = false; TEST_TIMESTAMP = '2026-10-20T20:10:00Z'")
    snapshot(client)
    snapshots = [json.loads(body) for _, body in read_export(export(client))]
    assert len(snapshots) == 2
    assert snapshots[0]["sections"]["bank"]["status"] == "unavailable"
    bank = next(data for data in snapshots if data["sections"]["bank"]["status"] == "available")
    assert bank["captured_at"] == "2026-10-20T20:00:00Z"
    assert bank["sections"]["bank"]["items"][0]["bag"] == -1
    assert client.eval("#GuildSyncDB.snapshots") == 2


def test_unloaded_bank_and_occupied_slot_are_not_reported_as_empty(client):
    client.execute("""
        GaddHub.bankOpen = true
        local original = C_Container.GetContainerNumSlots
        function C_Container.GetContainerNumSlots(bag)
            return bag == -1 and 0 or original(bag)
        end
        function C_Container.GetContainerItemInfo() return nil end
    """)
    data = snapshot(client)["sections"]
    assert data["bank"]["status"] == "unavailable" and "items" not in data["bank"]
    assert data["inventory"]["status"] == "error" and "items" not in data["inventory"]


@pytest.mark.parametrize(
    ("code", "section"),
    [
        ("function GetInventoryItemID() return nil end", "equipment"),
        ("function C_Container.GetContainerItemID() return nil end", "inventory"),
    ],
)
def test_inconsistent_item_id_and_details_do_not_silently_lose_items(client, code, section):
    if section == "inventory":
        client.execute("""
            function C_Container.GetContainerItemInfo(bag, slot)
                if bag == 0 and slot == 1 then return {itemID = 456, stackCount = 3} end
            end
        """)
    client.execute(code)
    data = snapshot(client)["sections"][section]
    assert data["status"] == "error"
    assert "items" not in data


def test_situational_snapshot_is_not_aliased_and_survives_addon_reload(client):
    client.execute("GaddHub.bankOpen = true; GaddHub.tradeOpen = true")
    snapshot(client)
    load_addon(client)
    client.execute("TEST_TIMESTAMP = '2026-10-20T20:15:00Z'")
    snapshot(client)
    data = [json.loads(body) for _, body in read_export(export(client))]
    assert len(data) == 2
    assert data[0]["sections"]["bank"]["status"] == "unavailable"
    assert data[1]["sections"]["bank"]["status"] == "available"
    assert data[1]["sections"]["recipes"]["status"] == "available"
    assert data[1]["captured_at"] == "2026-10-20T20:00:00Z"


def test_recipes_exclude_unlearned_and_linked_data(client):
    client.execute("GaddHub.tradeOpen = true")
    data = snapshot(client)
    assert data["sections"]["recipes"]["items"] == [{"recipe_id": 10, "name": "Recipe 10"}]
    client.execute("function C_TradeSkillUI.IsTradeSkillLinked() return true end")
    assert client.eval("GaddHub.collectors.recipes().status") == "unavailable"


def test_current_and_situational_snapshots_are_bounded_not_an_event_history(client):
    for minute in range(10):
        client.globals().TEST_TIMESTAMP = f"2026-10-20T20:{minute:02d}:00Z"
        assert client.eval("GaddHub.Capture()")
    assert len(read_export(export(client))) == 1
    client.execute("TEST_GUID = 'Player-Test-2'")
    assert client.eval("GaddHub.Capture()")
    assert len(read_export(export(client))) == 2


def test_malformed_or_future_database_is_not_overwritten(client):
    client.execute("GuildSyncDB = {schema_version = 99, snapshots = {}}")
    assert not client.eval("GaddHub.Capture()")
    assert client.eval("GuildSyncDB.schema_version") == 99
    assert "not overwritten" in client.eval("GaddHub.lastError")


def test_capacity_failure_preserves_existing_characters(client):
    snapshot(client)
    client.execute("""
        local original = GuildSyncDB.snapshots[1]
        for index = 1, 100 do
            local copy = TestClone(original)
            copy.character.character_id = "Player-" .. index
            GuildSyncDB.snapshots[index] = copy
        end
        TEST_GUID = "Player-101"
    """)
    assert not client.eval("GaddHub.Capture()")
    assert len(read_export(export(client))) == 100
    assert "capacity" in client.eval("GaddHub.lastError")


def test_events_debounce_and_logout_captures_without_a_timer(client):
    client.execute("""
        local frame = GaddHub.frame
        frame.scripts.OnEvent(frame, "PLAYER_LOGIN")
        frame.scripts.OnUpdate(frame, 0.5)
    """)
    assert client.eval("GuildSyncDB == nil")
    client.execute("""
        local frame = GaddHub.frame
        frame.scripts.OnEvent(frame, "PLAYER_EQUIPMENT_CHANGED")
        frame.scripts.OnUpdate(frame, 0.5)
    """)
    assert client.eval("GuildSyncDB == nil")
    client.execute("GaddHub.frame.scripts.OnUpdate(GaddHub.frame, 0.3)")
    assert client.eval("GaddHub.frame.scripts.OnUpdate == nil")
    assert len(read_export(export(client))) == 1
    client.execute("""
        TEST_TIMESTAMP = "2026-10-20T20:20:00Z"
        GaddHub.frame.scripts.OnEvent(GaddHub.frame, "PLAYER_LOGOUT")
    """)
    assert json.loads(read_export(export(client))[0][1])["captured_at"] == "2026-10-20T20:20:00Z"


def test_slash_commands_explain_memory_export_and_print_client_diagnostics(client):
    client.execute("SlashCmdList.GADDHUB('capture'); SlashCmdList.GADDHUB('diag')")
    messages = client.eval("table.concat(MESSAGES, '\\n')")
    assert "Use /reload or log out" in messages
    assert "build 70450, interface 16001" in messages
    assert "equipment: available" in messages


def test_export_runs_through_agent_queue_without_format_changes(client, tmp_path):
    snapshot(client)
    source = tmp_path / "GaddHub.lua"
    source.write_bytes(export(client))
    sent = []

    def sender(url, secret, content_hash, payload):
        sent.append((content_hash, payload))
        return UploadResult(True, "Test acknowledgement")

    settings = Settings(sources=[str(source)], stable_seconds=0.2)
    store = Store(tmp_path / "sync.sqlite3")
    try:
        engine = Engine(settings, "synthetic-test-password", store, lambda text: None, sender)
        engine.tick()
        engine.observed[str(source)].changed -= 1
        engine.tick()
        assert sent == read_export(source.read_bytes())
        assert store.status(settings.server_url)[2] is not None
        engine.tick()
        assert len(sent) == 1
    finally:
        store.close()
