test("addon loads and sends HELLO on entering the world", function(M, ns)
    M.Advance(0.5)
    local it = H.lastIntent(M, "HELLO")
    H.ok(it, "HELLO sent")
    H.eq(it.fields[1], "1")
end)

test("every TOC file loaded", function(M, ns)
    H.ok(#M.loaded >= 19, "files loaded: " .. #M.loaded)
end)

test("demo opens all windows without errors", function(M, ns)
    M.env.SlashCmdList.BLEAKHOLD("demo")
    M.Advance(2)
    for _, k in ipairs({ "tasks", "dungeons", "keys", "rift", "collections", "season", "leaderboards" }) do
        ns.UI.Open(k)
        M.Advance(1)
    end
end)
