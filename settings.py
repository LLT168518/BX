# -*- coding: utf-8 -*-
import json
from pathlib import Path
from dataclasses import dataclass, asdict


@dataclass
class ConnSettings:
    ip: str = "169.254.200.224"
    port: int = 2406
    device_addr: int = 1
    timeout: float = 1.0
    group_start: int = 10
    group_end: int = 30
    check_comm: bool = True
    comtrade_dir: str = "COMTRADE"


class SettingStore:
    def __init__(self, root: str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.ip_file      = self.root / "ip.txt"
        self.json_file    = self.root / "settings.json"
        self.qss_file     = self.root / "css.qss"
        self.devices_file = self.root / "devices.json"
        self.comtrade_dir = self.root / "COMTRADE"
        self.comtrade_dir.mkdir(parents=True, exist_ok=True)

    def load(self) -> ConnSettings:
        s = ConnSettings()
        if self.json_file.exists():
            try:
                data = json.loads(self.json_file.read_text(encoding="utf-8"))
                for k, v in data.items():
                    if hasattr(s, k):
                        setattr(s, k, v)
                return s
            except Exception:
                pass
        if self.ip_file.exists():
            try:
                lines = [l.strip() for l in self.ip_file.read_text(
                    encoding="utf-8").splitlines() if l.strip()]
                if len(lines) >= 1: s.ip = lines[0]
                if len(lines) >= 2: s.port = int(lines[1])
                if len(lines) >= 3: s.device_addr = int(lines[2], 0)
            except Exception:
                pass
        return s

    def save(self, s: ConnSettings) -> None:
        self.json_file.write_text(
            json.dumps(asdict(s), indent=2, ensure_ascii=False),
            encoding="utf-8")
        self.ip_file.write_text(
            f"{s.ip}\n{s.port}\n{s.device_addr}\n", encoding="utf-8")

    def qss(self) -> str:
        if self.qss_file.exists():
            try:
                return self.qss_file.read_text(encoding="utf-8")
            except Exception:
                pass
        return ""

    def list_comtrade(self):
        return sorted([p.name for p in self.comtrade_dir.glob("*.cfg")])

    def comtrade_path(self, name: str) -> Path:
        return self.comtrade_dir / name