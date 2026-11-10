import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from daily_state import State
from review_first_daily import group_signature


class Checkpoints(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.day="20261102"
        self.folder=self.root/self.day/("AR4"+self.day)
        self.folder.mkdir(parents=True)
        self.state=State(self.root)
        self.addCleanup(self.state.db.close)

    def test_unchanged_night_never_enumerates_members(self):
        (self.folder/"initial.bmp").write_bytes(b"a")
        self.state.discover_day(self.day)
        self.state.db.execute("DELETE FROM jobs")
        with patch("daily_state.os.scandir",side_effect=AssertionError("historical enumeration")):
            self.state.discover_day(self.day)
        self.assertEqual([],self.state.pending("prepare"))

    def test_late_file_and_restart(self):
        initial=self.folder/"first.bmp"
        initial.write_bytes(b"a")
        self.state.discover_day(self.day)
        self.state.done("prepare",initial.relative_to(self.root).as_posix())
        late=self.folder/"late.bmp"
        late.write_bytes(b"b")
        self.state.discover_day(self.day)
        after=State(self.root)
        self.addCleanup(after.db.close)
        self.assertEqual(after.pending("prepare"),[late.relative_to(self.root).as_posix()])

    def test_nested_external_arrival(self):
        folder=self.root/"External Data"/"Other"/self.day
        folder.mkdir(parents=True)
        self.state.watch(self.root/"External Data","external",True)
        (folder/"one.bmp").write_bytes(b"a")
        self.state.watch(self.root/"External Data","external",True)
        self.assertEqual(self.state.pending("external-file"),["External Data/Other/"+self.day+"/one.bmp"])

    def test_quarantine_tracks_changed_bytes(self):
        p=self.folder/"bad.bmp"
        p.write_bytes(b"")
        rel=p.relative_to(self.root).as_posix()
        self.state.reject(rel,group_signature(p),"empty")
        self.assertTrue(self.state.blocked(rel,group_signature(p)))
        p.write_bytes(b"replacement")
        self.assertFalse(self.state.blocked(rel,group_signature(p)))

    def test_repeated_current_day_coalesces_generated_sidecars(self):
        bmp=self.folder/"example.bmp"
        bmp.write_bytes(b"test")
        self.state.discover_day(self.day,True)
        self.state.done("prepare",bmp.relative_to(self.root).as_posix())
        Path(str(bmp)+".data").write_text("[]")
        self.state.remember_outputs(bmp)
        self.state.discover_day(self.day,True)
        self.assertEqual([],self.state.pending("prepare"))

    def test_scan_ignores_generated_trees(self):
        folder=self.folder/"Backup"
        folder.mkdir()
        (folder/"old.bmp").touch()
        self.state.discover_day(self.day)
        self.assertEqual([],self.state.pending("prepare"))

    def test_failed_step_has_timing_but_remains_pending(self):
        self.state.put("night",self.day)
        with self.assertRaises(ValueError):
            with self.state.timed("failure"):
                raise ValueError()
        self.assertEqual(self.state.pending("night"),[self.day])
        self.assertEqual(self.state.db.execute("SELECT result FROM timing").fetchone()[0],"failed")


if __name__=="__main__":
    unittest.main()
