"""Export recording times from a Stream card or one boot folder."""
import argparse
import csv
import re
import struct
import sys
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path


def anchors(session):
    path = session / "clock.csv"
    result = []
    if path.is_file():
        for row in path.read_bytes().splitlines():
            fields = row.split(b",")
            if len(fields) != 5:
                continue
            boot, up, utc, source, end = fields
            if (boot != session.name.upper().encode() or end != b"END" or
                    source not in (b"WIFI_NTP", b"LORA_OTD") or
                    not up.isdigit() or not utc.isdigit()):
                continue
            if 1735689600000 <= int(utc) < 4102444800000:
                result.append((int(up), int(utc), source.decode()))
    return result


def export(root, output):
    cached = {}
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(("boot", "file", "kind", "trigger_uptime_ms", "trigger_utc", "source", "anchor_distance_s",
                     "pre_samples", "estimated_clip_start_utc", "score_acc", "receiver_wav_ack"))
    for path in sorted(root.rglob("*.wav")):
        boot = path.parent
        match = re.fullmatch(r"(\d+)_(\d+)_(event|test)\.wav", path.name)
        if not match or not re.fullmatch("[0-9A-Fa-f]{8}", boot.name):
            continue
        up = int(match[2])
        if boot not in cached:
            cached[boot] = anchors(boot)
        stamp, source, distance = "", "UNSYNCED", ""
        if cached[boot]:
            at, utc, source = min(cached[boot], key=lambda a: (abs(a[0]-up), a[2] != "WIFI_NTP"))
            dt = datetime.fromtimestamp((utc+up-at)/1000, tz=timezone.utc)
            stamp = dt.isoformat(timespec="milliseconds").replace("+00:00","Z")
            distance = f"{abs(at-up)/1000:.3f}"
        pre, start, score, ack = "", "", "", ""
        record = path.with_suffix(".evt")
        if record.is_file():
            raw = record.read_bytes()
            if len(raw) == 28:
                event_up, seq, value, samples, manual, crc = struct.unpack("<qIiIII", raw)
                if (crc == zlib.crc32(raw[:24]) and seq == int(match[1]) and up == event_up
                        and manual == int(match[3] == "test") and 0 < samples <= 48128 and samples % 512 == 0):
                    pre, score = samples, value
                    if stamp:
                        start = (dt - timedelta(microseconds=round(samples*1000000/192000))).isoformat(
                            timespec="microseconds").replace("+00:00", "Z")
                    marker = path.with_suffix(".done")
                    ack = int(marker.is_file() and marker.read_bytes() == bytes([0xa5]))
        writer.writerow((boot.name, path.name, match[3], up, stamp, source, distance, pre, start, score, ack))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.folder.is_dir():
        parser.error("The card or session folder does not exist.")
    if args.output:
        with args.output.open("w", newline="", encoding="utf-8") as out:
            export(args.folder, out)
    else:
        export(args.folder, sys.stdout)
