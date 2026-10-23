/* Bleakhold Launcher: a fake backend for previewing the window in a browser. app.js loads this file only when
 * window.__TAURI__ is absent. It implements every command of DESIGN.md and emits its events.
 *
 * ?scenario=  demo (default: a full interactive run) | loading | first-run | install-dialog | install-existing |
 *             install-low | downloading | verifying | paused | update | ready | launching | playing | offline |
 *             offline-new | error | errors | settings | self-updating | no-news
 * &code=      error code for ?scenario=error (default game_running)
 * &realm=     partial (world server down) | offline
 * &warp=      download time warp (default 1, demo 40) */
(() => {
    "use strict";
    if (window.__TAURI__) {
        return;
    }

    const q = new URLSearchParams(location.search);
    const scenario = q.get("scenario") || "demo";
    const MB = 1024 * 1024;
    const GB = 1024 * MB;
    const log = (...a) => console.info("[mock]", ...a);
    const delay = (ms) => new Promise((r) => setTimeout(r, ms));
    const iso = (daysAgo) => {
        const d = new Date();
        d.setDate(d.getDate() - daysAgo);
        return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    };

    const NEWS = [
        {
            title: "Patch 1.4: The Frozen Vault opens",
            date: iso(0),
            body: "A new five-player dungeon beneath Icecrown, reworked class trainers, and the first Bleakhold mount vendor.",
            url: "https://bleakhold.com/news/patch-1-4",
        },
        {
            title: "Weekend event: Double reputation",
            date: iso(2),
            body: "From Friday to Sunday every reputation gain is doubled. The Argent Tournament grounds are open all weekend.",
            url: "https://bleakhold.com/news/double-rep",
        },
        {
            title: "Realm maintenance on Tuesday",
            date: iso(9),
            body: "The realm restarts at 06:00 server time for about thirty minutes while we move to faster hardware.",
            url: "https://bleakhold.com/news/maintenance",
        },
        {
            title: "Welcome to Bleakhold",
            date: iso(40),
            body: "A Wrath of the Lich King realm with a few surprises of its own. Read the guide for new adventurers.",
            url: "https://bleakhold.com/guide",
        },
    ];

    const FILES = [
        ["Wow.exe", 7.6 * MB], ["Data/common.MPQ", 2.71 * GB], ["Data/common-2.MPQ", 1.88 * GB],
        ["Data/expansion.MPQ", 1.71 * GB], ["Data/lichking.MPQ", 2.47 * GB], ["Data/patch.MPQ", 1.9 * GB],
        ["Data/patch-2.MPQ", 0.82 * GB], ["Data/patch-3.MPQ", 0.62 * GB], ["Data/enUS/locale-enUS.MPQ", 0.68 * GB],
        ["Data/enUS/expansion-locale-enUS.MPQ", 0.49 * GB], ["Data/enUS/lichking-locale-enUS.MPQ", 0.81 * GB],
        ["Data/enUS/patch-enUS.MPQ", 0.37 * GB], ["Data/enUS/patch-enUS-3.MPQ", 0.26 * GB],
        ["Data/patch-B.MPQ", 1.21 * GB], ["Data/enUS/patch-enUS-B.MPQ", 0.21 * GB],
    ];

    const FULL = Math.round(FILES.reduce((sum, f) => sum + f[1], 0));
    const HD = Math.round(19.8 * GB);

    const listeners = {};
    const emit = (event, payload) => (listeners[event] || []).slice().forEach((cb) => cb({ event, payload }));

    const state = {
        launcher_version: "1.2.0",
        phase: "loading",
        message: "",
        installed: true,
        install_dir: "C:\\Games\\Bleakhold",
        settings: { parallel: 4, limit_mbps: 0, close_on_play: true, packs: {} },
        build: "2026-10-23 16:00 c74f1eb",
        total_bytes: FULL,
        pending_bytes: 0,
        news: NEWS,
        links: { register: "https://bleakhold.com/register", website: "https://bleakhold.com", discord: "https://discord.gg/bleakhold" },
        server: { name: "Bleakhold", online: true, auth: true, world: true, ping_ms: 41 },
        packs: [{ id: "hd", name: "HD graphics", about: "Reforged's HD models and textures, with Bleakhold's Patch-Y",
            bytes: HD, on: true }],
    };
    state.total_bytes = FULL + HD;

    const preview = { scenario, open: null };
    window.__BLEAKHOLD_MOCK__ = preview;

    function setPhase(phase, message = "") {
        state.phase = phase;
        state.message = message;
        emit("phase", { phase, message });
    }

    // ------------------------------------------------------------------------------- download sim

    const job = { timer: 0, done: 0, total: 0, mode: "download", files: [], speed: 22 * MB, after: null };
    const warp = parseFloat(q.get("warp")) || (scenario === "demo" ? 40 : 1);
    let noise = 0;

    function fileAt(done) {
        let acc = 0;
        for (let i = 0; i < job.files.length; i++) {
            acc += job.files[i][1];
            if (done < acc) {
                return [i, job.files[i][0]];
            }
        }
        return [job.files.length - 1, job.files[job.files.length - 1][0]];
    }

    function emitProgress(speed) {
        const [i, file] = fileAt(job.done);
        emit("progress", {
            done_bytes: Math.round(job.done),
            total_bytes: Math.round(job.total),
            speed_bps: Math.round(speed),
            eta_s: speed > 0 ? Math.round((job.total - job.done) / speed) : null,
            file,
            files_done: job.mode === "verify" ? Math.floor((job.done / job.total) * 3876) : i,
            files_total: job.mode === "verify" ? 3876 : job.files.length,
        });
    }

    function tick() {
        noise = noise * 0.8 + (Math.random() - 0.5) * 0.4;
        const limit = state.settings.limit_mbps > 0 ? state.settings.limit_mbps * MB : Infinity;
        const base = job.mode === "verify" ? 380 * MB : job.speed * (0.6 + state.settings.parallel * 0.1);
        const speed = Math.max(0.3 * MB, Math.min(limit, base * (1 + noise)));
        job.done = Math.min(job.total, job.done + speed * 0.25 * warp);
        emitProgress(speed);
        if (job.done >= job.total) {
            stopJob();
            const after = job.after;
            job.after = null;
            if (after) {
                after();
            }
        }
    }

    function startJob(mode, files, startAt, after) {
        stopJob();
        job.mode = mode;
        job.files = files;
        job.total = files.reduce((a, f) => a + f[1], 0);
        job.done = Math.min(job.total, startAt || 0);
        job.after = after;
        setPhase(mode === "verify" ? "verifying" : "downloading");
        emitProgress(mode === "verify" ? 380 * MB : job.speed);
        job.timer = setInterval(tick, 250);
    }

    function stopJob() {
        clearInterval(job.timer);
        job.timer = 0;
    }

    function finishInstall() {
        state.installed = true;
        state.pending_bytes = 0;
        startJob("verify", FILES.map(([p, s]) => [p, s]), 0, () => setPhase("ready"));
    }

    function updateFiles() {
        return [["Data/patch-B.MPQ", 1.04 * GB], ["Data/enUS/patch-enUS-B.MPQ", 0.21 * GB], ["Wow.exe", 7.6 * MB]];
    }

    // ---------------------------------------------------------------------------------- folders

    const FOLDERS = ["D:\\Games\\Bleakhold", "D:\\World of Warcraft 3.3.5a", "C:\\Program Files\\Bleakhold", "E:\\Bleakhold"];
    let folderIndex = 0;

    function folderInfo(path) {
        const p = String(path || "");
        if (/world of warcraft/i.test(p)) {
            return { path: p, free_bytes: 88.4 * GB, needed_bytes: 2.35 * GB, has_game: true, writable: true };
        }
        if (/^c:\\program files/i.test(p)) {
            return { path: p, free_bytes: 214.6 * GB, needed_bytes: FULL, has_game: false, writable: false };
        }
        if (/^e:/i.test(p)) {
            return { path: p, free_bytes: 9.8 * GB, needed_bytes: FULL, has_game: false, writable: true };
        }
        return { path: p, free_bytes: 214.6 * GB, needed_bytes: state.total_bytes, has_game: false, writable: true };
    }

    // --------------------------------------------------------------------------------- commands

    let started = false;

    const commands = {
        get_state() {
            if (!started) {
                started = true;
                setTimeout(kickOff, 0);
            }
            return JSON.parse(JSON.stringify(state));
        },
        choose_folder() {
            const path = FOLDERS[folderIndex++ % FOLDERS.length];
            log("choose_folder ->", path);
            return path;
        },
        folder_info({ path }) {
            return delay(350).then(() => folderInfo(path));
        },
        install({ path, desktop_shortcut, start_menu }) {
            log("install", { path, desktop_shortcut, start_menu });
            state.install_dir = path;
            const info = folderInfo(path);
            const files = info.has_game ? updateFiles().concat([["Data/enUS/patch-enUS-3.MPQ", 0.26 * GB]]) : FILES;
            state.pending_bytes = files.reduce((a, f) => a + f[1], 0);
            setTimeout(() => startJob("download", files, 0, finishInstall), 300);
        },
        check() {
            setPhase("loading");
            setTimeout(() => {
                state.server.online = true;
                state.server.auth = state.server.world = true;
                state.news = NEWS;
                emit("server", { online: true, auth: true, world: true, ping_ms: 44 });
                setPhase(state.installed ? (state.pending_bytes > 0 ? "needs_update" : "ready") : "needs_install");
            }, 1100);
        },
        update() {
            const files = updateFiles();
            startJob("download", files, 0, () => {
                state.pending_bytes = 0;
                setPhase("ready");
            });
        },
        pause() {
            stopJob();
            setPhase("paused");
            emitProgress(0);
        },
        resume() {
            if (!job.files.length) {
                job.files = FILES;
                job.total = FILES.reduce((a, f) => a + f[1], 0);
                job.done = job.total * 0.63;
                job.after = finishInstall;
            }
            setPhase("downloading");
            job.timer = setInterval(tick, 250);
        },
        cancel() {
            stopJob();
            job.files = [];
            setPhase(state.installed ? "needs_update" : "needs_install");
        },
        repair() {
            startJob("verify", FILES, 0, () => setPhase("ready"));
        },
        play() {
            setPhase("launching");
            setTimeout(() => setPhase("playing"), 1600);
            setTimeout(() => setPhase("ready"), 12000);
        },
        save_settings({ settings }) {
            log("save_settings", settings);
            Object.assign(state.settings, settings, { packs: Object.assign({}, state.settings.packs, settings.packs) });
            state.packs.forEach((p) => {
                if (settings.packs && typeof settings.packs[p.id] === "boolean") {
                    p.on = settings.packs[p.id];
                }
            });
            state.total_bytes = FULL + state.packs.reduce((a, p) => a + (p.on ? p.bytes : 0), 0);
            if (state.phase === "needs_install") {
                state.pending_bytes = state.total_bytes;
            }
        },
        open_folder() {
            log("open_folder", state.install_dir);
        },
        open_url({ url }) {
            log("open_url", url);
        },
        clear_cache() {
            log("clear_cache");
            return delay(300);
        },
        minimize() {
            log("minimize");
        },
        close() {
            log("close");
        },
    };

    // -------------------------------------------------------------------------------- scenarios

    function setup() {
        switch (scenario) {
        case "loading":
            break;
        case "first-run":
        case "install-dialog":
        case "install-existing":
        case "install-low":
        case "offline-new":
            state.installed = false;
            state.phase = scenario === "offline-new" ? "offline" : "needs_install";
            state.install_dir = { "install-existing": "D:\\World of Warcraft 3.3.5a", "install-low": "E:\\Bleakhold" }[scenario]
                || "C:\\Games\\Bleakhold";
            state.pending_bytes = FULL;
            if (scenario.startsWith("install")) {
                preview.open = "install";
            }
            if (scenario === "offline-new") {
                state.news = [];
                state.server = { name: "Bleakhold", online: false, auth: false, world: false, ping_ms: null };
            }
            break;
        case "downloading":
        case "paused":
            state.installed = q.get("installed") === "1";
            state.phase = "downloading";
            break;
        case "verifying":
            state.phase = "verifying";
            break;
        case "update":
            state.phase = "needs_update";
            state.pending_bytes = Math.round(1.26 * GB);
            break;
        case "launching":
            state.phase = "launching";
            break;
        case "playing":
            state.phase = "playing";
            break;
        case "offline":
            state.phase = "offline";
            state.news = [];
            state.server = { name: "Bleakhold", online: false, auth: false, world: false, ping_ms: null };
            break;
        case "error":
        case "errors":
            state.phase = "error";
            state.message = "Data/patch-B.MPQ is in use by another process (os error 32)";
            break;
        case "settings":
            state.phase = "ready";
            state.settings = { parallel: 6, limit_mbps: 0, close_on_play: true };
            preview.open = "settings";
            break;
        case "self-updating":
            state.phase = "self_updating";
            state.message = "Bleakhold Launcher 1.1.0 is out. It restarts by itself in a moment.";
            break;
        case "no-news":
            state.phase = "ready";
            state.news = [];
            break;
        case "ready":
            state.phase = "ready";
            break;
        default: // demo
            state.installed = false;
            state.install_dir = "C:\\Games\\Bleakhold";
            state.pending_bytes = FULL;
            state.phase = "loading";
        }
    }

    // Runs once the window has subscribed and read its first State.
    function kickOff() {
        switch (scenario) {
        case "demo":
            setTimeout(() => setPhase("needs_install"), 1400);
            break;
        case "downloading":
            startJob("download", FILES, FULL * 0.42, finishInstall);
            break;
        case "paused":
            startJob("download", FILES, FULL * 0.63, finishInstall);
            commands.pause();
            break;
        case "verifying":
            startJob("verify", FILES, FULL * 0.36, () => setPhase("ready"));
            break;
        case "self-updating": {
            let done = 0;
            const total = 8.12 * MB;
            const t = setInterval(() => {
                done = Math.min(total, done + 0.21 * MB);
                emit("progress", {
                    done_bytes: done, total_bytes: total, speed_bps: 0.84 * MB, eta_s: (total - done) / (0.84 * MB),
                    file: "BleakholdLauncher.exe", files_done: 0, files_total: 1,
                });
                if (done >= total * 0.7) {
                    clearInterval(t);
                }
            }, 250);
            break;
        }
        case "error":
            emit("error", { code: q.get("code") || "game_running", message: state.message });
            break;
        case "errors": {
            const codes = ["network", "disk_full", "game_running"];
            codes.forEach((code, i) => setTimeout(() => emit("error", { code, message: "" }), i * 120));
            break;
        }
        default:
            break;
        }
        if (scenario !== "offline" && scenario !== "offline-new" && !q.get("realm")) {
            setInterval(() => {
                emit("server", {
                    online: true, auth: true, world: true, ping_ms: Math.round(38 + Math.random() * 14),
                });
            }, 5000);
        }
    }

    setup();
    if (q.get("realm") === "partial") {
        state.server = { name: "Bleakhold", online: true, auth: true, world: false, ping_ms: 63 };
    } else if (q.get("realm") === "offline") {
        state.server = { name: "Bleakhold", online: false, auth: false, world: false, ping_ms: null };
    }

    window.__TAURI__ = {
        core: {
            async invoke(cmd, args) {
                const fn = commands[cmd];
                if (!fn) {
                    throw new Error(`unknown command: ${cmd}`);
                }
                await delay(40 + Math.random() * 60);
                return fn(args || {});
            },
        },
        event: {
            async listen(event, cb) {
                (listeners[event] = listeners[event] || []).push(cb);
                return () => {
                    listeners[event] = (listeners[event] || []).filter((f) => f !== cb);
                };
            },
        },
    };
    log("scenario:", scenario);
})();
