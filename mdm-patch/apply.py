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
    "}\n\n/// One queue of the list.",
)
edit(
    API,
    "            free: self.free,\n        })",
    "            free: self.free,\n            limit_kb: self.limit_kb,\n        })",
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
    "                    && i.downloaded > 0\n"
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

# ---- the page ----------------------------------------------------------------------------
for name in ("index.html", "app.css", "app.js"):
    shutil.copyfile(here / "web" / name, root / "crates/remote/web" / name)
    print("copied", name)
print("done")
