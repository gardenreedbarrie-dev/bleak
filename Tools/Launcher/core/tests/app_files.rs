//! Checks on the app's files that can run on any machine (the app itself only builds on Windows CI):
//! `launcher.json` parses, the versions agree, the window and CSP are what DESIGN.md says, and the window
//! is granted nothing beyond what it needs.

use std::path::PathBuf;

use bleakhold_launcher_core::signature::PLACEHOLDER_KEY;
use bleakhold_launcher_core::LauncherConfig;
use serde_json::{json, Value};

fn app_file(name: &str) -> String {
    let p = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../app").join(name);
    std::fs::read_to_string(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()))
}

fn json_file(name: &str) -> Value {
    serde_json::from_str(&app_file(name)).unwrap_or_else(|e| panic!("{name}: {e}"))
}

#[test]
fn launcher_json_is_valid() {
    let c = LauncherConfig::parse(&app_file("launcher.json")).unwrap();
    assert_eq!(c.base_url, "http://185.217.124.41:8090/");
    assert_eq!(c.realmlist, "185.217.124.41");
    // Either still the placeholder (the launcher then refuses to trust anything) or a real key.
    assert!(c.public_key == PLACEHOLDER_KEY || c.key().is_ok(), "public_key is neither the placeholder nor valid");
}

#[test]
fn versions_agree() {
    let cargo = app_file("Cargo.toml");
    let cargo_version = cargo
        .lines()
        .find_map(|l| l.strip_prefix("version = \"").and_then(|v| v.strip_suffix('"')))
        .expect("version in app/Cargo.toml");
    let conf = json_file("tauri.conf.json");
    assert_eq!(conf["version"], json!(cargo_version));
    assert!(semver::Version::parse(cargo_version).is_ok());
}

#[test]
fn window_and_security_follow_the_contract() {
    let conf = json_file("tauri.conf.json");
    assert_eq!(conf["build"]["frontendDist"], json!("../ui"));
    assert_eq!(conf["app"]["withGlobalTauri"], json!(true));
    assert_eq!(conf["bundle"]["active"], json!(false));
    let w = &conf["app"]["windows"][0];
    assert_eq!(w["label"], json!("main"));
    assert_eq!((w["width"].as_u64(), w["height"].as_u64()), (Some(1180), Some(700)));
    for (key, want) in [("decorations", false), ("resizable", false), ("maximizable", false), ("shadow", true)] {
        assert_eq!(w[key], json!(want), "{key}");
    }
    let csp_map = conf["app"]["security"]["csp"].as_object().expect("the CSP as a directive map");
    let csp: String = csp_map.iter().map(|(k, v)| format!("{k} {}; ", v.as_str().unwrap())).collect();
    assert!(csp.contains("default-src 'self'") && csp.contains("script-src 'self'"));
    assert!(!csp.contains("unsafe") && !csp.contains('*'), "{csp}");
}

#[test]
fn capabilities_grant_only_what_the_window_needs() {
    let cap = json_file("capabilities/default.json");
    assert_eq!(cap["windows"], json!(["main"]));
    let mut names: Vec<String> = cap["permissions"]
        .as_array()
        .unwrap()
        .iter()
        .map(|p| p.as_str().map(String::from).unwrap_or_else(|| p["identifier"].as_str().unwrap().to_string()))
        .collect();
    names.sort();
    assert_eq!(
        names,
        [
            "core:event:allow-listen",
            "core:event:allow-unlisten",
            "core:window:allow-close",
            "core:window:allow-minimize",
            "core:window:allow-start-dragging",
            "dialog:allow-open",
            "opener:allow-open-url",
        ]
    );
    let opener = cap["permissions"].as_array().unwrap().iter().find(|p| p["identifier"] == "opener:allow-open-url");
    let urls: Vec<&str> =
        opener.unwrap()["allow"].as_array().unwrap().iter().map(|a| a["url"].as_str().unwrap()).collect();
    assert_eq!(urls, ["https://*", "http://*"]);
}
