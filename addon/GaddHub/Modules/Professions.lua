local A = GaddHub

A.collectors.professions = function()
    if not A.Has(GetProfessions, GetProfessionInfo) then
        return A.Status("unsupported",
            "Profession APIs unavailable; a Classic skill-line adapter needs client verification.")
    end
    local items = {}
    local indices = {GetProfessions()}
    -- GetProfessions may have nil holes, so ipairs would omit secondary professions.
    for position = 1, 6 do
        local index = indices[position]
        if index ~= nil then
            local name, _, rank, maximum, _, _, skillLine = GetProfessionInfo(index)
            A.Require(type(name) == "string" and A.Integer(rank, 0, 10000)
                and A.Integer(maximum, 1, 10000) and A.Integer(skillLine, 1, 2147483647),
                "Unexpected profession API result.")
            items[#items + 1] = {
                name = name, skill_line_id = skillLine, rank = rank, max_rank = maximum,
            }
        end
    end
    return {status = "available", items = items}
end
