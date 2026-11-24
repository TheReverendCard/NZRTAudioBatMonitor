import io
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from power_report import report


class PowerReportTest(unittest.TestCase):
    def test_mixed_archive_and_interrupted_append(self):
        with tempfile.TemporaryDirectory() as root:
            archive = Path(root)
            boot = archive / "4280DF29"
            boot.mkdir()
            (boot / "health.csv").write_text(
                "0,0,4,0,0,0,0,0,0,0,0,0,0,0,0,END\n"
                "1800000,0,675000,0,2,2,0,0,0,0,0,0,6500,110,0,3,2,0,240,3,900,1200,0,2000,END\n"
                "1800010,0,1", encoding="ascii")
            out = io.StringIO()
            report(archive, out)
            self.assertEqual(out.getvalue().splitlines()[1:],
                             ["4280DF29,30.0,packed,240,3,6.5,2.0,300.0,400.0,2,2,0,2,0,0,0"])
