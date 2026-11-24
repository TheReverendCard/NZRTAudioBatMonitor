import hashlib
import http.client
import json
import struct
import sys
import tempfile
import threading
import unittest
import zlib
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import receiver


class FieldReceiverTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.srv=receiver.server(("127.0.0.1",0),self.tmp.name,["bench"])
        self.worker=threading.Thread(target=self.srv.serve_forever,daemon=True)
        self.worker.start()
        self.ident="010203040506-11223344-1"
        self.headers={"X-Event-ID":self.ident,"X-Uptime-Ms":"18000","X-Pre-Samples":"48128",
                      "X-Score":"1440","X-Kind":"event","X-Clock":"UNSYNCED","X-Trigger-UTC-Ms":"0",
                      "X-Model":receiver.MODEL,"Authorization":"Bearer bench"}
        self.folder=Path(self.tmp.name)/"Stream/010203040506/11223344"

    def tearDown(self):
        self.srv.shutdown(); self.worker.join(); self.srv.server_close(); self.tmp.cleanup()

    def post(self,path="/stream-event",data=b"",**headers):
        conn=http.client.HTTPConnection(*self.srv.server_address,timeout=4)
        try:
            conn.request("POST",path,data,self.headers|headers)
            response=conn.getresponse()
            return response.status,response.read().decode()
        finally:
            conn.close()

    @staticmethod
    def wav():
        pcm=b"\x32\x01"*384000
        return struct.pack("<4sI4s4sIHHIIHH4sI",b"RIFF",36+len(pcm),b"WAVE",b"fmt ",16,1,1,192000,384000,2,16,b"data",len(pcm))+pcm

    def test_outage_retry_late_anchor_and_deferred_wav(self):
        self.assertEqual(self.post(),(200,"OK "+self.ident))
        receipt=(self.folder/(self.ident+".received.json")).read_bytes()
        self.assertEqual(self.post()[0],200)
        self.assertFalse(list(self.folder.glob("*.time.json")))
        self.headers.update({"X-Clock":"LORA_OTD","X-Trigger-UTC-Ms":"1795481799931"})
        wav=self.wav()
        crc=f"{zlib.crc32(wav):08x}"
        for _ in range(2):
            self.assertEqual(self.post("/stream-clip",wav,**{"X-WAV-CRC32":crc}),(200,"OK "+self.ident+" "+crc))
        self.assertEqual(receipt,(self.folder/(self.ident+".received.json")).read_bytes())
        self.assertEqual((self.folder/(self.ident+".wav")).read_bytes(),wav)
        timing=json.loads((self.folder/(self.ident+".time.json")).read_text())
        self.assertEqual(timing["estimated_clip_start_utc_us"],1795481799931000-250667)
        self.assertEqual(json.loads((self.folder/(self.ident+".wav.json")).read_text())["sha256"],hashlib.sha256(wav).hexdigest())

    def test_reject_invalid_and_conflict(self):
        self.assertEqual(self.post(Authorization="wrong")[0],401)
        self.assertEqual(self.post(**{"X-Model":"unknown"})[0],422)
        self.assertEqual(self.post(**{"X-Event-ID":"../bad"})[0],422)
        self.assertEqual(self.post(**{"X-Clock":"WIFI_NTP"})[0],422)
        self.assertEqual(self.post()[0],200)
        self.assertEqual(self.post(**{"X-Score":"2000"})[0],409)
        self.assertEqual(self.post("/stream-clip",self.wav(),**{"X-WAV-CRC32":"00000000"})[0],422)
        wav=bytearray(self.wav());wav[24:28]=struct.pack("<I",96000)
        self.assertEqual(self.post("/stream-clip",wav,**{"X-WAV-CRC32":f"{zlib.crc32(wav):08x}"})[0],422)
        self.assertFalse(list(self.folder.glob("*.wav")))

    def test_separate_boot_and_test(self):
        for boot in ("11223344","55667788"):
            ident=f"010203040506-{boot}-1"
            self.assertEqual(self.post(**{"X-Event-ID":ident,"X-Kind":"test"})[0],200)
        metadata=list(Path(self.tmp.name).rglob("*.event.json"))
        self.assertEqual(len(metadata),2)
        self.assertTrue(all(json.loads(p.read_text())["label"]=="equipment_test" for p in metadata))
