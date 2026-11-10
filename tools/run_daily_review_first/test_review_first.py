import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from daily_state import State
from review_first_daily import group_signature, check_predictions


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

    def test_readonly_sealed_legacy_checkpoint(self):
        root=self.root/"Bat #1 % data"
        home=root/"Daily_Run_Reports"/"Daily_Integration"
        home.mkdir(parents=True)
        path=home/"Incremental_State_v3.sqlite3"
        conn=sqlite3.connect(path)
        conn.executescript("CREATE TABLE meta(key,value); CREATE TABLE folder(path); CREATE TABLE source(path,size,mtime_ns,folder)")
        conn.execute("INSERT INTO meta VALUES ('seal',?)",(json.dumps({"root":str(root),"created_utc":"2026-11-10T00:00:00+00:00"}),))
        conn.execute("INSERT INTO folder VALUES ('recorder')")
        conn.execute("INSERT INTO source VALUES ('recorder/example.bmp',42,10,'recorder')")
        conn.commit()
        conn.close()
        before=path.read_bytes()
        state=State(root)
        self.addCleanup(state.db.close)
        self.addCleanup(state.archive.close)
        with self.assertRaisesRegex(sqlite3.OperationalError,"readonly"):
            state.archive.execute("DELETE FROM meta")
        state.seed("recorder",None,"local",False)
        self.assertEqual(state.db.execute("SELECT sig FROM media").fetchone()[0],"42/10")
        self.assertEqual(before,path.read_bytes())

    def test_failed_legacy_open_preserves_pending_work(self):
        self.state.put("prepare","pending.bmp")
        self.state.db.commit()
        path=self.root/"Daily_Run_Reports"/"Daily_Integration"/"Incremental_State_v3.sqlite3"
        path.touch()
        connect=sqlite3.connect
        def simulate(path,*args,**kwargs):
            if str(path).startswith("file:"):
                raise sqlite3.OperationalError("unable to open database")
            return connect(path,*args,**kwargs)
        with patch("daily_state.sqlite3.connect",side_effect=simulate):
            state=State(self.root)
        self.addCleanup(state.db.close)
        self.assertEqual(state.pending("prepare"),["pending.bmp"])
        self.assertIsNone(state.archive)
        self.assertIsNone(state.seed("recorder",None,"local",False))

    def test_damaged_optional_checkpoint_does_not_block_startup(self):
        path=self.root/"Daily_Run_Reports"/"Daily_Integration"/"Incremental_State_v3.sqlite3"
        path.write_bytes(b"damaged database header")
        state=State(self.root)
        self.addCleanup(state.db.close)
        self.assertIsNone(state.archive)
        self.assertEqual(path.read_bytes(),b"damaged database header")

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

    def test_model_completion_requires_each_applicable_prediction(self):
        folder=self.root/"scoring"
        folder.mkdir()
        (folder/"trial_report.json").write_text(json.dumps({"night":self.day,"status":"COMPLETE"}))
        source=self.day+"/AR4"+self.day+"/one.bmp"
        csv=folder/"trial_predictions.csv"
        csv.write_text("night,source,model,probability\n"+"".join(
            f"{self.day},{source},{model},0.7\n" for model in ("bmp_lr","bmp_mlp")))
        with self.assertRaisesRegex(RuntimeError,"1 missing"):
            check_predictions(folder,self.day,[(source,"stamp")])
        with csv.open("a") as f:
            f.write(f"{self.day},{source},bmp_cnn,0.5\n")
        self.assertEqual(3,len(check_predictions(folder,self.day,[(source,"stamp")])))

    def test_failed_step_has_timing_but_remains_pending(self):
        self.state.put("night",self.day)
        with self.assertRaises(ValueError):
            with self.state.timed("failure"):
                raise ValueError()
        self.assertEqual(self.state.pending("night"),[self.day])
        self.assertEqual(self.state.db.execute("SELECT result FROM timing").fetchone()[0],"failed")


if __name__=="__main__":
    unittest.main()
