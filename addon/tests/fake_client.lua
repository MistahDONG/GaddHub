MESSAGES = {}
TEST_TIMESTAMP = "2026-10-20T20:00:00Z"
TEST_GUID = "Player-Test-1"
function print(text) MESSAGES[#MESSAGES + 1] = text end
function GetBuildInfo() return "1.60.1", "70450", "Oct 15 2026", 16001, "", " " end
function UnitGUID() return TEST_GUID end
function UnitName() return "Gäddkrigaren" end
function GetRealmName() return "Test Realm" end
function UnitClass() return "Warrior", "WARRIOR" end
function UnitRace() return "Human", "Human" end
function UnitFactionGroup() return "Alliance" end
function UnitLevel() return 60 end
function GetServerTime() return 1792526400 end
function date(format, timestamp)
    assert(format == "!%Y-%m-%dT%H:%M:%SZ" and type(timestamp) == "number")
    return TEST_TIMESTAMP
end
function GetInventoryItemID(unit, slot)
    assert(unit == "player")
    if slot == 16 then return 123 end
end
function GetInventoryItemLink(unit, slot)
    if slot == 16 then return "|cff0070dd|Hitem:123:0:0:0|h[Test Sword]|h|r" end
end
function GetNumTalentTabs() return 1 end
function GetNumTalents(tab) assert(tab == 1); return 2 end
function GetTalentInfo(tab, index)
    return "Talent " .. index, 42, index, 1, index == 1 and 2 or 0, 5
end
function GetProfessions() return nil, nil, nil, nil, 7 end
function GetProfessionInfo(index)
    assert(index == 7)
    return "Fishing", 42, 75, 150, 1, 0, 356
end
NUM_BAG_SLOTS = 4
NUM_BANKBAGSLOTS = 6
BANK_CONTAINER = -1
C_Container = {}
function C_Container.GetContainerNumSlots(bag)
    return (bag == 0 or bag == -1) and 3 or 0
end
function C_Container.GetContainerItemID(bag, slot)
    if (bag == 0 or bag == -1) and slot == 1 then return 456 end
end
function C_Container.GetContainerItemInfo(bag, slot)
    if C_Container.GetContainerItemID(bag, slot) then
        return {itemID = 456, stackCount = 3, hyperlink = "|Hitem:456|h[Test Material]|h"}
    end
end
C_TradeSkillUI = {}
function C_TradeSkillUI.IsTradeSkillLinked() return false end
function C_TradeSkillUI.IsTradeSkillGuild() return false end
function C_TradeSkillUI.GetAllRecipeIDs() return {10, 20} end
function C_TradeSkillUI.GetRecipeInfo(id)
    return {recipeID = id, name = "Recipe " .. id, learned = id == 10}
end
SlashCmdList = {}
function CreateFrame()
    local frame = {scripts = {}, events = {}}
    function frame:SetScript(name, callback) self.scripts[name] = callback end
    function frame:RegisterEvent(name) self.events[name] = true end
    return frame
end
function TestClone(value)
    if type(value) ~= "table" then return value end
    local result = {}
    for key, child in pairs(value) do result[key] = TestClone(child) end
    return result
end
function TestSerialize(value, seen)
    local kind = type(value)
    if kind == "string" then return string.format("%q", value) end
    if kind == "number" or kind == "boolean" then return tostring(value) end
    assert(kind == "table", "Non-data value in SavedVariables")
    seen = seen or {}
    assert(not seen[value], "Shared/cyclic table in SavedVariables")
    seen[value] = true
    local fields = {}
    for key, child in pairs(value) do
        fields[#fields + 1] = "[" .. TestSerialize(key, seen) .. "]="
            .. TestSerialize(child, seen) .. ","
    end
    table.sort(fields)
    return "{" .. table.concat(fields) .. "}"
end
