-- SYNTHETIC TEST DATA. Not exported from or verified against WoW Forever.
GuildSyncDB = {
    ["schema_version"] = 1,
    ["snapshots"] = {
        {
            ["schema_version"] = 1,
            ["addon_version"] = "0.1.0",
            ["character"] = {
                ["character_id"] = "synthetic:example-realm:example",
                ["name"] = "Example",
                ["realm"] = "Example Realm",
                ["class"] = "Example Class",
                ["level"] = 60,
            },
            ["captured_at"] = "2026-10-20T12:00:00Z",
            ["sections"] = {
                ["equipment"] = {
                    ["status"] = "available",
                    ["items"] = {
                        { ["slot_id"] = 1, ["item_id"] = 12345, },
                    },
                },
                ["talents"] = {
                    ["status"] = "available",
                    ["build"] = {},
                },
                ["professions"] = { ["status"] = "not_collected", },
                ["inventory"] = { ["status"] = "not_collected", },
                ["bank"] = { ["status"] = "unavailable", },
                ["recipes"] = { ["status"] = "unsupported", },
            },
        },
    },
}
