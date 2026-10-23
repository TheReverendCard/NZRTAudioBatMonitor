#!/usr/bin/env python3
"""Overlay a pinned upstream MeshCore v1.18.0 repeater with NZRT microphone diagnostics.

Requires a separate clean checkout at the *exact* SHA. Never modifies the
working raw-LoRa firmware or the Open Transit Display project. --check only
validates source anchors and does not modify the MeshCore checkout.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import shutil
import subprocess

PINNED_SHA = "81dbae592ffad40b4212bc0b37e82b38da08f4bc"
ENV_NAME = "NZRT_Xiao_S3_WIO_wildlife_repeater"

def replace_one(source: str, before: str, after: str, label: str) -> str:
    count = source.count(before)
    if count != 1:
        raise RuntimeError(f"Upstream drift in {label}: expected one anchor, found {count}")
    return source.replace(before, after, 1)

def prepare(src: Path, check: bool = False) -> None:
    src = src.resolve()
    overlay = Path(__file__).resolve().parent
    if not (src / ".git").exists():
        raise RuntimeError("Use a full Git checkout of MeshCore, not an archive")
    head = subprocess.check_output(["git", "-C", str(src), "rev-parse", "HEAD"],
                                   text=True).strip()
    if head != PINNED_SHA:
        raise RuntimeError(f"Wrong MeshCore source revision {head}; expected {PINNED_SHA}")
    if (src / "platformio.local.ini").exists() or (src / "nzrt").exists():
        raise RuntimeError("Refusing to overwrite existing local.ini or nzrt overlay")

    main_path = src / "examples/simple_repeater/main.cpp"
    main = main_path.read_text()
    main = replace_one(main, '#include "MyMesh.h"',
                       '#include "MyMesh.h"\n#include "WildlifeMic.h"',
                       "repeater includes")
    main = replace_one(main, "  the_mesh.begin(fs);",
                       """  the_mesh.begin(fs);

  // Continuous audio sampling forbids sleep; MeshCore retains the radio.
  the_mesh.getNodePrefs()->powersaving_enabled = false;
  if (!WildlifeMic::begin())
    Serial.println("NZRT microphone start failed: MeshCore still running");""",
                       "repeater setup")
    main = replace_one(main, "  board.loop();   // let the board feed its watchdog, run periodic housekeeping",
                       "  WildlifeMic::printHealthIfDue();\n  board.loop();   // let the board feed its watchdog, run periodic housekeeping",
                       "repeater loop")

    ini_path = src / "platformio.ini"
    config = ini_path.read_text()
    config = replace_one(config, "  -D LORA_FREQ=869.618",
                         "  -D LORA_FREQ=917.375", "NZ band selection")
    config = replace_one(config, "  -D LORA_SF=8",
                         "  -D LORA_SF=7", "NZ narrow SF")
    config = replace_one(config, "  -D ENABLE_ADVERT_ON_BOOT=1",
                         "  -D ENABLE_ADVERT_ON_BOOT=0", "quiet bootstrap")

    # Board variant environments are in variants/xiao_s3_wio/platformio.ini,
    # not the root platformio.ini. Scope this to the exact repeater section.
    variant_path = src / "variants/xiao_s3_wio/platformio.ini"
    variant = variant_path.read_text()
    begin = variant.index("[env:Xiao_S3_WIO_repeater]")
    end = variant.index("; [env:Xiao_S3_WIO_repeater_bridge_rs232]", begin)
    section = variant[begin:end]
    section = replace_one(section, "  -D ADMIN_PASSWORD='\"password\"'",
                          "  -D ADMIN_PASSWORD='\"BENCH_ONLY_CHANGE_ME\"'",
                          "bench-only credential")
    variant = variant[:begin] + section + variant[end:]

    local = """; NZRT transient development target; NOT a public/production build.
[env:NZRT_Xiao_S3_WIO_wildlife_repeater]
extends = env:Xiao_S3_WIO_repeater
build_flags =
  ${env:Xiao_S3_WIO_repeater.build_flags}
  -I nzrt
  -D NZRT_WILDLIFE_MIC=1
  -D LORA_CR=5
  -D LORA_TX_POWER=10
build_unflags =
  -D LORA_TX_POWER=22
build_src_filter =
  ${env:Xiao_S3_WIO_repeater.build_src_filter}
  +<../nzrt/WildlifeMic.cpp>
"""
    if check:
        print(f"CHECK PASSED: pinned MeshCore SHA {head}; overlay anchors verified")
        return
    main_path.write_text(main)
    ini_path.write_text(config)
    variant_path.write_text(variant)
    (src / "platformio.local.ini").write_text(local)
    dest = src / "nzrt"
    dest.mkdir()
    shutil.copyfile(overlay / "WildlifeMic.cpp", dest / "WildlifeMic.cpp")
    shutil.copyfile(overlay / "WildlifeMic.h", dest / "WildlifeMic.h")
    print(f"PREPARED: MeshCore {head}, target {ENV_NAME}")
    print("Experimental capture + upstream repeater, NOT native wildlife telemetry yet")

if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--upstream", type=Path, required=True)
    cli.add_argument("--check", action="store_true")
    a = cli.parse_args()
    prepare(a.upstream, a.check)
