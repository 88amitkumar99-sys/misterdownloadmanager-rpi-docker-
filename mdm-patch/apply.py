#!/usr/bin/env python3
"""Mister Download Manager, for the headless server on a phone-first page:

  * a password (chosen on the first visit) instead of the pairing code; any number of devices
  * a speed limit for all downloads together, and one for each download
  * the page lists "resume supported or not" and the time left
  * the same file added again after it stopped or failed goes on from what it has
  * a new page that looks like the design asked for

Usage: python3 apply.py <path to the upstream checkout>
Stops with an error if upstream's code is not the one these edits were written for.
"""
import pathlib
import shutil
import sys

root = pathlib.Path(sys.argv[1])
here = pathlib.Path(__file__).resolve().parent


def edit(path, old, new):
    f = root / path
    text = f.read_text(encoding="utf-8")
    if text.count(old) != 1:
        sys.exit(f"ANCHOR NOT FOUND (x{text.count(old)}) in {path}:\n{old}")
    f.write_text(text.replace(old, new), encoding="utf-8")
    print("edited", path)


# ---- ipc: what the list says ------------------------------------------------------------
API = "crates/ipc/src/api.rs"
edit(
    API,
    "    pub free: Option<u64>,\n}\n\n/// One queue of the list.",
    "    pub free: Option<u64>,\n"
    "    /// The limit for all downloads together, KB/s (the Speed Limiter's); null when off.\n"
    "    #[serde(default)]\n"
    "    pub limit_kb: Option<u64>,\n"
    "    /// The folder downloads go to (each category's folder is inside it).\n"
    "    #[serde(default)]\n"
    "    pub folder: Option<String>,\n"
    "}\n\n/// One queue of the list.",
)
edit(
    API,
    "            free: self.free,\n        })",
    "            free: self.free,\n            limit_kb: self.limit_kb,\n            folder: self.folder.clone(),\n        })",
)
edit(
    API,
    "    pub redownload: bool,\n",
    "    pub redownload: bool,\n"
    "    /// A file: whether its server lets it go on from where it stopped; null until known.\n"
    '    #[serde(default, skip_serializing_if = "Option::is_none")]\n'
    "    pub resumable: Option<bool>,\n"
    "    /// The limit this download has of its own, KB/s; null when it has none.\n"
    '    #[serde(default, skip_serializing_if = "Option::is_none")]\n'
    "    pub limit_kb: Option<u64>,\n",
)
edit(
    "crates/app/src/recent.rs",
    "            && i.remote.is_none(),\n        icon: None,\n",
    "            && i.remote.is_none(),\n"
    "        resumable: i.resumable,\n"
    "        limit_kb: i.own_limit.map(|b| b / 1024),\n"
    "        icon: None,\n",
)

