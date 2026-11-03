//! The signature vector in `tests/vector/`: a manifest signed with OpenSSL 3 exactly as the VPS signs
//! (`openssl pkeyutl -sign -inkey manifest.key -rawin -in manifest.json`, base64), and the public key as
//! the VPS prints it. Its private key was thrown away.

use std::path::PathBuf;

use bleakhold_launcher_core::manifest::Manifest;
use bleakhold_launcher_core::signature::{decode_public_key, verify};
use bleakhold_launcher_core::Code;

fn vector(name: &str) -> Vec<u8> {
    let p = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/vector").join(name);
    std::fs::read(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()))
}

#[test]
fn openssl_signed_manifest_verifies_and_parses() {
    let manifest = vector("manifest.json");
    let sig = vector("manifest.json.sig");
    let key = decode_public_key(&String::from_utf8(vector("pub.b64")).unwrap()).unwrap();
    verify(&manifest, &sig, &key).unwrap();
    let m = Manifest::parse(&manifest).unwrap();
    assert_eq!(m.build, "test");
    assert_eq!(m.files[0].p, "Data/abc.txt");
    assert_eq!(m.launcher.unwrap().version, "0.0.1");
}

#[test]
fn signature_with_line_breaks_still_verifies() {
    // `base64` wraps at 76 columns by default; the launcher ignores whitespace in the .sig.
    let manifest = vector("manifest.json");
    let sig = String::from_utf8(vector("manifest.json.sig")).unwrap();
    let wrapped = format!("{}\n{}\n", &sig.trim()[..76], &sig.trim()[76..]);
    let key = decode_public_key(&String::from_utf8(vector("pub.b64")).unwrap()).unwrap();
    verify(&manifest, wrapped.as_bytes(), &key).unwrap();
}

#[test]
fn any_change_breaks_the_signature() {
    let manifest = vector("manifest.json");
    let sig = vector("manifest.json.sig");
    let key = decode_public_key(&String::from_utf8(vector("pub.b64")).unwrap()).unwrap();

    let mut tampered = manifest.clone();
    let i = tampered.iter().position(|&b| b == b'3').unwrap();
    tampered[i] = b'4';
    assert_eq!(verify(&tampered, &sig, &key).unwrap_err().code, Code::Signature);

    let mut with_newline = manifest.clone();
    with_newline.push(b'\n');
    assert_eq!(verify(&with_newline, &sig, &key).unwrap_err().code, Code::Signature);

    let mut bad_sig = String::from_utf8(sig.clone()).unwrap().into_bytes();
    bad_sig[10] = if bad_sig[10] == b'A' { b'B' } else { b'A' };
    assert_eq!(verify(&manifest, &bad_sig, &key).unwrap_err().code, Code::Signature);

    assert_eq!(verify(&manifest, b"not base64!", &key).unwrap_err().code, Code::Signature);
    assert_eq!(verify(&manifest, b"AAAA", &key).unwrap_err().code, Code::Signature);

    let other = decode_public_key("11qYAYKxCrfVS/7TyWQHOg7hcvPapiMlrwIaaPcHURo=").unwrap();
    assert_eq!(verify(&manifest, &sig, &other).unwrap_err().code, Code::Signature);
}
