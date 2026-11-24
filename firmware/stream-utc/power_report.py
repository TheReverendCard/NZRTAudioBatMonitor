"""Summarise the last complete Stream 04 power checkpoint for each boot."""
import argparse
import csv
import sys
from pathlib import Path


def checkpoints(path):
    with path.open(encoding="ascii", errors="replace", newline="") as f:
        for row in csv.reader(f):
            if len(row) != 25 or row[-1] != "END":
                continue
            try:
                yield [int(field) for field in row[:-1]]
            except ValueError:
                continue


def report(archive, output):
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(("boot", "elapsed_min", "fft", "cpu_MHz", "wifi_starts", "wifi_on_s", "lora_rx_s",
                     "decode_us_per_frame", "score_us_per_frame", "events", "SD_saves", "capture_gaps",
                     "UDP_sent", "event_ACKs", "WAV_ACKs", "WAV_enabled"))
    for path in sorted(archive.glob("*/health.csv")):
        last = None
        for row in checkpoints(path):
            last = row
        if last is None:
            continue
        samples = last[19]
        writer.writerow((path.parent.name, round(last[0]/60000, 2), "reference" if last[17] else "packed",
                         last[18], last[15], round(last[12]/1000, 2), round(last[23]/1000, 2),
                         round(last[20]/samples, 1) if samples else "",
                         round(last[21]/samples, 1) if samples else "", last[4], last[5], last[3],
                         last[16], last[8], last[9], last[22]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="STREAM03 directory on the card")
    args = parser.parse_args()
    if not args.archive.is_dir():
        parser.error("STREAM03 directory not found")
    report(args.archive, sys.stdout)