# ---- app ---------------------------------------------------------------------------------
APP = "crates/app/src/app.rs"
edit(
    APP,
    "                    free: self.free_space(),\n                })",
    "                    free: self.free_space(),\n"
    "                    limit_kb: self\n"
    "                        .settings\n"
    "                        .global_limit_on\n"
    "                        .then_some(self.settings.global_limit_kb),\n"
    "                    folder: Some(self.downloads.to_string_lossy().into_owned()),\n"
    "                })",
)
edit(
    APP,
    "            if cmd.url.is_some() || cmd.torrent_file.is_some() {\n"
    "                return self.remote_add(cmd.clone());\n"
    "            }\n"
    "        }\n",
    "            if cmd.url.is_some() || cmd.torrent_file.is_some() {\n"
    "                return self.remote_add(cmd.clone());\n"
    "            }\n"
    "            // The page's speed limit for all downloads together: `size` is KB/s, 0 is off.\n"
    '            if cmd.action.as_deref() == Some("set_limit") {\n'
    "                let kb = cmd.size.unwrap_or(0);\n"
    "                self.settings.global_limit_on = kb > 0;\n"
    "                if kb > 0 {\n"
    "                    self.settings.global_limit_kb = kb;\n"
    "                }\n"
    "                self.apply_speed_limit();\n"
    "                self.dirty = true;\n"
    "                return line(&ipc::api::ActAnswer::default());\n"
    "            }\n"
    "            // The page's speed limit for one download (`ids[0]`): `size` is KB/s, 0 is none.\n"
    '            if cmd.action.as_deref() == Some("set_item_limit") {\n'
    "                let limit = cmd.size.filter(|kb| *kb > 0).map(|kb| kb * 1024);\n"
    "                let Some(&id) = cmd.ids.first() else {\n"
    "                    return line(&ErrorAnswer {\n"
    '                        error: "no such download".into(),\n'
    '                        code: Some("unknown-id".into()),\n'
    "                    });\n"
    "                };\n"
    "                let mut helper = false;\n"
    "                let Some(item) = self.item(id) else {\n"
    "                    return line(&ErrorAnswer {\n"
    '                        error: "no such download".into(),\n'
    '                        code: Some("unknown-id".into()),\n'
    "                    });\n"
    "                };\n"
    "                if let Some(l) = item.live.as_ref() {\n"
    "                    l.dl.set_speed_limit(limit);\n"
    "                    helper = l.dl.is_helper();\n"
    "                }\n"
    "                item.own_limit = limit;\n"
    "                self.dirty = true;\n"
    "                if helper {\n"
    "                    self.helper_own.insert(id, limit);\n"
    "                    self.reapply_helper_limits();\n"
    "                }\n"
    "                return line(&ipc::api::ActAnswer::default());\n"
    "            }\n"
    "        }\n",
)
edit(
    APP,
    "        // Already in the list: no one at the computer to ask, so Options' choice, with \"ask\"\n",
    "        // The same file again after it stopped or failed (its link may have died, or been\n"
    "        // renewed): it goes on from what it has, under the address given, not as a new copy\n"
    "        // that starts over.\n"
    "        let wanted = mdm_engine::naming::sanitize(&mdm_engine::naming::file_name(None, &url));\n"
    "        let earlier = self\n"
    "            .items\n"
    "            .iter()\n"
    "            .find(|i| {\n"
    "                i.live.is_none()\n"
    "                    && i.status != Status::Complete\n"
    "                    && i.downloaded.max(i.best) > 0\n"
    "                    && i.torrent.is_none()\n"
    "                    && i.video.is_none()\n"
    "                    && i.gallery.is_none()\n"
    "                    && i.remote.is_none()\n"
    "                    && (i.url == url || i.file_name == wanted)\n"
    "            })\n"
    "            .map(|i| i.id);\n"
    "        if let Some(id) = earlier {\n"
    "            if let Some(item) = self.item(id) {\n"
    "                item.note(crate::i18n::fmt(\n"
    '                    crate::i18n::t("Address changed to {host}"),\n'
    '                    &[("host", &crate::i18n::ltr(url.host_str().unwrap_or("?")))],\n'
    "                ));\n"
    "                take_address(item, url.clone());\n"
    "            }\n"
    "            self.rewrite_state(id, false, Some(url.clone()));\n"
    "            self.start(id, true);\n"
    "            self.dirty = true;\n"
    "            return line(&AddAnswer {\n"
    "                id: Some(id),\n"
    "                pending: false,\n"
    "            });\n"
    "        }\n"
    "        // Already in the list: no one at the computer to ask, so Options' choice, with \"ask\"\n",
)

# ---- remote: the password and the limits -------------------------------------------------
LIB = "crates/remote/src/lib.rs"
edit(LIB, "pub mod pairing;\n", "pub mod pairing;\nmod password;\n")
edit(
    LIB,
    "    pairing: Mutex<pairing::Pairing>,\n}",
    "    pairing: Mutex<pairing::Pairing>,\n    password: Mutex<password::Password>,\n}",
)
edit(
    LIB,
    '        let devices = devices::Devices::load(Some(dir.join("devices.json")));\n',
    '        let devices = devices::Devices::load(Some(dir.join("devices.json")));\n'
    '        let password = password::Password::load(Some(dir.join("password.json")));\n',
)
edit(
    LIB,
    "                pairing: Mutex::default(),\n",
    "                pairing: Mutex::default(),\n                password: Mutex::new(password),\n",
)
shutil.copyfile(here / "password.rs", root / "crates/remote/src/password.rs")
print("copied password.rs")

