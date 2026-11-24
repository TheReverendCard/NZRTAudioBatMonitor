import io
import csv
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from clip_times import export

class TestIndex(unittest.TestCase):
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
