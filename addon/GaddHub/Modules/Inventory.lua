local A = GaddHub

A.collectors.inventory = function()
    if not A.Integer(NUM_BAG_SLOTS, 0, 10) then
        return A.Status("unsupported", "Client bag-slot count unavailable.")
    end
    local ids = {0}
    for bag = 1, NUM_BAG_SLOTS do ids[#ids + 1] = bag end
    return A.Containers(ids)
end