HTTP = "crates/remote/src/http.rs"
edit(HTTP, "use crate::pairing::Check;\n", "use crate::pairing::Check;\nuse crate::password::Login;\n")
edit(
    HTTP,
    '        .route("/api/pair", post(pair))\n',
    '        .route("/api/pair", post(pair))\n'
    '        .route("/api/auth", get(auth_state))\n'
    '        .route("/api/setup", post(setup))\n'
    '        .route("/api/login", post(login))\n',
)
edit(
    HTTP,
    '        .route("/api/queue", post(queue))\n',
    '        .route("/api/queue", post(queue))\n        .route("/api/limit", post(limit))\n',
)
edit(
    HTTP,
    "async fn list(s: S, _: Paired) -> Response {\n",
    '''/// Does a password exist yet? (The page asks before it shows a form.)
async fn auth_state(s: S) -> Response {
    let set = s.inner.password.lock().unwrap().is_set();
    json(serde_json::json!({ "set": set }).to_string())
}

#[derive(Deserialize)]
struct PasswordBody {
    password: String,
    #[serde(default)]
    name: String,
}

/// A device that has given the right password: its own token, as a paired device has.
fn signed_in(s: &State, name: &str, ip: std::net::IpAddr) -> Response {
    let (device, token) = s.inner.devices.lock().unwrap().add(name);
    tracing::info!("remote control: {} signed in ({})", device.name, ip);
    s.inner.sink.wake();
    json(serde_json::json!({ "token": token, "id": device.id, "name": device.name }).to_string())
}

/// The first visit: the password is chosen (only while none is set).
async fn setup(
    s: S,
    ConnectInfo(peer): ConnectInfo<Peer>,
    axum::Json(b): axum::Json<PasswordBody>,
) -> Response {
    let set = s.inner.password.lock().unwrap().set(&b.password);
    match set {
        Ok(()) => signed_in(&s, &b.name, peer.0.ip()),
        Err("password-set") => error(StatusCode::CONFLICT, "password-set"),
        Err(code) => error(StatusCode::BAD_REQUEST, code),
    }
}

/// A new device signs in with the password.
async fn login(
    s: S,
    ConnectInfo(peer): ConnectInfo<Peer>,
    axum::Json(b): axum::Json<PasswordBody>,
) -> Response {
    let check = s
        .inner
        .password
        .lock()
        .unwrap()
        .check(&b.password, peer.0.ip());
    match check {
        Login::Right => signed_in(&s, &b.name, peer.0.ip()),
        Login::Wrong { left } => {
            tracing::info!("remote control: a wrong password ({})", peer.0.ip());
            let body = serde_json::json!({
                "error": "wrong password", "code": "wrong-password", "left": left
            });
            (
                StatusCode::FORBIDDEN,
                [(header::CONTENT_TYPE, "application/json")],
                body.to_string(),
            )
                .into_response()
        }
        Login::NotSet => error(StatusCode::GONE, "no-password"),
        Login::TooSoon => error(StatusCode::TOO_MANY_REQUESTS, "too-soon"),
    }
}

async fn list(s: S, _: Paired) -> Response {
''',
)
edit(
    HTTP,
    "/// The device unpairs itself (the page's Forget this device).\n",
    '''#[derive(Deserialize)]
struct LimitBody {
    /// KB/s; 0 takes the limit off.
    kb: u64,
    /// One download's limit; without it, the limit for all downloads together.
    #[serde(default)]
    id: Option<u64>,
}

async fn limit(s: S, _: Paired, axum::Json(b): axum::Json<LimitBody>) -> Response {
    if b.kb > 10_000_000 {
        return error(StatusCode::BAD_REQUEST, "bad-limit");
    }
    let cmd = match b.id {
        Some(id) => mdm_ipc::Command {
            action: Some("set_item_limit".into()),
            ids: vec![id],
            size: Some(b.kb),
            ..Default::default()
        },
        None => mdm_ipc::Command {
            action: Some("set_limit".into()),
            size: Some(b.kb),
            ..Default::default()
        },
    };
    ask(&s, cmd).await
}

/// The device unpairs itself (the page's Forget this device).
''',
)

