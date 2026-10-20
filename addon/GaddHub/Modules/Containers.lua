local A = GaddHub

function A.Containers(ids)
    local api = C_Container
    if type(api) ~= "table"
        or not A.Has(api.GetContainerNumSlots, api.GetContainerItemID, api.GetContainerItemInfo) then
        return A.Status("unsupported", "Structured C_Container APIs unavailable.")
    end
    local items = {}
    for containerIndex, bag in ipairs(ids) do
        local slots = api.GetContainerNumSlots(bag)
        A.Require(A.Integer(slots, 0, 1000), "Unexpected container size.")
        if containerIndex == 1 and slots == 0 then
            return A.Status("unavailable", "Main container data not ready; not treated as empty.")
        end
        for slot = 1, slots do
            local id = api.GetContainerItemID(bag, slot)
            local info = api.GetContainerItemInfo(bag, slot)
            if id ~= nil or info ~= nil then
                A.Require(A.Integer(id, 1, 2147483647) and type(info) == "table"
                    and A.Integer(info.stackCount, 1, 2147483647)
                    and (info.itemID == nil or info.itemID == id),
                    "Occupied container slot data not ready.")
                local item = {bag = bag, slot = slot, item_id = id, count = info.stackCount}
                if type(info.hyperlink) == "string" then item.link = info.hyperlink end
                items[#items + 1] = item
                A.Require(#items <= 10000, "Container item limit exceeded.")
            end
        end
    end
    return {status = "available", items = items}
end
