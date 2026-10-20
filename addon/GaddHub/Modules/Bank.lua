local A = GaddHub

A.collectors.bank = function()
    if not A.bankOpen then
        return A.Status("unavailable", "Bank is closed; contents were not inspected.")
    end
    if not A.Integer(BANK_CONTAINER, -10, -1)
        or not A.Integer(NUM_BAG_SLOTS, 0, 10) or not A.Integer(NUM_BANKBAGSLOTS, 0, 20) then
        return A.Status("unsupported", "Classic bank container constants unavailable.")
    end
    local ids = {BANK_CONTAINER}
    for bag = NUM_BAG_SLOTS + 1, NUM_BAG_SLOTS + NUM_BANKBAGSLOTS do
        ids[#ids + 1] = bag
    end
    return A.Containers(ids)
end