# ---- the folder downloads go to, chosen on the page (setup and later) ---------------------
edit(
    "crates/app/src/settings.rs",
    "    pub remote_listen: String,\n",
    "    pub remote_listen: String,\n"
    "    /// The folder downloads go to, chosen on the remote control's page (\"\": the one the\n"
    "    /// server was started with).\n"
    "    pub downloads_root: String,\n",
)
edit(
    "crates/app/src/settings.rs",
    "            remote_listen: String::new(),\n",
    "            remote_listen: String::new(),\n            downloads_root: String::new(),\n",
)
edit(
    APP,
    "        if let Some(d) = downloads {\n            self.downloads = d;\n        }\n",
    "        if let Some(d) = downloads {\n            self.downloads = d;\n        }\n"
    "        // The folder chosen on the page comes before the one the server was started with, as\n"
    "        // long as it can still be used.\n"
    "        let chosen = PathBuf::from(self.settings.downloads_root.trim());\n"
    "        if chosen.is_absolute() && std::fs::create_dir_all(&chosen).is_ok() {\n"
    "            self.downloads = chosen;\n"
    "        }\n",
)
edit(
    APP,
    "            // The page's speed limit for one download (`ids[0]`): `size` is KB/s, 0 is none.\n",
    "            // The page's choice of the folder downloads go to (`dir`): made if it isn't there,\n"
    "            // and a file written in it, so a folder that can't be used is told at once.\n"
    '            if cmd.action.as_deref() == Some("set_folder") {\n'
    "                let dir = PathBuf::from(cmd.dir.clone().unwrap_or_default().trim());\n"
    "                let no_parent = dir\n"
    "                    .components()\n"
    "                    .all(|c| !matches!(c, std::path::Component::ParentDir));\n"
    "                if !dir.is_absolute() || !no_parent {\n"
    "                    return line(&ErrorAnswer {\n"
    '                        error: "not a full folder path".into(),\n'
    '                        code: Some("bad-folder".into()),\n'
    "                    });\n"
    "                }\n"
    '                let probe = dir.join(format!(".mdm-write-test-{}", std::process::id()));\n'
    "                let usable = std::fs::create_dir_all(&dir)\n"
    "                    .and_then(|()| std::fs::write(&probe, b\"\"))\n"
    "                    .is_ok();\n"
    "                let _ = std::fs::remove_file(&probe);\n"
    "                if !usable {\n"
    "                    return line(&ErrorAnswer {\n"
    '                        error: "MDM cannot write in this folder".into(),\n'
    '                        code: Some("folder-not-writable".into()),\n'
    "                    });\n"
    "                }\n"
    "                self.settings.downloads_root = dir.to_string_lossy().into_owned();\n"
    "                self.downloads = dir;\n"
    "                self.dirty = true;\n"
    "                return line(&ipc::api::ActAnswer::default());\n"
    "            }\n"
    "            // The page's speed limit for one download (`ids[0]`): `size` is KB/s, 0 is none.\n",
)
edit(
    HTTP,
    '        .route("/api/limit", post(limit))\n',
    '        .route("/api/limit", post(limit))\n'
    '        .route("/api/dirs", get(dirs))\n'
    '        .route("/api/folder", post(folder))\n',
)
edit(
    HTTP,
    "/// The device unpairs itself (the page's Forget this device).\n",
    """#[derive(Deserialize)]
struct FolderBody {
    path: String,
}

/// The page's choice of the folder downloads go to.
async fn folder(s: S, _: Paired, axum::Json(b): axum::Json<FolderBody>) -> Response {
    if b.path.len() > 4096 {
        return error(StatusCode::BAD_REQUEST, "bad-folder");
    }
    ask(
        &s,
        mdm_ipc::Command {
            action: Some("set_folder".into()),
            dir: Some(b.path),
            ..Default::default()
        },
    )
    .await
}

#[derive(Deserialize)]
struct DirsQuery {
    #[serde(default)]
    path: String,
}

/// Folders a server's own system keeps: not offered to a person choosing where downloads go.
const SYSTEM_DIRS: [&str; 14] = [
    "proc", "sys", "dev", "run", "etc", "bin", "sbin", "lib", "lib32", "lib64", "libx32", "usr",
    "var", "boot",
];

/// The folders inside a folder: the page's folder chooser. Names only, and only for a device
/// that has signed in.
async fn dirs(_: Paired, Query(q): Query<DirsQuery>) -> Response {
    let typed = q.path.trim();
    let path = std::path::PathBuf::from(if typed.is_empty() { "/" } else { typed });
    let no_parent = path
        .components()
        .all(|c| !matches!(c, std::path::Component::ParentDir));
    if !path.is_absolute() || !no_parent {
        return error(StatusCode::BAD_REQUEST, "bad-folder");
    }
    let Ok(read) = std::fs::read_dir(&path) else {
        return error(StatusCode::NOT_FOUND, "no-folder");
    };
    let at_root = path == std::path::Path::new("/");
    let mut names: Vec<String> = read
        .filter_map(Result::ok)
        .filter(|e| e.path().is_dir())
        .filter_map(|e| e.file_name().into_string().ok())
        .filter(|n| !n.starts_with('.') && !(at_root && SYSTEM_DIRS.contains(&n.as_str())))
        .collect();
    names.sort_by_key(|n| n.to_lowercase());
    names.truncate(500);
    let parent = path.parent().map(|p| p.to_string_lossy().into_owned());
    json(
        serde_json::json!({
            "path": path.to_string_lossy(), "parent": parent, "dirs": names
        })
        .to_string(),
    )
}

/// The device unpairs itself (the page's Forget this device).
""",
)

