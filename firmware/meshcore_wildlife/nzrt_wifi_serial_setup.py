#!/usr/bin/env python3
"""One-shot NZRT Wi-Fi setup over XIAO ESP32-S3 USB CDC (Python + pyserial).

Usage: py nzrt_wifi_serial_setup.py [--port COM8] [--config private.ini]
Requires 'pyserial'. Prompts for SSID and hidden password BEFORE opening serial.
Credentials are never passed as command-line args or printed. Optionally read\nfrom a *user-created private INI* without adding them to PlatformIO build flags.\nPrompt mode doesn't save credentials on the PC.
The device stores them in its own NVS; the device's USB transport is not encrypted.
"""
import argparse
import configparser
import getpass
import sys
import time

try:
    import serial
except ImportError:
    sys.exit("pyserial not installed. Run: py -m pip install pyserial")


SUCCESS = b"NZRT TIME Wi-Fi credentials stored locally"
ERROR = b"NZRT TIME ERROR"
REBOOT_CMD = b"reboot\r"


def read_until(serial_port, success: bytes, error: bytes, seconds: float):
    end = time.monotonic() + seconds
    data = bytearray()
    while time.monotonic() < end:
        try:
            chunk = serial_port.read(serial_port.in_waiting or 1)
        except serial.SerialException as exc:
            return "disconnected", str(exc)
        if not chunk:
            continue
        data.extend(chunk)
        if success in data:
            return "ok", ""
        if error in data:
            return "error", ""
        # Keep memory bounded if the detector produces many candidates.
        if len(data) > 16000:
            del data[:-3000]
    return "timeout", ""


def main():
    parser = argparse.ArgumentParser(description="Privately provision NZRT XIAO Wi-Fi over USB serial")
    parser.add_argument("--port", default="COM8", help="USB serial port (default: COM8)")
    parser.add_argument("--config", help="Optional private INI containing [nzrt_wifi] ssid and password")
    args = parser.parse_args()

    print("Close Miniterm and other serial programs before proceeding.")
    if args.config:
        cfg = configparser.ConfigParser(interpolation=None)
        try:
            loaded = cfg.read(args.config, encoding="utf-8-sig")
            if not loaded or not cfg.has_section("nzrt_wifi"):
                sys.exit("Config missing or missing [nzrt_wifi] section. No credentials sent.")
            ssid = cfg.get("nzrt_wifi", "ssid", fallback="")
            password = cfg.get("nzrt_wifi", "password", fallback="")
        except (OSError, configparser.Error) as exc:
            sys.exit(f"Cannot read private INI: {exc}")
        print("Using private local INI. Password will not be printed.")
    else:
        ssid = input("Wi-Fi network name (SSID): ")
        password = getpass.getpass("Wi-Fi password (hidden): ")
    ssid_bytes = ssid.encode("utf-8")
    pass_bytes = password.encode("utf-8")
    if not (1 <= len(ssid_bytes) <= 32):
        sys.exit("SSID must contain 1 to 32 UTF-8 bytes.")
    if b"|" in ssid_bytes or b"\r" in ssid_bytes or b"\n" in ssid_bytes:
        sys.exit("SSID cannot contain a pipe, CR, or newline.")
    if len(pass_bytes) > 63 or any(c in pass_bytes for c in (b"\r", b"\n")):
        sys.exit("Password must be at most 63 UTF-8 bytes and cannot contain CR/newline.")
    if b"\x00" in ssid_bytes or b"\x00" in pass_bytes:
        sys.exit("NUL is not supported in credentials.")

    # Single bulk USB write with CR terminator. No command or password printing.
    payload = b"nzrt wifi set " + ssid_bytes + b"|" + pass_bytes + b"\r"
    print(f"Opening {args.port} at 115200 baud...")
    try:
        with serial.Serial(args.port, 115200, timeout=0.25, write_timeout=3,
                           rtscts=False, dsrdtr=False) as port:
            time.sleep(2.0)  # Give a re-enumerated CDC device time to settle.
            port.reset_input_buffer()
            port.write(payload)
            port.flush()
            print("Provisioning command sent; looking for confirmation...")
            result, err = read_until(port, SUCCESS, ERROR, 15.0)
            if result == "ok":
                print("Confirmed: Wi-Fi credentials saved in the XIAO.")
                # Reboot makes the next boot perform the bounded Wi-Fi + NTP attempt.
                # Native ESP32-S3 USB CDC disconnects after reboot, so do not keep
                # reading this port after issuing reset.
                try:
                    port.write(REBOOT_CMD)
                    port.flush()
                    print("Reboot command sent.")
                except (serial.SerialException, serial.SerialTimeoutException):
                    print("Device disconnected during reboot. This is expected.")
            elif result == "error":
                sys.exit("Device reported NZRT TIME ERROR. Credentials were not confirmed saved.")
            elif result == "disconnected":
                sys.exit("COM port disconnected before confirmation. Check the device/USB connection; do not assume credentials were saved.")
            else:
                sys.exit("No confirmation received within 15 seconds. Do not assume credentials were saved.")
    except (serial.SerialException, serial.SerialTimeoutException, OSError) as exc:
        sys.exit(f"Cannot complete COM-port transaction: {exc}")

    print("After reboot, connect using:")
    print(f"  py -m serial.tools.miniterm {args.port} 115200 --eol CR")
    print("Then type: nzrt time")
    print("Expected: status=SYNCED source=WIFI_NTP (if network/NTP reachable).")


if __name__ == "__main__":
    main()
