//! Desktop and Start menu shortcuts (Windows): `Bleakhold.lnk` pointing to the install folder's copy of
//! the launcher, made by the system's own PowerShell through `WScript.Shell`. Paths reach the script
//! through environment variables, never through the script text.

use std::path::Path;

/// Name of the shortcut files.
pub const SHORTCUT_NAME: &str = "Bleakhold.lnk";

/// Creates the shortcuts asked for. Elsewhere than Windows it does nothing.
pub fn create(target: &Path, workdir: &Path, desktop: bool, start_menu: bool) -> Result<(), String> {
    if !desktop && !start_menu {
        return Ok(());
    }
    imp::create(target, workdir, desktop, start_menu)
}

/// The PowerShell script (kept separate so it can be read in tests).
pub fn script() -> &'static str {
    "$ErrorActionPreference = 'Stop'\n\
     $shell = New-Object -ComObject WScript.Shell\n\
     $dirs = @()\n\
     if ($env:BH_DESKTOP -eq '1') { $dirs += [Environment]::GetFolderPath('Desktop') }\n\
     if ($env:BH_STARTMENU -eq '1') { $dirs += [Environment]::GetFolderPath('Programs') }\n\
     foreach ($d in $dirs) {\n\
       if (-not $d) { continue }\n\
       New-Item -ItemType Directory -Force -Path $d | Out-Null\n\
       $s = $shell.CreateShortcut((Join-Path $d $env:BH_NAME))\n\
       $s.TargetPath = $env:BH_TARGET\n\
       $s.WorkingDirectory = $env:BH_WORKDIR\n\
       $s.IconLocation = $env:BH_TARGET + ',0'\n\
       $s.Description = 'Bleakhold Launcher'\n\
       $s.Save()\n\
     }\n"
}

#[cfg(windows)]
mod imp {
    use std::os::windows::process::CommandExt;
    use std::path::{Path, PathBuf};
    use std::process::{Command, Stdio};

    use base64::engine::general_purpose::STANDARD;
    use base64::Engine as _;

    const CREATE_NO_WINDOW: u32 = 0x0800_0000;

    pub fn create(target: &Path, workdir: &Path, desktop: bool, start_menu: bool) -> Result<(), String> {
        let root = std::env::var_os("SystemRoot").map(PathBuf::from).unwrap_or_else(|| PathBuf::from("C:\\Windows"));
        let ps = root.join("System32").join("WindowsPowerShell").join("v1.0").join("powershell.exe");
        let utf16: Vec<u8> = super::script().encode_utf16().flat_map(u16::to_le_bytes).collect();
        let out = Command::new(&ps)
            .args(["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand"])
            .arg(STANDARD.encode(utf16))
            .env("BH_TARGET", target)
            .env("BH_WORKDIR", workdir)
            .env("BH_NAME", super::SHORTCUT_NAME)
            .env("BH_DESKTOP", if desktop { "1" } else { "0" })
            .env("BH_STARTMENU", if start_menu { "1" } else { "0" })
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::piped())
            .creation_flags(CREATE_NO_WINDOW)
            .output()
            .map_err(|e| format!("could not run PowerShell: {e}"))?;
        if out.status.success() {
            Ok(())
        } else {
            Err(format!("PowerShell failed: {}", String::from_utf8_lossy(&out.stderr).trim()))
        }
    }
}

#[cfg(not(windows))]
mod imp {
    use std::path::Path;

    pub fn create(target: &Path, _workdir: &Path, _desktop: bool, _start_menu: bool) -> Result<(), String> {
        log::info!("shortcuts are only made on Windows (target {})", target.display());
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    #[test]
    fn script_takes_paths_from_the_environment() {
        let s = super::script();
        assert!(s.contains("$env:BH_TARGET") && s.contains("GetFolderPath('Programs')"));
        assert!(!s.contains("Bleakhold.lnk"), "names come from the environment");
        assert!(super::create(std::path::Path::new("x"), std::path::Path::new("y"), false, false).is_ok());
    }
}
