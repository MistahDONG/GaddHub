local A = GaddHub

A.collectors.equipment = function()
    if not A.Has(GetInventoryItemID, GetInventoryItemLink) then
        return A.Status("unsupported", "Equipment item ID/link APIs unavailable.")
    end
    local items = {}
    for slot = 1, 19 do
        local id = GetInventoryItemID("player", slot)
        local link = GetInventoryItemLink("player", slot)
        if id ~= nil or link ~= nil then
            A.Require(A.Integer(id, 1, 2147483647), "Unexpected equipped item ID.")
            A.Require(link == nil or type(link) == "string", "Unexpected equipment link.")
            local item = {slot = slot, item_id = id}
            if type(link) == "string" then item.link = link end
            items[#items + 1] = item
        end
    end
    return {status = "available", items = items}
end
