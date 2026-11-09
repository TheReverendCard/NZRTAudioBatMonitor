# NZRT modular wildlife node: deployment profiles and stackable modules

**Status: design direction, not a claim of implemented hot-plug detection, bird classification, web UI, or battery optimisation.** Started from the Whangārei XIAO ESP32-S3 MeshCore + ultrasonic microphone field tests (October 2026). The user intends modules that physically stack, identify themselves, and can be configured from a local web interface or phone without firmware recompilation.

## Product separation: what hardware is present vs what the owner enables

Model these as independent data objects:

- **Detected hardware:** power board/controller (USB wall, solar + charger, battery), radio (Wio SX1262/MeshCore), sensors (ultrasonic PDM, audible mic, smart trap switch/current/vibration, SD/WAV storage, RTC/GNSS), hardware revision and calibration. Hardware IDs should derive from module-specific hardware descriptors, not assumed from what firmware was compiled for or what the user toggled in a menu.
- **Owner-selected capabilities:** trap detection, bird acoustic monitoring, bat acoustic monitoring, continuous/triggered WAV saving, private LoRa telemetry, USB/Wi-Fi bulk data, house gateway/repeater functions, local logs, and privacy/data retention.
- **Power policy:** wall/always-on, solar with capacity and SoC-aware budget, primary-battery long-life sensor, rechargeable field battery. Firmware should report measured supply and remaining energy only when hardware sensors exist; do not invent battery state from the configured policy.
- **Site config:** latitude/longitude, timezone for presentation, dusk/dawn offsets, user-defined schedules, whether a site provides dependable Wi-Fi, and whether MeshCore must remain available all day.
- **Capabilities and conflicts:** CPU/RAM/storage/energy/radio-duty estimates; combined loads need a scheduler and conflict table, not duplicated sensor tasks or an arbitrary single global night/day switch.

This should produce a unified effective schedule from **the union of selected capabilities**. Example: bat sampling dusk-to-dawn, bird sampling around dawn and daytime, trap switch monitoring around the clock; when sharing a microphone, coordinate sample rates and filters explicitly. If only a trap switch is installed, minimise awake duty cycle and send sparse compact LoRa change events.

## Deployment profiles (editable defaults; not hard-coded identities)

| Example profile | Sensors and duty | Compute / radio | Power expectation |
|---|---|---|---|
| Trap-only | event interrupt / periodic trap health all day | deep sleep between reports only when receiver availability is not required; intermittent LoRa TX | longest battery life |
| Bird | audible microphone on desired daylight/dawn windows | BirdNET-style inference only when compute budget allows; may offload WAV | solar or mains preferred |
| Bat | ultrasound on dusk-to-dawn (default sunset-30 min to sunrise+30 min) | lightweight trigger always on during window, confidence refinement, optional reference WAV | higher nightly duty |
| Bat + bird | joint schedule/split data path across night and day | shared microphone resources and CPU budget, explicit conflict policy | mains/solar more likely |
| Repeater/gateway | 24h LoRa RX/repeating, optional Wi-Fi bridge | **cannot deep sleep and reliably receive MeshCore packets** | mains / ample solar unless duty-limited |

Selections should be composable: a "bat + trap + repeater" deployment isn't another fixed firmware binary.

## Present field-pilot scope (NZRT-FIELD-PILOT-4)

