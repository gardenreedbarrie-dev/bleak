/* Bleakhold Launcher: the window's logic. It talks to the backend only through the commands, events, State and
 * phases of Tools/Launcher/DESIGN.md (window.__TAURI__.core.invoke / window.__TAURI__.event.listen). When the page
 * is opened in a plain browser, mock.js stands in for the backend. Vanilla JS, no build step, no inline code
 * (the CSP is self-only), and backend text only ever goes through textContent. */
(() => {
    "use strict";

    // ------------------------------------------------------------------------------------------- icons

    const GEAR = "M9.93 5L10.07 2.49L13.93 2.49L14.07 5A7.3 7.3 0 0 1 15.48 5.58L17.35 3.91L20.09 6.65L18.42 8.52" +
        "A7.3 7.3 0 0 1 19 9.93L21.51 10.07L21.51 13.93L19 14.07A7.3 7.3 0 0 1 18.42 15.48L20.09 17.35L17.35 20.09" +
        "L15.48 18.42A7.3 7.3 0 0 1 14.07 19L13.93 21.51L10.07 21.51L9.93 19A7.3 7.3 0 0 1 8.52 18.42L6.65 20.09" +
        "L3.91 17.35L5.58 15.48A7.3 7.3 0 0 1 5 14.07L2.49 13.93L2.49 10.07L5 9.93A7.3 7.3 0 0 1 5.58 8.52L3.91 6.65" +
        "L6.65 3.91L8.52 5.58A7.3 7.3 0 0 1 9.93 5Z";

    const ICONS = {
        minimize: '<path d="M6 12h12"/>',
        close: '<path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/>',
        settings: `<path d="${GEAR}"/><circle cx="12" cy="12" r="3"/>`,
        folder: '<path d="M3.5 7.5a2 2 0 0 1 2-2h3.8l2.2 2.3h7a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z"/>',
        repair: '<path d="M12 3.2l7 2.7v5.3c0 4.3-2.9 7.9-7 9.6-4.1-1.7-7-5.3-7-9.6V5.9z"/><path d="M8.9 12.1l2.2 2.2 4.1-4.4"/>',
        globe: '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.3 2.3 3.5 5.2 3.5 8.5s-1.2 6.2-3.5 8.5c-2.3-2.3-3.5-5.2-3.5-8.5s1.2-6.2 3.5-8.5z"/>',
        chat: '<path d="M5.2 5.5h13.6c.9 0 1.7.8 1.7 1.7v8.1c0 .9-.8 1.7-1.7 1.7h-8.3L6 20.3V17h-.8c-.9 0-1.7-.8-1.7-1.7V7.2c0-.9.8-1.7 1.7-1.7z"/><path d="M8.6 11.3h.01M12 11.3h.01M15.4 11.3h.01" stroke-width="2.6"/>',
        user: '<circle cx="10" cy="8.5" r="3.5"/><path d="M3.8 19.5c.8-3.3 3.3-5.4 6.2-5.4s5.4 2.1 6.2 5.4M18.5 8v6M15.5 11h6"/>',
        pause: '<path d="M9 6.5v11M15 6.5v11" stroke-width="2.4"/>',
        play: '<path d="M8.5 6.2v11.6L18 12z" fill="currentColor" stroke-width="1.4"/>',
        stop: '<rect x="7" y="7" width="10" height="10" rx="1.6"/>',
        arrow: '<path d="M5 12h13M13.5 7.5L18 12l-4.5 4.5"/>',
        check: '<path d="M5.5 12.5l4 4 9-9" stroke-width="2.2"/>',
        alert: '<path d="M12 4.2l8.6 15.3H3.4z"/><path d="M12 10.2v4.2M12 17.1h.01" stroke-width="2.2"/>',
        error: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.8v5M12 16.2h.01" stroke-width="2.2"/>',
        info: '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5M12 7.8h.01" stroke-width="2.2"/>',
        offline: '<path d="M3.5 3.5l17 17"/><path d="M8.6 16.2a5 5 0 0 1 6.2-.6M5.2 12.8a9.8 9.8 0 0 1 4.3-2.4M18.8 12.8a9.9 9.9 0 0 0-2.4-1.7M2 9.4a14.9 14.9 0 0 1 4-2.7M22 9.4a14.9 14.9 0 0 0-11.4-3.8M12 19.6h.01" />',
        download: '<path d="M12 4v11M7.5 10.5L12 15l4.5-4.5M5 19.5h14"/>',
        news: '<rect x="4" y="5" width="16" height="14" rx="2"/><path d="M8 9.2h8M8 12.5h8M8 15.8h5"/>',
        spark: '<path d="M12 3.5l1.9 5.4 5.6 2.1-5.6 2.1L12 18.5l-1.9-5.4L4.5 11l5.6-2.1z"/>',
    };

    function icon(name) {
        return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" ' +
            'stroke-linejoin="round" aria-hidden="true">' + (ICONS[name] || "") + "</svg>";
    }

    function injectIcons(root) {
        root.querySelectorAll("[data-icon]").forEach((node) => {
            node.innerHTML = icon(node.dataset.icon);
        });
    }

    // --------------------------------------------------------------------------------------- utilities

    const $ = (id) => document.getElementById(id);
    const app = $("app");

    // The window is designed at 1180x700. If the app has to open it smaller (a small screen or a high
    // scaling factor), the whole layout scales down instead of clipping.
    const DESIGN_W = 1180;
    const DESIGN_H = 700;
    let uiScale = 1;

    function fitWindow() {
        const s = Math.min(window.innerWidth / DESIGN_W, window.innerHeight / DESIGN_H);
        uiScale = s < 0.995 ? s : 1;
        app.classList.toggle("is-scaled", uiScale < 1);
        app.style.transform = uiScale < 1 ? `scale(${uiScale})` : "";
    }

    function el(tag, className, text) {
        const node = document.createElement(tag);
        if (className) {
            node.className = className;
        }
        if (text != null) {
            node.textContent = text;
        }
        return node;
    }

    function debounce(fn, ms) {
        let t = 0;
        return (...args) => {
            clearTimeout(t);
            t = setTimeout(() => fn(...args), ms);
        };
    }

    const isHttp = (url) => typeof url === "string" && /^https?:\/\//i.test(url);
    const num = (v) => (typeof v === "number" && Number.isFinite(v) ? v : null);

    // ------------------------------------------------------------------------------------- formatting

    const KB = 1024;
    const MB = KB * 1024;
    const GB = MB * 1024;
    const TB = GB * 1024;

    function fmtBytes(n) {
        n = num(n);
        if (n == null || n < 0) {
            return "–";
        }
        if (n >= TB) {
            return (n / TB).toFixed(1) + " TB";
        }
        if (n >= GB) {
            return (n / GB).toFixed(1) + " GB";
        }
        if (n >= MB) {
            return (n >= 100 * MB ? Math.round(n / MB) : (n / MB).toFixed(1)) + " MB";
        }
        if (n >= KB) {
            return Math.round(n / KB) + " KB";
        }
        return Math.round(n) + " B";
    }

    function fmtSpeed(bps) {
        bps = num(bps);
        if (bps == null || bps <= 0) {
            return "";
        }
        if (bps >= MB) {
            return (bps >= 100 * MB ? Math.round(bps / MB) : (bps / MB).toFixed(1)) + " MB/s";
        }
        return Math.max(1, Math.round(bps / KB)) + " KB/s";
    }

    function fmtEta(s) {
        s = num(s);
        if (s == null || s < 0) {
            return "";
        }
        if (s < 50) {
            return "less than a minute left";
        }
        const min = Math.round(s / 60);
        if (min < 60) {
            return min + " min left";
        }
        const h = Math.floor(min / 60);
        const m = min % 60;
        return m ? `${h} h ${m} min left` : `${h} h left`;
    }

    const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

    function parseDate(str) {
        if (typeof str !== "string") {
            return null;
        }
        const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(str);
        const d = m ? new Date(+m[1], +m[2] - 1, +m[3]) : new Date(str);
        return Number.isNaN(d.getTime()) ? null : d;
    }

    function fmtDate(str) {
        const d = parseDate(str);
        if (!d) {
            return { text: str || "", full: str || "", days: Infinity };
        }
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        const day = new Date(d.getFullYear(), d.getMonth(), d.getDate());
        const days = Math.round((today - day) / 86400000);
        const full = `${MONTHS[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
        let text;
        if (days === 0) {
            text = "Today";
        } else if (days === 1) {
            text = "Yesterday";
        } else if (days > 1 && days < 7) {
            text = days + " days ago";
        } else if (d.getFullYear() === today.getFullYear()) {
            text = `${MONTHS[d.getMonth()]} ${d.getDate()}`;
        } else {
            text = full;
        }
        return { text, full, days };
    }

    function shortBuild(build) {
        if (!build) {
            return "";
        }
        const m = /^(\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2})?)\b/.exec(build);
        return m ? m[1] : build;
    }

    function shortPath(p) {
        if (!p) {
            return "";
        }
        const parts = String(p).split(/[\\/]+/).filter(Boolean);
        return parts.length > 2 ? "…/" + parts.slice(-2).join("/") : parts.join("/");
    }

    // -------------------------------------------------------------------------------------- backend

    let api = null;

    function invoke(cmd, args) {
        return api.core.invoke(cmd, args);
    }

    // Human wording for the error codes of the `error` event.
    const ERRORS = {
        network: {
            title: "Can't reach the server",
            body: "Check your internet connection, then press Retry.",
            action: "retry",
        },
        signature: {
            title: "The update failed a safety check",
            body: "It wasn't signed by Bleakhold, so nothing was changed. Try again later.",
            action: "retry",
        },
        manifest: {
            title: "The update list is broken",
            body: "Nothing was changed. Please try again in a few minutes.",
            action: "retry",
        },
        disk_full: {
            title: "Your disk is full",
            body: "Free up some space on this drive, then press Retry.",
            action: "retry",
        },
        game_running: {
            title: "Close Bleakhold to update",
            body: "The game is still running. Quit it, then press Retry.",
            action: "retry",
            tone: "warn",
        },
        hash: {
            title: "A download kept arriving damaged",
            body: "This is usually a shaky connection. Press Retry to try again.",
            action: "retry",
        },
        io: {
            title: "Couldn't write a file",
            body: "Make sure the game folder isn't read-only, then try Check files.",
            action: "repair",
        },
        launch: {
            title: "Bleakhold didn't start",
            body: "Try Check files to repair the game, then press Play again.",
            action: "repair",
        },
    };

    function errorInfo(code) {
        return ERRORS[code] || { title: "Something went wrong", body: "Press Retry to try again.", action: "retry" };
    }

    // Calls a command; a failure becomes a toast and resolves to FAILED.
    const FAILED = Symbol("failed");

    async function call(cmd, args) {
        try {
            return await invoke(cmd, args);
        } catch (err) {
            console.error(`[launcher] ${cmd} failed`, err);
            const code = err && typeof err === "object" ? err.code : null;
            const message = typeof err === "string" ? err : (err && err.message) || "";
            if (code && ERRORS[code]) {
                showErrorToast(code, message);
            } else {
                toast({ tone: "error", title: "That didn't work", body: message || "Please try again." });
            }
            return FAILED;
        }
    }

    // ---------------------------------------------------------------------------------------- model

    const PROGRESS_PHASES = new Set(["downloading", "verifying", "paused", "self_updating"]);
    const BUSY_PHASES = new Set(["loading", "launching", "verifying", "self_updating"]);

    const model = {
        state: {
            launcher_version: "",
            phase: "loading",
            message: "",
            installed: false,
            install_dir: "",
            settings: { parallel: 4, limit_mbps: 0, close_on_play: true },
            build: "",
            total_bytes: 0,
            pending_bytes: 0,
            news: [],
            links: {},
            server: null,
        },
        progress: null,
        speed: 0,
        eta: null,
        lastError: null,
        phaseSeq: 0,
        pending: null, // { action, phase, timer }: the big button waits for the backend
    };

    function applyState(s) {
        if (!s || typeof s !== "object") {
            return;
        }
        const st = model.state;
        Object.assign(st, s);
        st.settings = Object.assign({ parallel: 4, limit_mbps: 0, close_on_play: true }, s.settings || st.settings);
        st.news = Array.isArray(st.news) ? st.news : [];
        st.links = st.links && typeof st.links === "object" ? st.links : {};
        render();
    }

    let syncing = null;

    async function syncState() {
        const seq = model.phaseSeq;
        try {
            const s = await invoke("get_state");
            if (s && model.phaseSeq !== seq) {
                // a newer phase event arrived meanwhile: keep it
                delete s.phase;
                delete s.message;
            }
            applyState(s);
        } catch (err) {
            console.error("[launcher] get_state failed", err);
        }
    }

    function requestSync() {
        if (!syncing) {
            syncing = syncState().finally(() => {
                syncing = null;
            });
        }
    }

    function onPhase(p) {
        if (!p || !p.phase) {
            return;
        }
        const prev = model.state.phase;
        model.state.phase = p.phase;
        model.state.message = p.message || "";
        model.phaseSeq++;
        clearPending();
        if (p.phase !== prev) {
            if (!PROGRESS_PHASES.has(p.phase)) {
                model.progress = null;
            }
            if (p.phase === "downloading" && prev !== "paused") {
                model.speed = 0;
                model.eta = null;
            }
            if (p.phase !== "error") {
                model.lastError = null;
            }
            if (p.phase === "launching" || p.phase === "playing") {
                closeDrawer();
            }
            if (install.busy && (p.phase === "downloading" || p.phase === "verifying" || p.phase === "error")) {
                install.busy = false;
                closeInstall(true);
            }
        }
        render();
        if (!PROGRESS_PHASES.has(p.phase) && p.phase !== "launching") {
            requestSync();
        }
    }

    function onProgress(p) {
        if (!p) {
            return;
        }
        model.progress = p;
        const speed = num(p.speed_bps);
        if (speed != null) {
            model.speed = model.speed > 0 ? model.speed * 0.7 + speed * 0.3 : speed;
        }
        const eta = num(p.eta_s);
        if (eta == null || eta < 0) {
            model.eta = null;
        } else if (model.eta == null || Math.abs(eta - model.eta) > model.eta * 0.6 + 30) {
            model.eta = eta;
        } else {
            model.eta = model.eta * 0.8 + eta * 0.2;
        }
        scheduleProgressRender();
    }

    function onServer(p) {
        if (!p) {
            return;
        }
        model.state.server = Object.assign({}, model.state.server || {}, p);
        renderRealm();
    }

    function onError(p) {
        if (!p) {
            return;
        }
        model.lastError = { code: p.code, message: p.message || "" };
        clearPending();
        showErrorToast(p.code, p.message);
        render();
    }

    // --------------------------------------------------------------------------------------- status

    function statusView() {
        const st = model.state;
        const pr = model.progress;
        const v = {
            title: "",
            detail: [],
            badge: null,
            bar: null, // { pct, mode }
            pct: "",
            file: "",
            pause: null,
            cancel: false,
        };
        const total = num(st.total_bytes) || 0;
        const pending = num(st.pending_bytes) || 0;
        const build = shortBuild(st.build);

        const barFromProgress = (mode) => {
            if (pr && num(pr.total_bytes) > 0) {
                const pct = Math.max(0, Math.min(100, (pr.done_bytes / pr.total_bytes) * 100));
                v.bar = { pct, mode };
                v.pct = (pct >= 99.95 ? 100 : Math.floor(pct)) + "%";
            } else if (pr && num(pr.files_total) > 0) {
                const pct = Math.max(0, Math.min(100, (pr.files_done / pr.files_total) * 100));
                v.bar = { pct, mode };
                v.pct = Math.floor(pct) + "%";
            } else {
                v.bar = { pct: 0, mode: "indeterminate" };
            }
        };

        switch (st.phase) {
        case "loading":
            v.title = "Checking for updates";
            v.detail = ["Contacting the Bleakhold server…"];
            v.bar = { pct: 0, mode: "indeterminate" };
            break;
        case "offline":
            v.title = "Can't reach the server";
            v.badge = { kind: "offline", icon: "offline" };
            v.detail = st.installed
                ? ["You can still play", "Updates resume when the server is back"]
                : ["Check your internet connection, then try again"];
            break;
        case "needs_install":
            v.title = "Welcome to Bleakhold";
            v.detail = ["Install the game to begin"];
            if (total > 0) {
                v.detail.push([{ b: fmtBytes(total) }, " download"]);
            }
            break;
        case "needs_update":
            v.title = "Update available";
            v.badge = { kind: "gold", icon: "download" };
            v.detail = [pending > 0 ? [{ b: fmtBytes(pending) }, " to download"] : "A new build is ready"];
            if (build) {
                v.detail.push("Build " + build);
            }
            break;
        case "downloading":
            v.title = st.installed ? "Updating Bleakhold" : "Installing Bleakhold";
            barFromProgress("normal");
            if (pr && num(pr.total_bytes) > 0) {
                v.detail = [[{ b: fmtBytes(pr.done_bytes) }, " of " + fmtBytes(pr.total_bytes)]];
                const speed = fmtSpeed(model.speed);
                const eta = fmtEta(model.eta);
                if (speed) {
                    v.detail.push(speed);
                }
                if (eta) {
                    v.detail.push(eta);
                }
                v.file = shortPath(pr.file);
            } else {
                v.detail = ["Preparing the download…"];
            }
            v.pause = "pause";
            v.cancel = true;
            break;
        case "verifying":
            v.title = "Checking files";
            barFromProgress("verify");
            if (pr && num(pr.files_total) > 0) {
                v.detail = [[{ b: Number(pr.files_done || 0).toLocaleString("en-US") },
                    " of " + Number(pr.files_total).toLocaleString("en-US") + " files"]];
                const speed = fmtSpeed(model.speed);
                if (speed) {
                    v.detail.push(speed);
                }
                v.file = shortPath(pr.file);
            } else {
                v.detail = ["Making sure every file is right…"];
            }
            break;
        case "paused":
            v.title = "Paused";
            v.badge = { kind: "muted", icon: "pause" };
            if (pr && num(pr.total_bytes) > 0) {
                barFromProgress("paused");
                v.detail = [
                    [{ b: fmtBytes(pr.done_bytes) }, " of " + fmtBytes(pr.total_bytes)],
                    "Resume whenever you like",
                ];
            } else if (!st.installed && total > 0) {
                const pct = Math.max(0, Math.min(100, ((total - pending) / total) * 100));
                v.bar = { pct, mode: "paused" };
                v.pct = Math.floor(pct) + "%";
                v.detail = [[{ b: fmtBytes(total - pending) }, " of " + fmtBytes(total)], "Resume whenever you like"];
            } else {
                v.detail = [pending > 0 ? [{ b: fmtBytes(pending) }, " left to download"] : "Resume whenever you like"];
            }
            v.pause = "resume";
            v.cancel = true;
            break;
        case "ready":
            v.title = "Ready to play";
            v.badge = { kind: "ok", icon: "check" };
            v.detail = ["Up to date"];
            if (build) {
                v.detail.push("Build " + build);
            }
            break;
        case "launching":
            v.title = "Starting Bleakhold";
            v.detail = ["Setting the realm and opening the game…"];
            break;
        case "playing":
            v.title = "Bleakhold is running";
            v.badge = { kind: "run", icon: "play" };
            v.detail = ["Have fun out there", "Updates wait until you close the game"];
            break;
        case "self_updating":
            v.title = "Updating the launcher";
            barFromProgress("normal");
            v.detail = [st.message || "It restarts by itself in a moment"];
            break;
        case "error": {
            const e = model.lastError;
            const info = e ? errorInfo(e.code) : null;
            v.title = info ? info.title : "Something went wrong";
            v.badge = { kind: info && info.tone === "warn" ? "gold" : "error", icon: "alert" };
            v.detail = [info ? info.body : st.message || "Press Retry to try again."];
            break;
        }
        default:
            v.title = st.phase || "";
        }
        return v;
    }

    function fillDetail(node, parts) {
        node.textContent = "";
        parts.forEach((part, i) => {
            if (i > 0) {
                node.appendChild(el("span", "sep", "·"));
            }
            (Array.isArray(part) ? part : [part]).forEach((bit) => {
                if (bit && typeof bit === "object") {
                    node.appendChild(el("b", null, bit.b));
                } else {
                    node.appendChild(document.createTextNode(bit));
                }
            });
        });
        node.title = node.textContent;
    }

    const dom = {};

    function renderStatus() {
        const v = statusView();
        dom.statusTitle.textContent = v.title;
        dom.statusPct.textContent = v.pct;
        fillDetail(dom.statusDetail, v.detail);
        dom.statusFile.textContent = v.file;
        dom.statusFile.title = model.progress && model.progress.file ? model.progress.file : "";

        if (v.badge) {
            if (dom.statusBadge.dataset.icon !== v.badge.icon || dom.statusBadge.dataset.kind !== v.badge.kind) {
                dom.statusBadge.dataset.kind = v.badge.kind;
                dom.statusBadge.dataset.icon = v.badge.icon;
                dom.statusBadge.innerHTML = icon(v.badge.icon);
                dom.statusBadge.classList.remove("is-shown");
                void dom.statusBadge.offsetWidth; // restart the pop animation
            }
            dom.statusBadge.classList.add("is-shown");
        } else {
            dom.statusBadge.classList.remove("is-shown");
            delete dom.statusBadge.dataset.icon;
        }

        dom.status.classList.toggle("has-progress", !!v.bar);
        if (v.bar) {
            dom.progress.classList.toggle("is-paused", v.bar.mode === "paused");
            dom.progress.classList.toggle("is-verify", v.bar.mode === "verify");
            dom.progress.classList.toggle("is-indeterminate", v.bar.mode === "indeterminate");
            dom.progressFill.style.width = v.bar.pct.toFixed(2) + "%";
            if (v.bar.mode === "indeterminate") {
                dom.progress.removeAttribute("aria-valuenow");
            } else {
                dom.progress.setAttribute("aria-valuenow", String(Math.round(v.bar.pct)));
            }
        }
        dom.btnPause.hidden = !v.pause;
        dom.btnCancel.hidden = !v.cancel;
        dom.status.classList.toggle("has-mini", !!(v.pause || v.cancel));
        if (v.pause) {
            const label = v.pause === "pause" ? "Pause" : "Resume";
            if (dom.btnPause.dataset.icon !== (v.pause === "pause" ? "pause" : "play")) {
                dom.btnPause.dataset.icon = v.pause === "pause" ? "pause" : "play";
                dom.btnPause.innerHTML = icon(dom.btnPause.dataset.icon);
            }
            dom.btnPause.setAttribute("aria-label", label);
            dom.btnPause.dataset.tip = label;
            dom.btnPause.dataset.action = v.pause;
        }
        renderSelfUpdate(v);
    }

    let progressFrame = 0;
    let lastProgressPaint = 0;

    function scheduleProgressRender() {
        if (progressFrame) {
            return;
        }
        const wait = Math.max(0, 180 - (performance.now() - lastProgressPaint));
        progressFrame = setTimeout(() => {
            requestAnimationFrame(() => {
                progressFrame = 0;
                lastProgressPaint = performance.now();
                renderStatus();
            });
        }, wait);
    }

    // ---------------------------------------------------------------------------------- big button

    function ctaView() {
        const st = model.state;
        switch (st.phase) {
        case "loading":
            return { label: "Checking", busy: true };
        case "offline":
            return st.installed ? { label: "Play", action: "play", glow: true } : { label: "Retry", action: "check" };
        case "needs_install":
            return { label: "Install", action: "install", glow: true };
        case "needs_update":
            return { label: "Update", action: "update", glow: true };
        case "downloading":
            return { label: "Pause", action: "pause", secondary: true };
        case "verifying":
            return { label: "Checking", busy: true };
        case "paused":
            return { label: "Resume", action: "resume" };
        case "ready":
            return { label: "Play", action: "play", glow: true };
        case "launching":
            return { label: "Starting", busy: true };
        case "playing":
            return { label: "Playing", running: true };
        case "self_updating":
            return { label: "Updating", busy: true };
        case "error":
            return { label: "Retry", action: "check" };
        default:
            return { label: "Please wait", busy: true };
        }
    }

    function renderCta() {
        let v = ctaView();
        if (model.pending && model.pending.phase === model.state.phase) {
            v = { label: v.label, busy: true, secondary: v.secondary };
        }
        const cta = dom.cta;
        dom.ctaLabel.textContent = v.label;
        cta.disabled = !v.action;
        cta.dataset.action = v.action || "";
        cta.classList.toggle("is-busy", !!v.busy);
        cta.classList.toggle("is-running", !!v.running);
        cta.classList.toggle("is-secondary", !!v.secondary);
        cta.classList.toggle("is-glow", !!v.glow && !!v.action);
        cta.setAttribute("aria-label", v.busy ? v.label + "…" : v.label);
        cta.setAttribute("aria-busy", v.busy ? "true" : "false");
    }

    function clearPending() {
        if (model.pending) {
            clearTimeout(model.pending.timer);
            model.pending = null;
        }
    }

    // The big button (and the small pause button) wait for the backend's next phase, so a second click does
    // nothing; if no phase comes in a few seconds the button comes back.
    function runAction(action) {
        if (!action) {
            return;
        }
        if (action === "install") {
            openInstall();
            return;
        }
        if (action === "repair") {
            doRepair();
            return;
        }
        clearPending();
        model.pending = {
            action,
            phase: model.state.phase,
            timer: setTimeout(() => {
                model.pending = null;
                renderCta();
            }, 6000),
        };
        renderCta();
        call(action).then(() => {
            if (action === "check") {
                requestSync();
            }
        }, () => {});
    }

    function doRepair() {
        closeDrawer();
        call("repair");
    }

    // -------------------------------------------------------------------------------------- tools

    function canRepair() {
        const st = model.state;
        return !!st.installed && ["ready", "needs_update", "error"].includes(st.phase);
    }

    function canOpenFolder() {
        const st = model.state;
        return !!st.install_dir && (st.installed || PROGRESS_PHASES.has(st.phase));
    }

    function canClearCache() {
        const st = model.state;
        return !!st.installed && !["launching", "playing", "self_updating", "loading"].includes(st.phase);
    }

    function renderTools() {
        dom.btnFolder.disabled = !canOpenFolder();
        dom.btnRepair.disabled = !canRepair();
        dom.btnSettings.disabled = model.state.phase === "self_updating";
    }

    // -------------------------------------------------------------------------------------- realm

    function renderRealm() {
        const st = model.state;
        const sv = st.server;
        let state = "unknown";
        let label = "Checking";
        let tip = "";
        if (sv && typeof sv.online === "boolean") {
            if (!sv.online) {
                state = "offline";
                label = "Offline";
                tip = "The realm can't be reached right now";
            } else if (sv.auth === false || sv.world === false) {
                state = "partial";
                label = "Limited";
                tip = sv.world === false ? "The world server is down" : "The login server is down";
            } else {
                state = "online";
                label = "Online";
            }
        } else if (st.phase === "offline") {
            state = "offline";
            label = "Offline";
        }
        dom.realm.dataset.state = state;
        dom.realmStatus.textContent = label;
        const pill = dom.realmStatus.parentElement;
        if (tip) {
            pill.dataset.tip = tip;
        } else {
            delete pill.dataset.tip;
        }
        dom.realmName.textContent = (sv && sv.name) || "Bleakhold";

        const svc = (node, up) => {
            node.classList.toggle("is-up", up === true && state !== "offline");
            node.classList.toggle("is-down", up === false || (state === "offline" && up !== undefined));
        };
        svc(dom.svcAuth, sv ? sv.auth : undefined);
        svc(dom.svcWorld, sv ? sv.world : undefined);

        const ping = sv && state !== "offline" ? num(sv.ping_ms) : null;
        dom.realmPing.classList.remove("is-good", "is-fair", "is-poor");
        if (ping != null) {
            dom.realmPingText.textContent = Math.round(ping) + " ms";
            const q = ping <= 80 ? ["is-good", 3] : ping <= 160 ? ["is-fair", 2] : ["is-poor", 1];
            dom.realmPing.classList.add(q[0]);
            dom.realmPing.dataset.bars = String(q[1]);
        } else {
            dom.realmPingText.textContent = "–";
            dom.realmPing.dataset.bars = "0";
        }
    }

    // --------------------------------------------------------------------------------------- news

    let newsKey = "";

    function renderNews() {
        const st = model.state;
        const offline = st.phase === "offline";
        const emptyKind = offline ? "|off" : st.phase === "loading" ? "|load" : "";
        const key = JSON.stringify(st.news) + (st.news.length ? "" : emptyKind);
        if (key === newsKey) {
            return;
        }
        newsKey = key;
        const list = dom.newsList;
        list.textContent = "";
        if (!st.news.length) {
            if (st.phase === "loading") {
                return;
            }
            const card = el("div", "news-card news-empty");
            const ic = el("div", "news-empty-icon");
            ic.innerHTML = icon(offline ? "offline" : "news");
            const text = el("div");
            text.appendChild(el("div", "news-title", offline ? "News is unavailable offline" : "No news yet"));
            text.appendChild(el("div", "news-body", offline
                ? "It comes back as soon as the server can be reached."
                : "Patch notes, events and realm updates will show up here."));
            card.append(ic, text);
            list.appendChild(card);
            updateNewsOverflow();
            return;
        }
        st.news.forEach((item, i) => {
            if (!item || typeof item !== "object") {
                return;
            }
            const card = el("article", "news-card");
            const date = fmtDate(item.date);
            const meta = el("div", "news-meta");
            if (i === 0 && date.days <= 3) {
                meta.appendChild(el("span", "chip-new", "New"));
            }
            const time = el("time", null, date.text);
            if (item.date) {
                time.dateTime = String(item.date);
                time.title = date.full;
            }
            meta.appendChild(time);
            card.appendChild(meta);
            if (isHttp(item.url)) {
                card.classList.add("has-link");
                const more = el("button", "news-more");
                more.type = "button";
                more.appendChild(document.createTextNode("Read more"));
                more.insertAdjacentHTML("beforeend", icon("arrow"));
                more.setAttribute("aria-label", "Read more: " + (item.title || "news"));
                more.addEventListener("click", (e) => {
                    e.stopPropagation();
                    openUrl(item.url);
                });
                meta.appendChild(more);
                card.addEventListener("click", () => openUrl(item.url));
            }
            const title = el("h3", "news-title", item.title || "Untitled");
            title.title = item.title || "";
            card.appendChild(title);
            if (item.body) {
                card.appendChild(el("p", "news-body", item.body));
            }
            list.appendChild(card);
        });
        updateNewsOverflow();
    }

    function updateNewsOverflow() {
        const list = dom.newsList;
        const over = list.scrollHeight > list.clientHeight + 2;
        const atEnd = list.scrollTop + list.clientHeight >= list.scrollHeight - 4;
        list.classList.toggle("is-overflowing", over && !atEnd);
    }

    function openUrl(url) {
        if (isHttp(url)) {
            call("open_url", { url });
        }
    }

    // -------------------------------------------------------------------------------------- links

    let linksKey = "";
    const LINK_ORDER = [
        ["register", "Create account", "user", true],
        ["website", "Website", "globe", false],
        ["discord", "Discord", "chat", false],
    ];

    function renderLinks() {
        const links = model.state.links || {};
        const key = JSON.stringify(links);
        if (key === linksKey) {
            return;
        }
        linksKey = key;
        dom.links.textContent = "";
        const known = new Set(LINK_ORDER.map((l) => l[0]));
        const entries = LINK_ORDER.filter(([k]) => isHttp(links[k]))
            .map(([k, label, ic, accent]) => [links[k], label, ic, accent]);
        Object.keys(links).forEach((k) => {
            if (!known.has(k) && isHttp(links[k]) && entries.length < 5) {
                entries.push([links[k], k.charAt(0).toUpperCase() + k.slice(1).replace(/_/g, " "), "globe", false]);
            }
        });
        entries.forEach(([url, label, ic, accent]) => {
            const b = el("button", "tb-link" + (accent ? " is-accent" : ""));
            b.type = "button";
            b.innerHTML = icon(ic);
            b.appendChild(el("span", null, label));
            b.addEventListener("click", () => openUrl(url));
            dom.links.appendChild(b);
        });
    }

    // -------------------------------------------------------------------------------- self-update

    function renderSelfUpdate(v) {
        const on = model.state.phase === "self_updating";
        if (dom.selfupdate.hidden === on) {
            dom.selfupdate.hidden = !on;
            if (on) {
                closeDrawer();
                closeInstall(true);
            }
        }
        if (!on) {
            return;
        }
        dom.selfupdateMsg.textContent = model.state.message ||
            "A newer Bleakhold Launcher is out. It restarts by itself in a moment.";
        const bar = v && v.bar;
        const prog = dom.selfupdateFill.parentElement;
        const det = !bar || bar.mode === "indeterminate";
        prog.classList.toggle("is-indeterminate", det);
        dom.selfupdateFill.style.width = det ? "" : bar.pct.toFixed(1) + "%";
        const pr = model.progress;
        dom.selfupdatePct.textContent = !det && pr && num(pr.total_bytes) > 0
            ? `${fmtBytes(pr.done_bytes)} of ${fmtBytes(pr.total_bytes)}`
            : "";
    }

    // ----------------------------------------------------------------------------------- render all

    function render() {
        const st = model.state;
        app.dataset.phase = st.phase;
        if (tipTarget && tipTarget.offsetParent === null) {
            hideTip();
        }
        renderStatus();
        renderCta();
        renderTools();
        renderRealm();
        renderNews();
        renderLinks();
        if (!dom.drawer.hidden) {
            renderSettings(false);
        }
        if (!dom.modal.hidden) {
            renderInstall();
        }
        updateCalm();
    }

    // ------------------------------------------------------------------------------------ settings

    function renderSettings(fillInputs) {
        const st = model.state;
        const s = st.settings || {};
        if (fillInputs) {
            const parallel = Math.min(8, Math.max(1, Math.round(num(s.parallel) || 4)));
            dom.setParallel.value = String(parallel);
            dom.setLimit.value = num(s.limit_mbps) > 0 ? String(s.limit_mbps) : "";
            dom.setClose.checked = s.close_on_play !== false;
            updateRange();
        }
        dom.setPath.textContent = st.install_dir || "Not installed yet";
        dom.setPath.title = st.install_dir || "";
        dom.setPath.classList.toggle("is-empty", !st.install_dir);
        dom.setOpen.disabled = !canOpenFolder();
        dom.setRepair.disabled = !canRepair();
        dom.setCache.disabled = !canClearCache();
        dom.setVersion.textContent = st.launcher_version || "–";
        dom.setBuild.textContent = st.build || "–";
        dom.setBuild.parentElement.title = st.build || "";
    }

    function updateRange() {
        const r = dom.setParallel;
        const pct = ((r.value - r.min) / (r.max - r.min)) * 100;
        r.style.setProperty("--pct", pct + "%");
        dom.setParallelOut.textContent = r.value;
    }

    const saveSettings = debounce(async () => {
        const settings = Object.assign({}, model.state.settings);
        if ((await call("save_settings", { settings })) !== FAILED) {
            flashSaved();
        }
    }, 450);

    let savedTimer = 0;

    function flashSaved() {
        dom.savedNote.innerHTML = icon("check");
        dom.savedNote.appendChild(el("span", null, "Saved"));
        dom.savedNote.classList.add("is-shown");
        clearTimeout(savedTimer);
        savedTimer = setTimeout(() => dom.savedNote.classList.remove("is-shown"), 1600);
    }

    function readSettingsInputs() {
        const s = model.state.settings;
        s.parallel = Math.min(8, Math.max(1, parseInt(dom.setParallel.value, 10) || 4));
        const lim = parseFloat(dom.setLimit.value);
        s.limit_mbps = Number.isFinite(lim) && lim > 0 ? Math.min(1000, Math.round(lim)) : 0;
        s.close_on_play = dom.setClose.checked;
    }

    let lastFocus = null;

    function openDrawer() {
        if (!dom.drawer.hidden || model.state.phase === "self_updating") {
            return;
        }
        hideTip();
        lastFocus = document.activeElement;
        renderSettings(true);
        dom.drawer.hidden = false;
        dom.scrim.hidden = false;
        requestAnimationFrame(() => {
            dom.drawer.classList.add("is-open");
            dom.scrim.classList.add("is-open");
        });
        setTimeout(() => dom.drawer.focus({ preventScroll: true }), 60);
    }

    function closeDrawer() {
        if (dom.drawer.hidden) {
            return;
        }
        dom.drawer.classList.remove("is-open");
        dom.scrim.classList.remove("is-open");
        setTimeout(() => {
            if (!dom.drawer.classList.contains("is-open")) {
                dom.drawer.hidden = true;
                dom.scrim.hidden = true;
            }
        }, 320);
        restoreFocus();
    }

    function restoreFocus() {
        if (lastFocus && document.contains(lastFocus) && !lastFocus.disabled) {
            lastFocus.focus({ preventScroll: true });
        }
        lastFocus = null;
    }

    // ------------------------------------------------------------------------------ install dialog

    const install = { path: "", info: null, loading: false, failed: false, busy: false, token: 0 };

    function openInstall() {
        if (!dom.modal.hidden) {
            return;
        }
        hideTip();
        closeDrawer();
        lastFocus = document.activeElement;
        install.path = model.state.install_dir || "";
        install.info = null;
        install.failed = false;
        install.busy = false;
        dom.modal.hidden = false;
        requestAnimationFrame(() => dom.modal.classList.add("is-open"));
        renderInstall();
        if (install.path) {
            fetchFolderInfo(install.path);
        }
        setTimeout(() => (install.path ? dom.installGo : dom.installBrowse).focus({ preventScroll: true }), 80);
    }

    function closeInstall(force) {
        if (dom.modal.hidden || (install.busy && !force)) {
            return;
        }
        dom.modal.classList.remove("is-open");
        setTimeout(() => {
            if (!dom.modal.classList.contains("is-open")) {
                dom.modal.hidden = true;
            }
        }, 260);
        restoreFocus();
    }

    async function fetchFolderInfo(path) {
        const token = ++install.token;
        install.loading = true;
        install.failed = false;
        renderInstall();
        try {
            const info = await invoke("folder_info", { path });
            if (token !== install.token) {
                return;
            }
            install.info = info || null;
            if (info && info.path) {
                install.path = info.path;
            }
        } catch (err) {
            if (token !== install.token) {
                return;
            }
            console.error("[launcher] folder_info failed", err);
            install.info = null;
            install.failed = true;
        }
        install.loading = false;
        renderInstall();
    }

    function note(tone, iconName, parts) {
        const n = el("div", "note");
        n.dataset.tone = tone;
        n.innerHTML = icon(iconName);
        const span = el("span");
        parts.forEach((p) => span.appendChild(typeof p === "object" ? el("b", null, p.b) : document.createTextNode(p)));
        n.appendChild(span);
        return n;
    }

    function renderInstall() {
        const info = install.info;
        dom.installPath.textContent = install.path || "Choose a folder";
        dom.installPath.title = install.path || "";
        dom.installPath.classList.toggle("is-empty", !install.path);

        const needed = info && num(info.needed_bytes) != null
            ? info.needed_bytes
            : num(model.state.total_bytes) || null;
        const free = info ? num(info.free_bytes) : null;
        const short = needed != null && free != null && free < needed;
        dom.space.classList.toggle("is-loading", install.loading);
        dom.space.classList.toggle("is-short", !install.loading && short);
        dom.spaceNeeded.textContent = needed != null ? fmtBytes(needed) : "–";
        dom.spaceFree.textContent = install.loading ? "Checking…" : free != null ? fmtBytes(free) : "–";
        dom.spaceUsed.style.width = needed != null && free
            ? Math.min(100, Math.max(2, (needed / free) * 100)) + "%"
            : "0%";

        dom.installNotes.textContent = "";
        if (!install.loading && info) {
            if (info.has_game) {
                dom.installNotes.appendChild(note("ok", "check",
                    [{ b: "Existing WoW 3.3.5a found." }, " Only the missing files will be downloaded."]));
            }
            if (info.writable === false) {
                dom.installNotes.appendChild(note("error", "error",
                    ["The launcher can't write to this folder. Pick another one, for example ",
                        { b: "C:\\Games" }, "."]));
            } else if (short) {
                dom.installNotes.appendChild(note("error", "alert",
                    ["Not enough free space. Free up ", { b: fmtBytes(needed - free) }, " or choose another drive."]));
            }
        } else if (!install.loading && install.failed) {
            dom.installNotes.appendChild(note("warn", "info",
                ["Couldn't check this folder. You can still try to install here."]));
        }

        const ok = !!install.path && !install.loading && !install.busy &&
            (info ? info.writable !== false && !short : install.failed);
        dom.installGo.disabled = !ok;
        dom.installGo.classList.toggle("is-busy", install.busy);
        dom.installBrowse.disabled = install.busy;
        dom.installCancel.disabled = install.busy;
    }

    async function browseFolder() {
        const path = await call("choose_folder");
        if (typeof path === "string" && path) {
            install.path = path;
            install.info = null;
            fetchFolderInfo(path);
        }
    }

    async function startInstall() {
        if (dom.installGo.disabled) {
            return;
        }
        install.busy = true;
        renderInstall();
        try {
            await invoke("install", {
                path: install.path,
                desktop_shortcut: dom.optDesktop.checked,
                start_menu: dom.optStart.checked,
            });
            install.busy = false;
            closeInstall(true);
        } catch (err) {
            install.busy = false;
            renderInstall();
            console.error("[launcher] install failed", err);
            const code = err && typeof err === "object" ? err.code : null;
            const message = typeof err === "string" ? err : (err && err.message) || "";
            if (code && ERRORS[code]) {
                showErrorToast(code, message);
            } else {
                toast({ tone: "error", title: "Couldn't start the install", body: message || "Please try again." });
            }
        }
    }

    // -------------------------------------------------------------------------------------- toasts

    const TOAST_ICON = { error: "error", warn: "alert", info: "info", ok: "check" };

    function toast(opts) {
        const tone = opts.tone || "info";
        const key = opts.key || tone + "|" + opts.title;
        dom.toasts.querySelectorAll(".toast").forEach((t) => {
            if (t.dataset.key === key) {
                t.remove();
            }
        });
        const t = el("div", "toast");
        t.dataset.tone = tone;
        t.dataset.key = key;
        t.setAttribute("role", tone === "error" ? "alert" : "status");
        const ic = el("div", "toast-icon");
        ic.innerHTML = icon(opts.icon || TOAST_ICON[tone]);
        const body = el("div", "toast-text");
        body.appendChild(el("div", "toast-title", opts.title));
        if (opts.body) {
            body.appendChild(el("div", "toast-body", opts.body));
        }
        if (opts.detail) {
            const d = el("div", "toast-detail", opts.detail);
            d.title = opts.detail;
            body.appendChild(d);
        }
        if (opts.actions && opts.actions.length) {
            const row = el("div", "toast-actions");
            opts.actions.forEach((a) => {
                const b = el("button", "btn btn-ghost btn-sm", a.label);
                b.type = "button";
                b.addEventListener("click", () => {
                    dismiss(t);
                    a.run();
                });
                row.appendChild(b);
            });
            body.appendChild(row);
        }
        const close = el("button", "toast-close");
        close.type = "button";
        close.setAttribute("aria-label", "Dismiss");
        close.innerHTML = icon("close");
        close.addEventListener("click", () => dismiss(t));
        t.append(ic, body, close);

        const timeout = opts.timeout != null ? opts.timeout : tone === "error" || tone === "warn" ? 12000 : 4500;
        if (timeout > 0) {
            const bar = el("div", "toast-timer");
            bar.style.animationDuration = timeout + "ms";
            bar.addEventListener("animationend", () => dismiss(t));
            t.appendChild(bar);
        }
        dom.toasts.appendChild(t);
        const all = dom.toasts.querySelectorAll(".toast:not(.is-leaving)");
        if (all.length > 3) {
            dismiss(all[0]);
        }
        return t;
    }

    function dismiss(t) {
        if (!t || t.classList.contains("is-leaving")) {
            return;
        }
        t.classList.add("is-leaving");
        t.addEventListener("animationend", () => t.remove(), { once: true });
        setTimeout(() => t.remove(), 400);
    }

    function showErrorToast(code, message) {
        const info = errorInfo(code);
        const actions = [];
        if (info.action === "repair" && model.state.installed) {
            actions.push({ label: "Check files", run: doRepair });
        }
        const detail = message && message !== info.body && message !== info.title ? message : "";
        toast({
            tone: info.tone || "error",
            key: "err|" + code,
            title: info.title,
            body: info.body,
            detail,
            actions,
        });
    }

    // ------------------------------------------------------------------------------------- tooltip

    let tipTarget = null;
    let tipTimer = 0;

    function showTip(target, delay) {
        clearTimeout(tipTimer);
        tipTarget = target;
        tipTimer = setTimeout(() => {
            if (tipTarget !== target || !target.dataset.tip || !document.contains(target)) {
                return;
            }
            const tip = dom.tooltip;
            tip.textContent = target.dataset.tip;
            tip.hidden = false;
            const sr = target.getBoundingClientRect();
            const r = {
                left: sr.left / uiScale, top: sr.top / uiScale, width: sr.width / uiScale, bottom: sr.bottom / uiScale,
            };
            const tw = tip.offsetWidth;
            const th = tip.offsetHeight;
            let x = r.left + r.width / 2 - tw / 2;
            x = Math.max(8, Math.min(app.clientWidth - tw - 8, x));
            let y = r.top - th - 8;
            if (y < 48) {
                y = r.bottom + 8;
            }
            tip.style.transform = "";
            tip.style.left = Math.round(x) + "px";
            tip.style.top = Math.round(y) + "px";
            requestAnimationFrame(() => tip.classList.add("is-shown"));
        }, delay);
    }

    function hideTip() {
        clearTimeout(tipTimer);
        tipTarget = null;
        dom.tooltip.classList.remove("is-shown");
        dom.tooltip.hidden = true;
    }

    // -------------------------------------------------------------------------------------- embers

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

    const embers = (() => {
        const canvas = $("embers");
        const ctx = canvas.getContext("2d");
        let w = 0;
        let h = 0;
        let dpr = 1;
        let parts = [];
        let raf = 0;
        let last = 0;
        let running = false;
        const sprites = {};

        function sprite(key, r, g, b) {
            const s = document.createElement("canvas");
            s.width = s.height = 32;
            const c = s.getContext("2d");
            const grad = c.createRadialGradient(16, 16, 0, 16, 16, 16);
            grad.addColorStop(0, `rgba(255,255,235,1)`);
            grad.addColorStop(0.18, `rgba(${r},${g},${b},0.95)`);
            grad.addColorStop(0.45, `rgba(${r},${g},${b},0.28)`);
            grad.addColorStop(1, `rgba(${r},${g},${b},0)`);
            c.fillStyle = grad;
            c.fillRect(0, 0, 32, 32);
            sprites[key] = s;
        }

        sprite("ember", 255, 138, 52);
        sprite("gold", 241, 200, 120);
        sprite("fel", 150, 255, 90);

        function resize() {
            dpr = Math.min(window.devicePixelRatio || 1, 1.5);
            w = canvas.clientWidth;
            h = canvas.clientHeight;
            canvas.width = Math.round(w * dpr);
            canvas.height = Math.round(h * dpr);
        }

        function portal() {
            // the portal's place on screen: 70.8% / 64.2% of the drifting painting
            const a = $("bg-art").getBoundingClientRect();
            const art = {
                left: a.left / uiScale, top: a.top / uiScale, width: a.width / uiScale, height: a.height / uiScale,
            };
            return { x: art.left + art.width * 0.708, y: art.top + art.height * 0.642, rw: art.width * 0.05 };
        }

        function spawn(initial) {
            const fel = Math.random() < 0.16;
            const p = {
                kind: fel ? "fel" : Math.random() < 0.3 ? "gold" : "ember",
                size: fel ? 2 + Math.random() * 3 : 2 + Math.random() * 4.5,
                life: 0,
                max: 7 + Math.random() * 9,
                vx: (Math.random() - 0.5) * 8,
                vy: -(10 + Math.random() * 26),
                sway: 6 + Math.random() * 16,
                phase: Math.random() * Math.PI * 2,
                freq: 0.4 + Math.random() * 0.9,
                flick: Math.random() * Math.PI * 2,
            };
            if (fel) {
                const po = portal();
                p.x = po.x + (Math.random() - 0.5) * po.rw * 2;
                p.y = po.y + (Math.random() - 0.2) * po.rw * 1.5;
                p.vy *= 0.7;
            } else {
                p.x = Math.random() * w;
                p.y = initial ? Math.random() * h : h + 10 + Math.random() * 40;
            }
            if (initial) {
                p.life = Math.random() * p.max;
            }
            return p;
        }

        function frame(t) {
            raf = requestAnimationFrame(frame);
            const dt = Math.min(0.05, (t - (last || t)) / 1000);
            last = t;
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            ctx.clearRect(0, 0, w, h);
            ctx.globalCompositeOperation = "lighter";
            for (let i = 0; i < parts.length; i++) {
                const p = parts[i];
                p.life += dt;
                if (p.life >= p.max || p.y < -20) {
                    parts[i] = spawn(false);
                    continue;
                }
                p.y += p.vy * dt;
                p.x += (p.vx + Math.sin(p.phase + p.life * p.freq) * p.sway) * dt;
                const k = p.life / p.max;
                const fade = k < 0.15 ? k / 0.15 : k > 0.7 ? (1 - k) / 0.3 : 1;
                const flicker = 0.75 + 0.25 * Math.sin(p.flick + p.life * 7);
                ctx.globalAlpha = Math.max(0, fade * flicker * (p.kind === "fel" ? 0.55 : 0.7));
                const s = p.size * 2;
                ctx.drawImage(sprites[p.kind], p.x - s, p.y - s, s * 2, s * 2);
            }
            ctx.globalAlpha = 1;
        }

        function set(on) {
            if (on === running) {
                return;
            }
            running = on;
            if (on) {
                resize();
                if (!parts.length) {
                    parts = Array.from({ length: 46 }, () => spawn(true));
                }
                last = 0;
                raf = requestAnimationFrame(frame);
            } else {
                cancelAnimationFrame(raf);
                ctx.clearRect(0, 0, canvas.width, canvas.height);
            }
        }

        window.addEventListener("resize", () => running && resize());
        return { set };
    })();

    // Animations rest while the window is hidden, while the game runs, and under reduced motion.
    function updateCalm() {
        const calm = document.hidden || model.state.phase === "playing";
        app.classList.toggle("is-calm", calm);
        embers.set(!calm && !reducedMotion.matches && !app.classList.contains("is-booting"));
    }

    // --------------------------------------------------------------------------------- focus trap

    function focusables(root) {
        return [...root.querySelectorAll("button, input, [tabindex]:not([tabindex='-1'])")]
            .filter((n) => !n.disabled && n.offsetParent !== null);
    }

    function trapTab(e, root) {
        const items = focusables(root);
        if (!items.length) {
            return;
        }
        const first = items[0];
        const lastItem = items[items.length - 1];
        if (!root.contains(document.activeElement)) {
            e.preventDefault();
            first.focus();
        } else if (e.shiftKey && document.activeElement === first) {
            e.preventDefault();
            lastItem.focus();
        } else if (!e.shiftKey && document.activeElement === lastItem) {
            e.preventDefault();
            first.focus();
        }
    }

    // ------------------------------------------------------------------------------------ binding

    function bindDom() {
        const ids = {
            status: "status", statusTitle: "status-title", statusPct: "status-pct", statusDetail: "status-detail",
            statusFile: "status-file", statusBadge: "status-badge", progress: "progress", progressFill: "progress-fill",
            btnPause: "btn-pause", btnCancel: "btn-cancel", btnFolder: "btn-folder", btnRepair: "btn-repair",
            btnSettings: "btn-settings", cta: "cta", ctaLabel: "cta-label", realm: "realm", realmStatus: "realm-status",
            realmName: "realm-name", svcAuth: "svc-auth", svcWorld: "svc-world", realmPing: "realm-ping",
            realmPingText: "realm-ping-text", newsList: "news-list", links: "links", toasts: "toasts", scrim: "scrim",
            drawer: "drawer", drawerClose: "drawer-close", savedNote: "saved-note", setPath: "set-path",
            setOpen: "set-open", setParallel: "set-parallel", setParallelOut: "set-parallel-out", setLimit: "set-limit",
            setClose: "set-close", setRepair: "set-repair", setCache: "set-cache", setVersion: "set-version",
            setBuild: "set-build", modal: "install-modal", installPath: "install-path", installBrowse: "install-browse",
            space: "space", spaceNeeded: "space-needed", spaceFree: "space-free", spaceUsed: "space-used",
            installNotes: "install-notes", optDesktop: "opt-desktop", optStart: "opt-start",
            installCancel: "install-cancel", installGo: "install-go", selfupdate: "selfupdate",
            selfupdateMsg: "selfupdate-msg", selfupdateFill: "selfupdate-fill", selfupdatePct: "selfupdate-pct",
            tooltip: "tooltip",
        };
        Object.keys(ids).forEach((k) => {
            dom[k] = $(ids[k]);
        });
    }

    function bindUi() {
        $("btn-min").addEventListener("click", () => call("minimize"));
        $("btn-close").addEventListener("click", () => call("close"));

        dom.cta.addEventListener("click", () => runAction(dom.cta.dataset.action));
        dom.btnPause.addEventListener("click", () => runAction(dom.btnPause.dataset.action));
        dom.btnCancel.addEventListener("click", () => call("cancel"));
        dom.btnFolder.addEventListener("click", () => call("open_folder"));
        dom.btnRepair.addEventListener("click", doRepair);
        dom.btnSettings.addEventListener("click", () => (dom.drawer.hidden ? openDrawer() : closeDrawer()));

        // settings
        dom.drawerClose.addEventListener("click", closeDrawer);
        dom.scrim.addEventListener("click", closeDrawer);
        dom.setOpen.addEventListener("click", () => call("open_folder"));
        dom.setRepair.addEventListener("click", doRepair);
        dom.setCache.addEventListener("click", async () => {
            dom.setCache.disabled = true;
            const r = await call("clear_cache");
            dom.setCache.disabled = !canClearCache();
            if (r !== FAILED) {
                toast({ tone: "ok", title: "Cache cleared", body: "The game rebuilds it the next time it starts." });
            }
        });
        dom.setParallel.addEventListener("input", () => {
            updateRange();
            readSettingsInputs();
            saveSettings();
        });
        dom.setLimit.addEventListener("input", () => {
            readSettingsInputs();
            saveSettings();
        });
        dom.setLimit.addEventListener("blur", () => {
            dom.setLimit.value = model.state.settings.limit_mbps > 0 ? String(model.state.settings.limit_mbps) : "";
        });
        dom.setClose.addEventListener("change", () => {
            readSettingsInputs();
            saveSettings();
        });

        // install dialog
        dom.installBrowse.addEventListener("click", browseFolder);
        $("folder-field").addEventListener("dblclick", browseFolder);
        dom.installCancel.addEventListener("click", () => closeInstall(false));
        dom.installGo.addEventListener("click", startInstall);
        dom.modal.addEventListener("mousedown", (e) => {
            if (e.target === dom.modal) {
                closeInstall(false);
            }
        });

        dom.newsList.addEventListener("scroll", updateNewsOverflow, { passive: true });

        // tooltips
        document.addEventListener("mouseover", (e) => {
            const t = e.target.closest && e.target.closest("[data-tip]");
            if (t && t !== tipTarget) {
                showTip(t, 380);
            } else if (!t && tipTarget) {
                hideTip();
            }
        });
        document.addEventListener("focusin", (e) => {
            const t = e.target.closest && e.target.closest("[data-tip]");
            if (t && t.matches(":focus-visible")) {
                showTip(t, 120);
            }
        });
        document.addEventListener("focusout", hideTip);
        document.addEventListener("mousedown", hideTip);

        document.addEventListener("keydown", (e) => {
            if (e.key === "Escape") {
                hideTip();
                if (!dom.modal.hidden) {
                    closeInstall(false);
                } else if (!dom.drawer.hidden) {
                    closeDrawer();
                }
                return;
            }
            if (e.key === "Tab") {
                if (!dom.modal.hidden) {
                    trapTab(e, dom.modal);
                } else if (!dom.drawer.hidden) {
                    trapTab(e, dom.drawer);
                }
            }
            if (isApp) {
                // no browser reload, print, find or source view inside the launcher
                const k = e.key.toLowerCase();
                const ctrl = (e.ctrlKey || e.metaKey) && k.length === 1 && "rpfgu".includes(k);
                if (e.key === "F5" || e.key === "F7" || ctrl) {
                    e.preventDefault();
                }
            }
        });

        if (isApp) {
            document.addEventListener("contextmenu", (e) => {
                if (!e.target.closest("input")) {
                    e.preventDefault();
                }
            });
        }
        document.addEventListener("dragstart", (e) => e.preventDefault());
        document.addEventListener("visibilitychange", updateCalm);
        if (reducedMotion.addEventListener) {
            reducedMotion.addEventListener("change", updateCalm);
        }
    }

    async function listenAll() {
        const on = (name, fn) => api.event.listen(name, (e) => {
            try {
                fn(e && "payload" in e ? e.payload : e);
            } catch (err) {
                console.error(`[launcher] ${name} handler failed`, err);
            }
        });
        await Promise.all([
            on("phase", onPhase),
            on("progress", onProgress),
            on("server", onServer),
            on("error", onError),
        ]);
    }

    // --------------------------------------------------------------------------------------- start

    const isApp = !!window.__TAURI__;

    function loadMock() {
        return new Promise((resolve, reject) => {
            const s = document.createElement("script");
            s.src = "mock.js";
            s.onload = resolve;
            s.onerror = () => reject(new Error("mock.js could not be loaded"));
            document.head.appendChild(s);
        });
    }

    async function start() {
        api = window.__TAURI__;
        if (!api || !api.core || !api.event) {
            console.error("[launcher] no backend: window.__TAURI__ is missing (withGlobalTauri)");
            return;
        }
        bindUi();
        render();
        try {
            await listenAll();
        } catch (err) {
            console.error("[launcher] event listen failed", err);
        }
        await syncState();
        await (document.fonts ? document.fonts.ready : Promise.resolve());
        app.classList.remove("is-booting");
        updateCalm();

        // preview hook: mock.js scenarios that open a dialog
        const mock = window.__BLEAKHOLD_MOCK__;
        if (mock && mock.open === "install") {
            openInstall();
        } else if (mock && mock.open === "settings") {
            openDrawer();
        }
    }

    bindDom();
    fitWindow();
    window.addEventListener("resize", fitWindow);
    injectIcons(document);
    if (isApp) {
        start();
    } else {
        loadMock().then(start, (err) => console.error("[launcher]", err));
    }
})();
