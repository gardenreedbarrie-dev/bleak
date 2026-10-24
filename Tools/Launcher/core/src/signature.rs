//! Ed25519 (RFC 8032) verification of `manifest.json` against `manifest.json.sig` (DESIGN.md "Manifest",
//! "Signature"). Verify only: the launcher never holds a private key.

use base64::engine::general_purpose::STANDARD;
use base64::Engine as _;
use ed25519_dalek::{Signature, VerifyingKey};

use crate::error::{Error, Result};

/// Placeholder `launcher.json` carries until the VPS key is filled in.
pub const PLACEHOLDER_KEY: &str = "REPLACE_WITH_VPS_PUBLIC_KEY";

fn strip_ws(s: &[u8]) -> Vec<u8> {
    s.iter().copied().filter(|b| !b.is_ascii_whitespace()).collect()
}

/// Reads the public key: base64 of the raw 32 bytes (what
/// `openssl pkey -in manifest.key -pubout -outform DER | tail -c 32 | base64` prints).
pub fn decode_public_key(b64: &str) -> std::result::Result<VerifyingKey, String> {
    let t = b64.trim();
    if t.is_empty() || t == PLACEHOLDER_KEY {
        return Err("This launcher was built without the realm's signing key, so it cannot trust any update. \
                    Ask the realm's admin for a properly built launcher."
            .into());
    }
    let raw = STANDARD.decode(strip_ws(t.as_bytes())).map_err(|e| format!("public key is not base64: {e}"))?;
    let bytes: [u8; 32] =
        raw.as_slice().try_into().map_err(|_| format!("public key must be 32 bytes, got {}", raw.len()))?;
    VerifyingKey::from_bytes(&bytes).map_err(|e| format!("public key is not a valid Ed25519 key: {e}"))
}

/// Checks `sig_file` (base64 of the 64-byte signature; line breaks and spaces are ignored) over the exact
/// bytes of `manifest`.
pub fn verify(manifest: &[u8], sig_file: &[u8], key: &VerifyingKey) -> Result<()> {
    let raw = STANDARD
        .decode(strip_ws(sig_file))
        .map_err(|_| Error::signature("The update list's signature is not readable."))?;
    let bytes: [u8; 64] =
        raw.as_slice().try_into().map_err(|_| Error::signature("The update list's signature has the wrong length."))?;
    let sig = Signature::from_bytes(&bytes);
    key.verify_strict(manifest, &sig).map_err(|_| {
        Error::signature("The update list is not signed by the realm. Nothing was changed; try again later.")
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn placeholder_and_bad_keys() {
        assert!(decode_public_key(PLACEHOLDER_KEY).unwrap_err().contains("signing key"));
        assert!(decode_public_key("").is_err());
        assert!(decode_public_key("!!!").unwrap_err().contains("base64"));
        assert!(decode_public_key("AAAA").unwrap_err().contains("32 bytes"));
    }
}