# ---- one download after another (a queue of one), and how many at once, from the page --------
edit(
    "crates/app/src/settings.rs",
    "    pub downloads_root: String,\n",
    "    pub downloads_root: String,\n"
    "    /// How many downloads of a queue run at the same time (the page's choice; 1 is one after\n"
    "    /// another).\n"
    "    pub parallel: u32,\n",
)
edit(
    "crates/app/src/settings.rs",
    "            downloads_root: String::new(),\n",
    "            downloads_root: String::new(),\n            parallel: 1,\n",
)
edit(
    API,
    "    pub folder: Option<String>,\n}",
    "    pub folder: Option<String>,\n"
    "    /// How many downloads of a queue run at the same time.\n"
    "    #[serde(default)]\n"
    "    pub parallel: Option<u32>,\n"
    "}",
)
edit(
    API,
    "            folder: self.folder.clone(),\n        })",
    "            folder: self.folder.clone(),\n            parallel: self.parallel,\n        })",
)
edit(
    APP,
    "                    folder: Some(self.downloads.to_string_lossy().into_owned()),\n                })",
    "                    folder: Some(self.downloads.to_string_lossy().into_owned()),\n"
    "                    parallel: Some(self.settings.parallel),\n"
    "                })",
)
edit(
    APP,
    "            self.downloads = chosen;\n        }\n",
    "            self.downloads = chosen;\n        }\n"
    "        // One download after another, unless the page's choice says otherwise.\n"
    "        let parallel = self.settings.parallel.clamp(1, 8);\n"
    "        for q in &mut self.queues {\n"
    "            q.files_at_once = parallel;\n"
    "        }\n",
)
edit(
    APP,
    "            // The page's speed limit for one download (`ids[0]`): `size` is KB/s, 0 is none.\n",
    "            // The page's choice of how many downloads of a queue run at the same time (`size`).\n"
    '            if cmd.action.as_deref() == Some("set_parallel") {\n'
    "                let n = cmd.size.unwrap_or(1).clamp(1, 8) as u32;\n"
    "                self.settings.parallel = n;\n"
    "                for q in &mut self.queues {\n"
    "                    q.files_at_once = n;\n"
    "                }\n"
    "                self.dirty = true;\n"
    "                self.tick_queues();\n"
    "                return line(&ipc::api::ActAnswer::default());\n"
    "            }\n"
    "            // The page's speed limit for one download (`ids[0]`): `size` is KB/s, 0 is none.\n",
)
edit(
    HTTP,
    '        .route("/api/folder", post(folder))\n',
    '        .route("/api/folder", post(folder))\n        .route("/api/parallel", post(parallel))\n',
)
edit(
    HTTP,
    "/// The device unpairs itself (the page's Forget this device).\n",
    """#[derive(Deserialize)]
struct ParallelBody {
    /// How many downloads of a queue run at the same time.
    n: u64,
}

async fn parallel(s: S, _: Paired, axum::Json(b): axum::Json<ParallelBody>) -> Response {
    ask(
        &s,
        mdm_ipc::Command {
            action: Some("set_parallel".into()),
            size: Some(b.n),
            ..Default::default()
        },
    )
    .await
}

/// The device unpairs itself (the page's Forget this device).
""",
)

