# packaging/

Windows Setup (Inno Setup) for SAA Alpha v3.

1. `powershell -ExecutionPolicy Bypass -File ..\scripts\bundle_runtime.ps1`
2. Open `saa_alpha.iss` in Inno Setup → Compile
3. Installer → `Output\SAAAlphaSetup-*.exe`

See `docs\V3_WINDOWS_PACKAGING.md`.
