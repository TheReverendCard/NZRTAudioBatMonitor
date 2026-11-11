@setlocal & py -3 -x "%~f0" %* & goto :finish
"""
:finish
@set "result=%errorlevel%"
@pause
@exit /b %result%
"""
import argparse
import http.client
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def settings(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def probe(port, token):
    for attempt in range(1, 4):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        stage = "connecting to TCP"
        try:
            conn.connect()
            stage = "sending the local WAV check"
            conn.request("GET", "/pass1-version", headers={"Authorization":"Bearer "+token})
            reply=conn.getresponse()
            if reply.status==200 and reply.read(6)==b"PASS-1":
                return True,"PASS-1 receiver verified"
            return False,"An older or different receiver is already running"
        except TimeoutError:
            print(f"Attempt {attempt}/3 timed out {stage} at 127.0.0.1:{port}.", flush=True)
            if attempt == 3:
                raise RuntimeError(f"Local check timed out {stage}. Check the listening process below.")
            time.sleep(1)
        finally:
            conn.close()


def show_listener(port):
    if os.name != "nt":
        return
    cmd = (
        f"$ls = @(Get-NetTCPConnection -State Listen -LocalPort {port} -ErrorAction SilentlyContinue);"
        "if (!$ls.Count) { Write-Output 'No listener found at diagnostic time.' };"
        "foreach ($l in $ls) { $p = Get-Process -Id $l.OwningProcess -ErrorAction SilentlyContinue;"
        "Write-Output ('LISTENER address={0} port={1} PID={2} process={3}' -f "
        "$l.LocalAddress,$l.LocalPort,$l.OwningProcess,$p.ProcessName) }"
    )
    try:
        subprocess.run(["powershell.exe", "-NoProfile", "-Command", cmd], timeout=12)
    except (OSError, subprocess.TimeoutExpired):
        print(f"To identify the listener, run: netstat -ano -p tcp | findstr :{port}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bat-root", type=Path, default=Path.home() / "Documents" / "Bat")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    root = args.bat_root.resolve()
    ext = Path(__file__).resolve().with_name("receiver_extension.py")
    os.environ["NZRT_BAT_ROOT"] = str(root)
    cfgfile = root / "bat_config.json"
    cfg = settings(cfgfile).get("receiver", {}) if cfgfile.is_file() else {}
    base = Path(cfg.get("script") or "receiver.py")
    if not base.is_absolute():
        base = root / base
    if not base.is_file():
        choices = sorted(p for p in root.glob("*/receiver.py") if p.with_name("receiver_config.json").is_file())
        if len(choices) == 1:
            base = choices[0]
        else:
            print("Choose the existing receiver.py. Available paths:", *choices, sep="\n")
            base = Path(input("Full path: ").strip().strip('"'))
    token = settings(base.with_name("receiver_config.json"))["token"]
    backup = Path(cfg.get("backup_root") or root / "WiFi_Backup")
    if not backup.is_absolute():
        backup = root / backup
    print(f"Checking extended receiver at 127.0.0.1:{args.port} ...", flush=True)
    global checked_port
    checked_port = args.port
    try:
        ok, detail = probe(args.port, token)
    except ConnectionRefusedError:
        pass
    else:
        if not ok:
            raise ValueError(f"Port {args.port} is occupied; WAV check returned {detail}. Check the existing receiver window and token. Close an old receiver before retrying.")
        print(f"ALREADY RUNNING: {detail} on port {args.port}.")
        return
    proc = subprocess.Popen([sys.executable, "-u", str(ext), "--receiver", str(base), "--root", str(backup), "--port", str(args.port)], cwd=root)
    try:
        for _ in range(60):
            if proc.poll() is not None:
                raise RuntimeError(f"Receiver exited during startup (code {proc.returncode}). See its output above.")
            try:
                ok, detail = probe(args.port, token)
            except ConnectionRefusedError:
                time.sleep(.25)
                continue
            if not ok:
                raise RuntimeError(f"Receiver check failed: {detail}")
            print(f"READY: {detail} on port {args.port}.", flush=True)
            print("Test WAV folder:", backup / "RT_Test_Clips", flush=True)
            print("Leave this window open for incoming RT requests.", flush=True)
            if proc.wait():
                raise RuntimeError("Receiver exited with an error.")
            return
        raise RuntimeError("Receiver did not begin listening within 15 seconds.")
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print("STOPPED:", exc, flush=True)
        if "checked_port" in globals():
            show_listener(checked_port)
        sys.exit(1)
