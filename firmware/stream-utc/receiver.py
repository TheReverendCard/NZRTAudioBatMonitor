"""Acknowledged Stream field receiver, alongside the existing SD/RT service."""
import argparse
import hashlib
import hmac
import json
import os
import re
import struct
import threading
import zlib
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import NamedTemporaryFile

IDENTITY = re.compile(r"([0-9a-f]{12})-([0-9A-F]{8})-([1-9][0-9]{0,9})")
KINDS = {"event", "test", "pulse"}
RATE = 192000
MAX_WAV = 768044
MODEL = "f9f857b24d21666831e3d5eaa145904003fc2cb0a93a64e59d0f68f4eb69588e"


def publish(path, data):
    if path.exists():
        if path.read_bytes() != data:
            raise FileExistsError(path)
        return
    with NamedTemporaryFile(dir=path.parent, delete=False) as f:
        tmp = Path(f.name)
        try:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        except BaseException:
            f.close()
            tmp.unlink(missing_ok=True)
            raise
    try:
        if tmp.read_bytes() != data:
            raise OSError("readback mismatch")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def as_json(obj):
    return (json.dumps(obj, sort_keys=True, indent=2) + "\n").encode()


def parse_meta(headers):
    ident = headers["X-Event-ID"] or ""
    match = IDENTITY.fullmatch(ident)
    if not match or headers["X-Model"] != MODEL:
        raise ValueError("identity")
    up = int(headers["X-Uptime-Ms"])
    pre = int(headers["X-Pre-Samples"])
    score = int(headers["X-Score"])
    kind = headers["X-Kind"]
    source = headers["X-Clock"]
    utc = int(headers["X-Trigger-UTC-Ms"])
    if (not 0 <= up < 2**53 or kind not in KINDS or not 0 <= pre <= 48128
            or pre % 512 or not -2**31 <= score < 2**31):
        raise ValueError("trigger metadata")
    if (source == "UNSYNCED" and utc == 0):
        timing = None
    elif source in {"WIFI_NTP", "LORA_OTD"} and 1735689600000 <= utc < 4102444800000:
        timing = dict(trigger_utc_ms=utc, clock=source,
                      estimated_clip_start_utc_us=utc*1000-round(pre*1000000/RATE) if pre else None)
    else:
        raise ValueError("clock")
    firmware = headers.get("X-Firmware", "XIAO-STREAM-03")
    if firmware not in {"XIAO-STREAM-03", "XIAO-STREAM-04"}:
        raise ValueError("firmware")
    meta = dict(schema="xiao-stream-03", event_id=ident, device=match[1], boot=match[2],
                sequence=int(match[3]), kind=kind, trigger_uptime_ms=up, pre_samples=pre,
                score_acc=score, threshold=1404, model_sha256=MODEL, sample_rate=RATE, firmware=firmware,
                label="equipment_test" if kind == "test" else "unreviewed")
    if kind == "pulse":
        meta.update(threshold=702, trigger_rule="pulse_train_v1", required_onsets=3,
                    release_frames=8, window_frames=187)
    return ident, meta, timing


def validate_wav(data):
    n = len(data)-44
    header = struct.pack("<4sI4s4sIHHIIHH4sI", b"RIFF", n+36, b"WAVE", b"fmt ", 16, 1, 1,
                         RATE, RATE*2, 2, 16, b"data", n)
    if n != MAX_WAV-44 or data[:44] != header:
        raise ValueError("WAV format")


class Receiver(BaseHTTPRequestHandler):
    def reply(self, code, body):
        body = body.encode()
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path not in ("/stream-event", "/stream-clip"):
            return self.reply(404, "unknown route")
        if not any(hmac.compare_digest(self.headers.get("Authorization","").encode(), b"Bearer "+t)
                   for t in self.server.tokens):
            return self.reply(401, "unauthorized")
        try:
            self.connection.settimeout(12)
            ident, meta, timing = parse_meta(self.headers)
            n = int(self.headers["Content-Length"])
            is_clip = self.path == "/stream-clip"
            if n != (MAX_WAV if is_clip else 0):
                raise ValueError("length")
            data = self.rfile.read(n)
            crc = f"{zlib.crc32(data):08x}"
            if is_clip:
                if len(data) != n or crc != self.headers["X-WAV-CRC32"] or not meta["pre_samples"]:
                    raise ValueError("clip integrity")
                validate_wav(data)
                pulse_evidence = self.headers.get("X-Pulse-Evidence")
                if pulse_evidence not in (None, "train-v1"):
                    raise ValueError("pulse evidence")
            folder = self.server.root / meta["device"] / meta["boot"]
            with self.server.commit_lock:
                folder.mkdir(parents=True, exist_ok=True)
                base = folder / ident
                publish(base.with_suffix(".event.json"), as_json(meta))
                # Keep first valid clock mapping; later retries can supply a first fix.
                if timing and not base.with_suffix(".time.json").exists():
                    publish(base.with_suffix(".time.json"), as_json(timing))
                receipt = base.with_suffix(".received.json")
                if not receipt.exists():
                    publish(receipt, as_json(dict(first_received_utc=datetime.now(timezone.utc).isoformat())))
                    print(f"{meta['kind']} {ident} score={meta['score_acc']} trigger_utc_ms={timing and timing['trigger_utc_ms']}", flush=True)
                if is_clip:
                    publish(base.with_suffix(".wav"), data)
                    if pulse_evidence == "train-v1" or meta["kind"] == "pulse":
                        publish(base.with_suffix(".pulse.json"), as_json(dict(trigger_rule="pulse_train_v1",
                                supported=True, required_onsets=3, score_floor=702, release_frames=8, window_frames=187)))
                    publish(base.with_suffix(".wav.json"), as_json(dict(wav_crc32=crc, sha256=hashlib.sha256(data).hexdigest(), bytes=n)))
            return self.reply(200, "OK "+ident+(" "+crc if is_clip else ""))
        except (ValueError, TypeError, KeyError, OverflowError):
            return self.reply(422, "invalid metadata or payload")
        except FileExistsError:
            return self.reply(409, "conflicting event or audio")
        except OSError:
            return self.reply(503, "transfer or storage failure")


def server(address, root, tokens):
    if not tokens or any(not isinstance(t,str) or not t.strip() for t in tokens):
        raise ValueError("receiver tokens required")
    srv = ThreadingHTTPServer(address, Receiver)
    srv.tokens = [t.encode() for t in tokens]
    srv.root = Path(root) / "Stream"
    srv.commit_lock = threading.Lock()
    return srv


def settings(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bat-root", type=Path, default=Path.home()/"Documents"/"Bat")
    p.add_argument("--config", type=Path, help="existing receiver_config.json")
    p.add_argument("--root", type=Path, help="WiFi_Backup directory")
    p.add_argument("--port",type=int,default=8769)
    args = p.parse_args()
    cfg_file = args.bat_root/"bat_config.json"
    cfg = settings(cfg_file).get("receiver", {}) if cfg_file.is_file() else {}
    backup = args.root or Path(cfg.get("backup_root") or "WiFi_Backup")
    config = args.config or (args.bat_root / (cfg.get("script") or "receiver.py")).with_name("receiver_config.json")
    private = settings(config)
    with server(("",args.port), args.bat_root/backup, [private["token"], *private.get("additional_tokens",[])]) as srv:
        print(f"Stream receiver ready on TCP {args.port}. Archive: {srv.root}",flush=True)
        srv.serve_forever()


if __name__ == "__main__":
    main()
