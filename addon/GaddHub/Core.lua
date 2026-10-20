GaddHub = {
    version = "0.1.0",
    collectors = {},
    sectionNames = {"equipment", "talents", "professions", "inventory", "bank", "recipes"},
    bankOpen = false,
    tradeOpen = false,
    errors = {},
}
local A = GaddHub

function A.Message(text)
    print("|cff20bfa9GaddHub:|r " .. text)
end

function A.Integer(value, minimum, maximum)
    return type(value) == "number" and value == math.floor(value)
        and value >= minimum and value <= maximum
end

function A.Require(condition, message)
    if not condition then error(message, 0) end
end

function A.Status(status, reason)
    return {status = status, reason = reason}
end

function A.ErrorReason(value)
    local text = tostring(value)
    if #text <= 512 then return text end
    local length = 509
    -- Lua indexes bytes; do not split a UTF-8 character when bounding diagnostics.
    while length > 0 do
        local nextByte = text:byte(length + 1)
        if not nextByte or nextByte < 128 or nextByte >= 192 then break end
        length = length - 1
    end
    return text:sub(1, length) .. "..."
end

function A.Has(...)
    for index = 1, select("#", ...) do
        if type(select(index, ...)) ~= "function" then return false end
    end
    return true
end

function A.Timestamp()
    A.Require(A.Has(date), "UTC date API unavailable.")
    local clock = GetServerTime or time
    A.Require(A.Has(clock), "Epoch clock API unavailable.")
    local timestamp = date("!%Y-%m-%dT%H:%M:%SZ", clock())
    A.Require(type(timestamp) == "string"
        and timestamp:match("^%d%d%d%d%-%d%d%-%d%dT%d%d:%d%d:%d%dZ$"),
        "UTC timestamp API returned an unexpected format.")
    return timestamp
end

function A.Character()
    A.Require(A.Has(UnitGUID, UnitName, GetRealmName, UnitClass, UnitLevel),
        "Required character APIs unavailable; no invented character ID will be exported.")
    local _, class = UnitClass("player")
    local character = {
        character_id = UnitGUID("player"),
        name = UnitName("player"),
        realm = GetRealmName(),
        class = class,
        level = UnitLevel("player"),
    }
    for _, key in ipairs({"character_id", "name", "realm", "class"}) do
        A.Require(type(character[key]) == "string" and #character[key] > 0,
            "Character identity not ready: " .. key)
    end
    A.Require(A.Integer(character.level, 1, 1000), "Character level not ready.")
    if A.Has(UnitRace) then
        local _, race = UnitRace("player")
        if type(race) == "string" then character.race = race end
    end
    if A.Has(UnitFactionGroup) then
        local faction = UnitFactionGroup("player")
        if type(faction) == "string" then character.faction = faction end
    end
    return character
end