# ---- a failed download keeps what it had on the page; a download can wait for a time -----------
edit(
    "crates/app/src/model.rs",
    "        self.downloaded = shown_downloaded(live_now, s.downloaded, self.downloaded);\n",
    "        // A failure that came before anything was read (a link that died, on going on from a\n"
    "        // saved state) knows nothing of what is already on disk: what the file had stays shown.\n"
    "        self.downloaded = if s.state == State::Failed {\n"
    "            s.downloaded.max(self.downloaded)\n"
    "        } else {\n"
    "            shown_downloaded(live_now, s.downloaded, self.downloaded)\n"
    "        };\n",
)
edit(
    "crates/ipc/src/lib.rs",
    "    pub size: Option<u64>,\n    pub mime: Option<String>,\n",
    "    pub size: Option<u64>,\n"
    "    /// From the remote control's page: the download waits for this time (seconds since 1970)\n"
    "    /// before it starts.\n"
    "    pub at: Option<u64>,\n"
    "    pub mime: Option<String>,\n",
)
edit(
    "crates/app/src/settings.rs",
    "    pub parallel: u32,\n",
    "    pub parallel: u32,\n"
    "    /// Downloads waiting to start at a time: (download id, seconds since 1970).\n"
    "    pub scheduled: Vec<(u64, u64)>,\n",
)
edit(
    "crates/app/src/settings.rs",
    "            parallel: 1,\n",
    "            parallel: 1,\n            scheduled: Vec::new(),\n",
)
edit(
    API,
    "    pub parallel: Option<u32>,\n}",
    "    pub parallel: Option<u32>,\n"
    "    /// Downloads waiting to start at a time: (download id, seconds since 1970).\n"
    '    #[serde(default, skip_serializing_if = "Vec::is_empty")]\n'
    "    pub scheduled: Vec<(u64, u64)>,\n"
    "}",
)
edit(
    API,
    "            parallel: self.parallel,\n        })",
    "            parallel: self.parallel,\n            scheduled: self.scheduled.clone(),\n        })",
)
edit(
    APP,
    "                    parallel: Some(self.settings.parallel),\n                })",
    "                    parallel: Some(self.settings.parallel),\n"
    "                    scheduled: self.settings.scheduled.clone(),\n"
    "                })",
)
edit(
    APP,
    "        cmd.remote = false;\n        let id = self.push_item(\n",
    "        let at = cmd.at.filter(|t| *t > 0);\n        cmd.remote = false;\n        let id = self.push_item(\n",
)
edit(
    APP,
    "        self.number_at_start(id);\n"
    "        match queue {\n"
    "            Some(q) => self.queues[q].items.push(id),\n"
    "            None => self.start(id, false),\n"
    "        }\n",
    "        self.number_at_start(id);\n"
    "        // At a set time: it waits, outside the queue, until the time comes (`tick_queues`).\n"
    "        if let Some(when) = at {\n"
    "            self.settings.scheduled.push((id, when));\n"
    "        } else {\n"
    "            match queue {\n"
    "                Some(q) => self.queues[q].items.push(id),\n"
    "                None => self.start(id, false),\n"
    "            }\n"
    "        }\n",
)
edit(
    APP,
    "    fn tick_queues(&mut self) {\n        use chrono::{Datelike, Timelike};\n",
    "    fn tick_queues(&mut self) {\n"
    "        use chrono::{Datelike, Timelike};\n"
    "        // Downloads set to start at a time: when it comes they join the main queue, which\n"
    "        // starts (one download after another).\n"
    "        if !self.settings.scheduled.is_empty() {\n"
    "            let now = chrono::Utc::now().timestamp().max(0) as u64;\n"
    "            let due: Vec<u64> = self\n"
    "                .settings\n"
    "                .scheduled\n"
    "                .iter()\n"
    "                .filter(|(_, at)| *at <= now)\n"
    "                .map(|(id, _)| *id)\n"
    "                .collect();\n"
    "            if !due.is_empty() {\n"
    "                self.settings.scheduled.retain(|(_, at)| *at > now);\n"
    "                for id in due {\n"
    "                    let waiting = self.items.iter().any(|i| {\n"
    "                        i.id == id\n"
    "                            && matches!(i.status, Status::Queued | Status::Stopped | Status::Error)\n"
    "                    });\n"
    "                    if waiting && let Some(q) = self.queues.first_mut() {\n"
    "                        if !q.items.contains(&id) {\n"
    "                            q.items.push(id);\n"
    "                        }\n"
    "                        q.running = true;\n"
    "                        self.stopped_by_hand.remove(&id);\n"
    "                    }\n"
    "                }\n"
    "                self.dirty = true;\n"
    "            }\n"
    "        }\n",
)
edit(
    APP,
    "            // The page's speed limit for one download (`ids[0]`): `size` is KB/s, 0 is none.\n",
    "            // The page's change of when a download starts (`ids[0]`; `size`: seconds since 1970,\n"
    "            // 0 takes the wait away).\n"
    '            if cmd.action.as_deref() == Some("set_schedule") {\n'
    "                if let Some(&id) = cmd.ids.first() {\n"
    "                    self.settings.scheduled.retain(|(i, _)| *i != id);\n"
    "                    if let Some(at) = cmd.size.filter(|t| *t > 0) {\n"
    "                        let open = self\n"
    "                            .items\n"
    "                            .iter()\n"
    "                            .any(|i| i.id == id && i.status != Status::Complete);\n"
    "                        if open {\n"
    "                            // It waits for its time: out of the queues, stopped if it runs.\n"
    "                            for q in &mut self.queues {\n"
    "                                q.items.retain(|x| *x != id);\n"
    "                            }\n"
    "                            self.stop_by_hand(id);\n"
    "                            self.settings.scheduled.push((id, at));\n"
    "                        }\n"
    "                    }\n"
    "                    self.dirty = true;\n"
    "                }\n"
    "                return line(&ipc::api::ActAnswer::default());\n"
    "            }\n"
    "            // The page's speed limit for one download (`ids[0]`): `size` is KB/s, 0 is none.\n",
)
edit(
    HTTP,
    "    /// Start now (else it waits in `queue`, the main queue by default).\n    #[serde(default)]\n    start: bool,\n}\n",
    "    /// Start now (else it waits in `queue`, the main queue by default).\n    #[serde(default)]\n    start: bool,\n"
    "    /// Wait for this time (seconds since 1970) before it starts.\n"
    "    #[serde(default)]\n"
    "    at: Option<u64>,\n"
    "}\n",
)
edit(
    HTTP,
    "            later: !b.start,\n            silent: true,\n",
    "            later: !b.start,\n            at: b.at,\n            silent: true,\n",
)
edit(
    HTTP,
    '        .route("/api/parallel", post(parallel))\n',
    '        .route("/api/parallel", post(parallel))\n        .route("/api/schedule", post(schedule))\n',
)
edit(
    HTTP,
    "/// The device unpairs itself (the page's Forget this device).\n",
    """#[derive(Deserialize)]
struct ScheduleBody {
    id: u64,
    /// Seconds since 1970; 0 takes the wait away.
    #[serde(default)]
    at: u64,
}

async fn schedule(s: S, _: Paired, axum::Json(b): axum::Json<ScheduleBody>) -> Response {
    ask(
        &s,
        mdm_ipc::Command {
            action: Some("set_schedule".into()),
            ids: vec![b.id],
            size: Some(b.at),
            ..Default::default()
        },
    )
    .await
}

/// The device unpairs itself (the page's Forget this device).
""",
)

