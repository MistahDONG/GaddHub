local A = GaddHub

A.collectors.recipes = function()
    if not A.tradeOpen then
        return A.Status("not_collected", "Open your profession window to collect recipes.")
    end
    local api = C_TradeSkillUI
    if type(api) ~= "table"
        or not A.Has(api.GetAllRecipeIDs, api.GetRecipeInfo, api.IsTradeSkillLinked,
            api.IsTradeSkillGuild) then
        return A.Status("unsupported",
            "Complete recipe enumeration unavailable; visible legacy rows are not a full recipe list.")
    end
    if api.IsTradeSkillLinked() or api.IsTradeSkillGuild() then
        return A.Status("unavailable", "Linked/guild recipes are not this character's recipes.")
    end
    local ids = api.GetAllRecipeIDs()
    A.Require(type(ids) == "table", "Recipe list not ready.")
    if #ids == 0 then return A.Status("not_collected", "Recipe list not ready.") end
    A.Require(#ids <= 10000, "Recipe limit exceeded.")
    local items = {}
    for _, id in ipairs(ids) do
        local info = api.GetRecipeInfo(id)
        A.Require(A.Integer(id, 1, 2147483647) and type(info) == "table"
            and type(info.learned) == "boolean", "Recipe details not ready.")
        if info.learned then
            A.Require(type(info.name) == "string", "Recipe name not ready.")
            items[#items + 1] = {recipe_id = id, name = info.name}
        end
    end
    return {status = "available", items = items,
        reason = "Known recipes for the currently open profession only."}
end
