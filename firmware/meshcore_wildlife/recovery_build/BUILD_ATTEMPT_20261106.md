# Build attempt, 6 November 2026

PlatformIO 6.1.18 installed in an isolated Python target.  Espressif32 6.11.0 platform download and installation succeeded.  Xtensa ESP32-S3 toolchain 8.4.0+2021r2-patch5 download failed its expected checksum on the first mirror.  The attempt was stopped during mirror fallback.  Compiler was not reached; no new firmware binary generated.  Checksum verification was not disabled.  This is a tool-download problem, not an observed source compilation error.

Use the Windows compile-only helper with the owner's existing installed toolchain to obtain a build receipt.  No device connection is needed.  Do not label recovery compiled until that receipt shows success.