function A.Database()
    if GuildSyncDB == nil then GuildSyncDB = {schema_version = 1, snapshots = {}} end
    A.Require(type(GuildSyncDB) == "table" and GuildSyncDB.schema_version == 1
        and type(GuildSyncDB.snapshots) == "table",
        "Existing GuildSyncDB has an unsupported format; it was not overwritten.")
    for key in pairs(GuildSyncDB) do
        A.Require(key == "schema_version" or key == "snapshots",
            "Existing GuildSyncDB has unknown fields; it was not overwritten.")
    end
    local count = 0
    for index, snapshot in pairs(GuildSyncDB.snapshots) do
        count = count + 1
        A.Require(A.Integer(index, 1, 100) and type(snapshot) == "table"
            and snapshot.schema_version == 1 and type(snapshot.character) == "table"
            and type(snapshot.character.character_id) == "string"
            and type(snapshot.captured_at) == "string" and type(snapshot.sections) == "table",
            "Existing snapshots have an unsupported format; they were not overwritten.")
    end
    A.Require(count == #GuildSyncDB.snapshots, "Existing snapshots are not a dense array.")
    return GuildSyncDB
end

function A.Store(snapshot)
    local database = A.Database()
    local characters = {}
    local function consider(candidate, newest)
        local id = candidate.character.character_id
        local group = characters[id] or {}
        characters[id] = group
        if newest or not group.latest or candidate.captured_at > group.latest.captured_at then
            group.latest = candidate
        end
        for _, section in ipairs({"bank", "recipes"}) do
            local data = candidate.sections[section]
            if data and data.status == "available"
                and (newest or not group[section]
                    or candidate.captured_at > group[section].captured_at) then
                group[section] = candidate
            end
        end
    end
    for _, previous in ipairs(database.snapshots) do consider(previous, false) end
    consider(snapshot, true)
    local ids, snapshots, included = {}, {}, {}
    for id in pairs(characters) do ids[#ids + 1] = id end
    table.sort(ids)
    for _, id in ipairs(ids) do
        local group = characters[id]
        -- Keep situational observations with their original timestamp, not as fresh data.
        for _, key in ipairs({"latest", "bank", "recipes"}) do
            local candidate = group[key]
            if candidate and not included[candidate] then
                snapshots[#snapshots + 1] = candidate
                included[candidate] = true
            end
        end
    end
    A.Require(#snapshots <= 100,
        "Export capacity reached (100 snapshots); existing data was not overwritten.")
    database.snapshots = snapshots
end

local validStatuses = {
    available = true, not_collected = true, unavailable = true, unsupported = true, error = true,
}

function A.Collect(name)
    local collector = A.collectors[name]
    if not collector then return A.Status("unsupported", "Collector not installed.") end
    local ok, section = pcall(collector)
    if not ok then section = A.Status("error", A.ErrorReason(section)) end
    if type(section) ~= "table" or not validStatuses[section.status] then
        section = A.Status("error", "Collector returned an invalid result.")
    end
    if section.status == "error" and A.errors[name] ~= section.reason then
        A.Message(name .. ": " .. section.reason)
    end
    A.errors[name] = section.status == "error" and section.reason or nil
    return section
end

function A.Capture()
    local ok, result = pcall(function()
        local snapshot = {
            schema_version = 1,
            addon_version = A.version,
            character = A.Character(),
            captured_at = A.Timestamp(),
            sections = {},
        }
        for _, name in ipairs(A.sectionNames) do snapshot.sections[name] = A.Collect(name) end
        A.Store(snapshot)
        return snapshot
    end)
    if not ok then
        local reason = A.ErrorReason(result)
        if A.lastError ~= reason then A.Message("Capture failed: " .. reason) end
        A.lastError = reason
        return false
    end
    A.lastError = nil
    A.lastSnapshot = result
    return true
end

function A.Diagnostics()
    if A.Has(GetBuildInfo) then
        local version, build, _, interface = GetBuildInfo()
        A.Message("Client " .. tostring(version) .. ", build " .. tostring(build)
            .. ", interface " .. tostring(interface) .. "; addon " .. A.version)
    end
    for _, name in ipairs({
        "UnitGUID", "GetInventoryItemID", "GetNumTalentTabs", "GetTalentInfo",
        "GetProfessions", "GetProfessionInfo", "GetNumTradeSkills", "GetTradeSkillInfo",
        "GetNumSkillLines", "GetSkillLineInfo",
    }) do
        A.Message(name .. ": " .. type(_G[name]))
    end
    for namespace, methods in pairs({
        C_Container = {"GetContainerNumSlots", "GetContainerItemID", "GetContainerItemInfo"},
        C_TradeSkillUI = {"GetAllRecipeIDs", "GetRecipeInfo", "IsTradeSkillLinked", "IsTradeSkillGuild"},
    }) do
        local api = _G[namespace]
        for _, method in ipairs(methods) do
            A.Message(namespace .. "." .. method .. ": "
                .. (type(api) == "table" and type(api[method]) or "unavailable"))
        end
    end
    if A.lastError then A.Message("Last capture error: " .. A.lastError) end
    local snapshot = A.lastSnapshot
    if snapshot then
        A.Message(snapshot.character.name .. " - " .. snapshot.character.realm
            .. ", collected " .. snapshot.captured_at)
        for _, name in ipairs(A.sectionNames) do
            local section = snapshot.sections[name]
            A.Message(name .. ": " .. section.status
                .. (section.reason and (" - " .. section.reason) or ""))
        end
    else
        A.Message("No snapshot captured this session.")
    end
end
