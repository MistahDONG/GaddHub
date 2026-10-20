local A = GaddHub

A.collectors.talents = function()
    if not A.Has(GetNumTalentTabs, GetNumTalents, GetTalentInfo) then
        return A.Status("unsupported", "Classic talent-tab APIs unavailable; no build inferred.")
    end
    local count = GetNumTalentTabs()
    A.Require(A.Integer(count, 0, 10), "Unexpected talent tree count.")
    if count == 0 then return A.Status("not_collected", "Talent trees not ready.") end
    local trees = {}
    for tab = 1, count do
        local talents = {}
        local total = GetNumTalents(tab)
        A.Require(A.Integer(total, 1, 100), "Talent tree is incomplete or unsupported.")
        for index = 1, total do
            local name, _, tier, column, rank, maximum = GetTalentInfo(tab, index)
            A.Require(type(name) == "string" and A.Integer(tier, 1, 100)
                and A.Integer(column, 1, 10) and A.Integer(rank, 0, 100)
                and A.Integer(maximum, 1, 100) and rank <= maximum,
                "Unexpected Classic talent API result.")
            talents[#talents + 1] = {
                index = index, name = name, tier = tier, column = column,
                rank = rank, max_rank = maximum,
            }
        end
        trees[#trees + 1] = {index = tab, talents = talents}
    end
    return {status = "available", build = {system = "classic_tabs", trees = trees}}
end