# ---- a failed or stopped download keeps showing the most it had downloaded ------------------
edit(
    "crates/app/src/model.rs",
    "    pub downloaded: u64,\n    pub status: Status,\n    pub category: Category,\n",
    "    pub downloaded: u64,\n"
    "    /// The most it had downloaded before a try started over (a server that cannot go on from\n"
    "    /// where it stopped): what a failed or stopped download still shows in the page's list.\n"
    "    #[serde(default)]\n"
    "    pub best: u64,\n"
    "    pub status: Status,\n    pub category: Category,\n",
)
edit(
    "crates/app/src/model.rs",
    "            size: None,\n            downloaded: 0,\n            status: Status::Queued,\n",
    "            size: None,\n            downloaded: 0,\n            best: 0,\n            status: Status::Queued,\n",
)
edit(
    "crates/app/src/model.rs",
    "        // A failure that came before anything was read (a link that died, on going on from a\n",
    "        self.best = self.best.max(self.downloaded);\n"
    "        // A failure that came before anything was read (a link that died, on going on from a\n",
)
edit(
    APP,
    "        let dl = if fresh {\n            item.downloaded = 0;\n",
    "        let dl = if fresh {\n            item.downloaded = 0;\n            item.best = 0;\n",
)
edit(
    "crates/app/src/recent.rs",
    "        downloaded: i.downloaded,\n",
    "        // A failed or stopped download shows the most it had, though a try that started over\n"
    "        // has read less so far.\n"
    "        downloaded: if matches!(i.status, Status::Error | Status::Stopped) {\n"
    "            i.downloaded.max(i.best)\n"
    "        } else {\n"
    "            i.downloaded\n"
    "        },\n",
)

