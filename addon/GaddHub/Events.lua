local A = GaddHub
local frame = CreateFrame("Frame")
A.frame = frame

function A.Schedule(delay)
    A.remaining = delay or 0.75
    frame:SetScript("OnUpdate", function(_, elapsed)
        A.remaining = A.remaining - elapsed
        if A.remaining <= 0 then
            frame:SetScript("OnUpdate", nil)
            A.Capture()
        end
    end)
end

frame:SetScript("OnEvent", function(_, event, name)
    if event == "ADDON_LOADED" then
        if name == "GaddHub" then
            A.Message("Test addon " .. A.version .. " loaded. /gaddhub help")
        end
        return
    end
    if event == "UNIT_INVENTORY_CHANGED" and name ~= "player" then return end
    if event == "PLAYER_LOGOUT" then
        frame:SetScript("OnUpdate", nil)
        A.Capture()
        return
    end
    if event == "BANKFRAME_OPENED" then A.bankOpen = true end
    if event == "BANKFRAME_CLOSED" then A.bankOpen = false end
    if event == "TRADE_SKILL_SHOW" then A.tradeOpen = true end
    if event == "TRADE_SKILL_CLOSE" then A.tradeOpen = false end
    A.Schedule((event == "BANKFRAME_OPENED" or event == "TRADE_SKILL_SHOW") and 1.5 or 0.75)
end)

for _, event in ipairs({
    "ADDON_LOADED", "PLAYER_LOGIN", "PLAYER_ENTERING_WORLD", "PLAYER_LOGOUT",
    "PLAYER_EQUIPMENT_CHANGED", "CHARACTER_POINTS_CHANGED", "PLAYER_TALENT_UPDATE",
    "UNIT_INVENTORY_CHANGED", "SKILL_LINES_CHANGED", "BAG_UPDATE", "BAG_UPDATE_DELAYED",
    "BANKFRAME_OPENED", "BANKFRAME_CLOSED",
    "PLAYERBANKSLOTS_CHANGED", "TRADE_SKILL_SHOW", "TRADE_SKILL_CLOSE",
    "TRADE_SKILL_UPDATE", "GET_ITEM_INFO_RECEIVED", "PLAYER_LEVEL_UP",
}) do
    local ok = pcall(frame.RegisterEvent, frame, event)
    if not ok then A.Message("Event unsupported by this client: " .. event) end
end

SLASH_GADDHUB1 = "/gaddhub"
SlashCmdList.GADDHUB = function(message)
    local command = (message or ""):lower():match("^%s*(%S*)")
    if command == "capture" or command == "sync" then
        if A.Capture() then
            A.Message("Snapshot updated in memory. Use /reload or log out to write SavedVariables.")
        end
    elseif command == "status" or command == "diag" then
        A.Diagnostics()
    else
        A.Message("/gaddhub capture | status | diag")
        A.Message("No direct network/file access. The desktop agent reads SavedVariables after saving.")
    end
end
