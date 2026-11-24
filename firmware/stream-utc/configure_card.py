"""Add the receiver to an existing Stream card without displaying its credentials."""
import argparse
from getpass import getpass
from ipaddress import IPv4Address
from pathlib import Path
from receiver import settings


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("card",type=Path,help="mounted card root, e.g. E:\\")
    p.add_argument("ip",type=IPv4Address,help="LAN IPv4 address of receiver PC")
    p.add_argument("--config",type=Path,help="existing receiver_config.json")
    args=p.parse_args()
    root=Path.home()/"Documents"/"Bat"
    if args.config:
        config=args.config
    else:
        cfg=settings(root/"bat_config.json")["receiver"]
        config=(root/cfg["script"]).with_name("receiver_config.json")
    token=settings(config)["token"]
    path=args.card/"stream-wifi.txt"
    old=path.read_text(encoding="utf-8-sig").splitlines() if path.exists() else []
    ssid=old[0] if old else input("2.4 GHz Wi-Fi name: ")
    password=old[1] if len(old)>1 else getpass("Wi-Fi password: ")
    if not ssid or not token or any(c in token for c in "\r\n"):
        p.error("missing network name or invalid receiver token")
    tmp=path.with_suffix(".new")
    with tmp.open("w",encoding="utf-8",newline="\n") as f:
        f.write("\n".join((ssid,password,str(args.ip),token))+"\n")
        f.flush()
        import os
        os.fsync(f.fileno())
    tmp.replace(path)
    print("Stream card configured. The private token and Wi-Fi password are on this card.")


if __name__=="__main__":
    main()
