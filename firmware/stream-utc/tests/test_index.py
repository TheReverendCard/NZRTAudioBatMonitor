import io
import struct
import zlib
import csv
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from clip_times import export

class TestIndex(unittest.TestCase):
    def test_field_clip_start_and_integrity(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "0123ABCD"
            root.mkdir()
            (root / "clock.csv").write_text("0123ABCD,1000,1795492800000,WIFI_NTP,END\n")
            clip = root / "00000001_0000001000_event.wav"
            clip.touch()
            event = struct.pack("<qIiII", 1000, 1, 1550, 48128, 0)
            clip.with_suffix(".evt").write_bytes(event + struct.pack("<I", zlib.crc32(event)))
            clip.with_suffix(".done").write_bytes(bytes([0xa5]))
            out = io.StringIO()
            export(root, out)
            row = next(csv.DictReader(io.StringIO(out.getvalue())))
            self.assertEqual((row["pre_samples"],row["score_acc"],row["receiver_wav_ack"]),("48128","1550","1"))
            self.assertTrue(row["estimated_clip_start_utc"].endswith("59.749333Z"))
            pulse = root / "00000002_0000001000_pulse.wav"
            pulse.touch()
            pulse_event = struct.pack("<qIiII", 1000, 2, 720, 48128, 2)
            pulse.with_suffix(".evt").write_bytes(pulse_event + struct.pack("<I", zlib.crc32(pulse_event)))
            out = io.StringIO()
            export(root, out)
            pulse_row = list(csv.DictReader(io.StringIO(out.getvalue())))[1]
            self.assertEqual((pulse_row["kind"], pulse_row["score_acc"], pulse_row["trigger_utc"]),
                             ("pulse", "720", row["trigger_utc"]))
            clip.with_suffix(".evt").write_bytes(event + bytes(4))
            out = io.StringIO()
            export(root, out)
            self.assertEqual(next(csv.DictReader(io.StringIO(out.getvalue())))["estimated_clip_start_utc"], "")

    def test_recovery_across_clock_lock_without_crossing_boots(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            one, two = root / "BBB2E908", root / "00000002"
            one.mkdir()
            two.mkdir()
            for session in (one, two):
                (session / "00000001_0000001000_test.wav").touch()
            (one / "00000002_0000009000_event.wav").touch()
            (one / "00000003.part").touch()
            (one / "clock.csv").write_bytes(
                b"BBB2E908,12,broken\n00000002,1000,1795492888888,WIFI_NTP,END\n"
                b"BBB2E908,2000,1795492800000,LORA_OTD,END\n"
                b"BBB2E908,8000,1795492806123,WIFI_NTP,END\nBBB2E908,9000,")
            out = io.StringIO()
            export(root, out)
            result = list(csv.DictReader(io.StringIO(out.getvalue())))
            self.assertEqual([r["source"] for r in result], ["UNSYNCED", "LORA_OTD", "WIFI_NTP"])
            self.assertEqual(result[0]["trigger_utc"], "")
            self.assertTrue(result[1]["trigger_utc"].endswith("59.000Z"))
            self.assertTrue(result[2]["trigger_utc"].endswith("07.123Z"))