# ---- resume: told only once the server has been asked for a part from the middle of the file,
#      not from the first answer's `Accept-Ranges` or a 206 for the start (which prove nothing) ----
ENGINE = "crates/engine/src/download.rs"
edit(
    ENGINE,
    "    v.resumable = (ranges == RANGES_YES)\n        .then_some(true)\n        .or(size.is_none().then_some(false));\n",
    "    // Resume is told once a part from the middle of the file has been answered (206) or\n"
    "    // refused (`request`): the first answer's `Accept-Ranges`, or a 206 for the start, proves\n"
    "    // nothing. Only a file of unknown length is known not to resume.\n"
    "    let _ = ranges;\n"
    "    v.resumable = size.is_none().then_some(false);\n",
)
edit(
    ENGINE,
    "        if learned {\n            self.shared.view.lock().unwrap().resumable = Some(yes);\n        }\n",
    "        if learned && !yes {\n            self.shared.view.lock().unwrap().resumable = Some(false);\n        }\n",
)
edit(
    ENGINE,
    "        StatusCode::PARTIAL_CONTENT => {\n            ctx.learn_ranges(true);\n            ctx.range_answered.notify_one();\n        }\n",
    "        StatusCode::PARTIAL_CONTENT => {\n            ctx.learn_ranges(true);\n"
    "            // A part from the middle of the file answered: the download can go on.\n"
    "            if from > 0 {\n                ctx.shared.view.lock().unwrap().resumable = Some(true);\n            }\n"
    "            ctx.range_answered.notify_one();\n        }\n",
)
edit(
    ENGINE,
    "                if from > 0 {\n                    ctx.learn_ranges(true);\n                }\n",
    "                if from > 0 {\n                    ctx.learn_ranges(true);\n                    ctx.shared.view.lock().unwrap().resumable = Some(true);\n                }\n",
)
edit(
    ENGINE,
    "        v.size = Some(saved.size);\n        v.resumable = Some(true);\n",
    "        v.size = Some(saved.size);\n        v.resumable = None;\n",
)

# ---- the worker's file, served beside the page ----
edit(
    HTTP,
    '        .route(\n            "/app.css",\n',
    '        .route(\n            "/ticker.js",\n            get(|| async { asset("text/javascript; charset=utf-8", TICKER) }),\n        )\n'
    '        .route(\n            "/app.css",\n',
)
edit(
    HTTP,
    'static STYLE: &str = include_str!("../web/app.css");\n',
    'static STYLE: &str = include_str!("../web/app.css");\nstatic TICKER: &str = include_str!("../web/ticker.js");\n',
)

# ---- the page ----------------------------------------------------------------------------
for name in ("index.html", "app.css", "app.js", "ticker.js"):
    shutil.copyfile(here / "web" / name, root / "crates/remote/web" / name)
    print("copied", name)
print("done")