- **Only the ultrasonic sensor is currently wired**. The active prototype is in the **bat-only profile** with daytime I2S/DSP standby (not ESP32 deep sleep).
- Sunrise/sunset calculated at an approximate **Whangārei/Maunu** coordinate, with wake 30 min before sunset and standby 30 min after sunrise; local NZ daylight saving rules are applied to presentation. These coordinates are **not suitable for arbitrary deployments** until configurable.
- If UTC is unknown or solar computation invalid, fail open: **keep the microphone running**, avoiding missed calls. Brief daily Wi-Fi NTP checks and authenticated incoming MeshCore clock corrections remain active independent of microphone standby.
- MeshCore repeater/serial keep running all day, so it is not yet a low-drain battery device. Standby turns off I2S bitclock and the DSP worker; it does not remove power from the microphone 3.3 V rail and should not be called full deep sleep.
- `nzrt day` reports current policy and solar times; `nzrt day enable` or `nzrt day disable` **persists locally** in NVS. This is the first configurable deployment preference: current bat-only builds default to enabled; disable for an always-on research test. Temporary `nzrt day test sleep` / `nzrt day test wake` overrides last 90s, and `nzrt day auto` returns to schedule.
- No general profile menu or plug-and-play detection exists yet; don't imply these commands configure bird/trap hardware.

## Proposed module identification and stacking (hardware revision)

1. Use keyed connectors with defined voltage/current limits, grounded shield, I2C/IRQ/UART interfaces, and documented pinout. Protect against incorrect plug orientation and power sequencing; avoid exposed high-frequency PDM traces on long unshielded stacking buses.
2. Give every board a **versioned, read-only descriptor**: vendor, module type, revision, capabilities, pin/I2C address allocation, power draw estimate, calibration pointer/CRC and protocol version. A small I2C EEPROM/ID resistor/1-Wire EEPROM is a possible mechanism; assess bus address collisions, hot-plugging and pull-up rail loading before choosing one. GPIO-only passive sensors may use an inexpensive ID circuit on a base board.
3. Device discovery creates a **capability inventory**; owner explicitly approves active functions. Refuse incompatible combinations with an explanation and preserve valid existing settings if a module is removed.
4. Store the configuration in NVS with a schema version and migration rules. Export/import a human-readable JSON backup (excluding secrets). Define safe defaults (no unrequested continuous high-power recording, no unspecified public RF transmission).
5. Later add an **on-device, local-first setup service**: temporary Wi-Fi AP/captive portal or BLE onboarding accessible by phone; show installed modules, selected functions, schedules, source of time, RF profile, energy/SD status, upload settings and estimated runtime. Disable provisioning radio after setup. Authenticate access and protect Wi-Fi passwords and private MeshCore keys; update over USB first, secured OTA only after validation.
6. Keep detection/report formats vendor-neutral, with session IDs, UTC and source/confidence, relative time, power-state, firmware/schema versions, and source sensor ID. LoRa only transmits compact, rate-limited event metadata; WAVs transfer over Wi-Fi/USB/SD with explicit retention/user permissions.

## Architecture suggestion

**Base firmware** provides a time service (NTP + authenticated MeshCore fallback), power scheduler, radio/serial services, secure local config and persistent journal. **Module drivers** expose `identify()`, `capabilities()`, `start()`, `stop()`, `health()`, and `measure()`/event stream. **Application profiles** declare required capabilities and schedules; the **resource planner** combines profiles and resolves CPU, mic, radio and battery constraints. Web UI talks to the same configuration service as CLI, avoiding different logic and accidental incompatibilities.

## Milestones

1. **Now:** verify v4 bat-only schedule, clock unknown fail-open, physically stopped I2S, successful sunset wake, retained event log and LoRa always-on; validate real power savings with an inline USB power meter.
2. **Next:** persist site location and a small capability/selected-functions schema. Improve bounded flash logging and evaluate the first SD+AR4 reference trials. Add configurable GPS/location/time zone to local setup or CLI.
3. **Then:** add a trap sensor daughterboard with interrupt wake and power budget; implement one unified scheduler; prove long-life trap-only operation, especially as a leaf node (not a permanent repeater).
4. **Then:** design a stackable connector/ID module prototype and trial module autodetection; add Wi-Fi/phone interface as a thin front end to the same tested configuration.
5. **Later:** audible birds, multiple mics, independent power boards, solar SoC strategy, OTA updates and connected MeshCore gateway integration.

The current field-pilot day/night code is a constrained test of one scheduler rule, not the final configurable multi-module system.
