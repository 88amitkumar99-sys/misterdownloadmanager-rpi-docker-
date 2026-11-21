//! The page's password (`remote/password.json`, readable by the user only): chosen on the
//! first visit to the page, asked for from every new device after that. The file holds a salt
//! and the password's PBKDF2-HMAC-SHA256, never the password. A device that has signed in keeps
//! a token of its own, as a paired device does (`devices.rs`), so any number of devices can be
//! signed in at once.

use std::collections::HashMap;
use std::net::IpAddr;
use std::num::NonZeroU32;
use std::path::PathBuf;
use std::time::{Duration, Instant};

use aws_lc_rs::pbkdf2;
use serde::{Deserialize, Serialize};

/// PBKDF2 rounds: slow enough to make guessing from the file hard, quick on a Raspberry Pi 3.
const ROUNDS: u32 = 100_000;
/// The shortest and the longest password taken (characters).
pub const MIN_LEN: usize = 4;
pub const MAX_LEN: usize = 200;
/// Wrong passwords from one address before it has to wait, and for how long.
const TRIES: u32 = 5;
const WAIT: Duration = Duration::from_secs(60);

#[derive(Clone, Serialize, Deserialize)]
struct Saved {
    salt: String,
    hash: String,
    rounds: u32,
}

#[derive(Default)]
pub struct Password {
    path: Option<PathBuf>,
    saved: Option<Saved>,
    /// Wrong tries by address: how many, and when the last was.
    wrong: HashMap<IpAddr, (u32, Instant)>,
}

/// What a sign-in with a password came to.
#[derive(Debug, PartialEq, Eq)]
pub enum Login {
    Right,
    Wrong { left: u32 },
    /// No password is set yet.
    NotSet,
    /// Too many wrong ones from this address: wait a minute.
    TooSoon,
}

impl Password {
    /// The password kept at `path` (None: in memory only, for tests).
    pub fn load(path: Option<PathBuf>) -> Password {
        let saved = path
            .as_ref()
            .and_then(|p| std::fs::read(p).ok())
            .and_then(|b| serde_json::from_slice(&b).ok());
        Password {
            path,
            saved,
            wrong: HashMap::new(),
        }
    }

    pub fn is_set(&self) -> bool {
        self.saved.is_some()
    }

    /// Set the password, while none is set. The error is the code the page shows.
    pub fn set(&mut self, password: &str) -> Result<(), &'static str> {
        if self.saved.is_some() {
            return Err("password-set");
        }
        let len = password.chars().count();
        if len < MIN_LEN {
            return Err("password-short");
        }
        if len > MAX_LEN {
            return Err("password-long");
        }
        let rounds = NonZeroU32::new(ROUNDS).ok_or("failed")?;
        let salt = crate::devices::random(16);
        let mut hash = [0u8; 32];
        pbkdf2::derive(
            pbkdf2::PBKDF2_HMAC_SHA256,
            rounds,
            &salt,
            password.as_bytes(),
            &mut hash,
        );
        let saved = Saved {
            salt: hex::encode(&salt),
            hash: hex::encode(hash),
            rounds: ROUNDS,
        };
        if let Some(path) = &self.path
            && let Ok(json) = serde_json::to_vec_pretty(&saved)
        {
            if let Some(dir) = path.parent() {
                let _ = mdm_ipc::private_dir(dir);
            }
            if let Err(e) = mdm_ipc::private_write(path, &json) {
                tracing::warn!("remote control: the password could not be saved: {e}");
            }
        }
        self.saved = Some(saved);
        Ok(())
    }

    /// Is `password` the one set? Wrong tries are counted by address.
    pub fn check(&mut self, password: &str, peer: IpAddr) -> Login {
        let Some(saved) = self.saved.clone() else {
            return Login::NotSet;
        };
        if let Some((n, at)) = self.wrong.get(&peer).copied()
            && n >= TRIES
        {
            if at.elapsed() < WAIT {
                return Login::TooSoon;
            }
            self.wrong.remove(&peer);
        }
        let right = password.len() <= 4 * MAX_LEN
            && match (
                hex::decode(&saved.salt),
                hex::decode(&saved.hash),
                NonZeroU32::new(saved.rounds),
            ) {
                (Ok(salt), Ok(hash), Some(rounds)) => pbkdf2::verify(
                    pbkdf2::PBKDF2_HMAC_SHA256,
                    rounds,
                    &salt,
                    password.as_bytes(),
                    &hash,
                )
                .is_ok(),
                _ => false,
            };
        if right {
            self.wrong.remove(&peer);
            return Login::Right;
        }
        if self.wrong.len() > 1000 {
            self.wrong.clear();
        }
        let n = self.wrong.get(&peer).map_or(0, |(n, _)| *n) + 1;
        self.wrong.insert(peer, (n, Instant::now()));
        Login::Wrong {
            left: TRIES.saturating_sub(n),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn set_once_check_and_wait() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("password.json");
        let ip: IpAddr = "192.168.1.5".parse().unwrap();
        let mut p = Password::load(Some(path.clone()));
        assert_eq!(p.check("abcd", ip), Login::NotSet);
        assert_eq!(p.set("abc"), Err("password-short"));
        assert_eq!(p.set("secret word"), Ok(()));
        assert_eq!(p.set("another one"), Err("password-set"));
        // The file holds no password.
        assert!(
            !std::fs::read_to_string(&path)
                .unwrap()
                .contains("secret word")
        );
        // Read back by a new start.
        let mut p = Password::load(Some(path));
        assert!(p.is_set());
        assert_eq!(p.check("secret word", ip), Login::Right);
        for left in (0..TRIES).rev() {
            assert_eq!(p.check("wrong", ip), Login::Wrong { left });
        }
        assert_eq!(p.check("secret word", ip), Login::TooSoon);
        // Another address is not made to wait.
        let other: IpAddr = "192.168.1.6".parse().unwrap();
        assert_eq!(p.check("secret word", other), Login::Right);
    }
}
