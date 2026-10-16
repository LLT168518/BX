# -*- coding: utf-8 -*-
"""IEEE C37.111 COMTRADE 录波解析器"""
import os
import struct
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class AnalogChannel:
    index: int
    name: str = ""
    phase: str = ""
    ccbm: str = ""
    unit: str = ""
    a: float = 1.0
    b: float = 0.0
    skew: float = 0.0
    min_val: float = -32767.0
    max_val: float = 32767.0
    primary: float = 1.0
    secondary: float = 1.0
    ps: str = "S"

    def to_primary(self, raw: float) -> float:
        if self.secondary == 0:
            return 0.0
        return (self.a * raw + self.b) * (self.primary / self.secondary)


@dataclass
class DigitalChannel:
    index: int
    name: str = ""
    phase: str = ""
    ccbm: str = ""
    normal_state: int = 0


@dataclass
class SampleRate:
    rate: float
    end_sample: int


@dataclass
class ComtradeConfig:
    station_name: str = ""
    device_id: str = ""
    rev_year: str = "1999"
    total_channels: int = 0
    analog_count: int = 0
    digital_count: int = 0
    analog_channels: List[AnalogChannel] = field(default_factory=list)
    digital_channels: List[DigitalChannel] = field(default_factory=list)
    frequency: float = 50.0
    sample_rates: List[SampleRate] = field(default_factory=list)
    start_time: Optional[datetime] = None
    trigger_time: Optional[datetime] = None
    data_type: str = "ASCII"
    time_mult: float = 1.0
    raw_lines: List[str] = field(default_factory=list)


@dataclass
class ComtradeSample:
    number: int
    timestamp: float
    analog: List[float]
    digital: List[int]


@dataclass
class ComtradeRecord:
    config: ComtradeConfig
    samples: List[ComtradeSample] = field(default_factory=list)
    cfg_path: str = ""
    dat_path: str = ""

    def primary_value(self, sample: ComtradeSample, ch: int) -> float:
        return self.config.analog_channels[ch].to_primary(sample.analog[ch])

    def duration_us(self) -> float:
        if not self.samples:
            return 0.0
        return self.samples[-1].timestamp - self.samples[0].timestamp


def _parse_time(s: str):
    s = s.strip()
    if not s:
        return None
    for fmt in ("%d/%m/%Y,%H:%M:%S.%f", "%d/%m/%Y,%H:%M:%S",
                "%m/%d/%Y,%H:%M:%S.%f", "%m/%d/%Y,%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def parse_cfg(path: str) -> ComtradeConfig:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = [l.rstrip("\r\n") for l in f if l.strip()]
    if len(lines) < 4:
        raise ValueError("cfg 文件过短")

    cfg = ComtradeConfig()
    cfg.raw_lines = lines
    idx = 0

    parts = lines[idx].split(",")
    cfg.station_name = parts[0].strip() if len(parts) > 0 else ""
    cfg.device_id    = parts[1].strip() if len(parts) > 1 else ""
    cfg.rev_year     = parts[2].strip() if len(parts) > 2 else "1999"
    idx += 1

    parts = lines[idx].split(",")
    cfg.total_channels = int(parts[0])
    cfg.analog_count   = int(parts[1].rstrip("Aa"))
    cfg.digital_count  = int(parts[2].rstrip("Dd"))
    idx += 1

    for _ in range(cfg.analog_count):
        p = [x.strip() for x in lines[idx].split(",")]
        cfg.analog_channels.append(AnalogChannel(
            index     = int(p[0]),
            name      = p[1] if len(p) > 1 else "",
            phase     = p[2] if len(p) > 2 else "",
            ccbm      = p[3] if len(p) > 3 else "",
            unit      = p[4] if len(p) > 4 else "",
            a         = float(p[5])  if len(p) > 5  and p[5]  else 1.0,
            b         = float(p[6])  if len(p) > 6  and p[6]  else 0.0,
            skew      = float(p[7])  if len(p) > 7  and p[7]  else 0.0,
            min_val   = float(p[8])  if len(p) > 8  and p[8]  else -32767.0,
            max_val   = float(p[9])  if len(p) > 9  and p[9]  else 32767.0,
            primary   = float(p[10]) if len(p) > 10 and p[10] else 1.0,
            secondary = float(p[11]) if len(p) > 11 and p[11] else 1.0,
            ps        = p[12] if len(p) > 12 else "S",
        ))
        idx += 1

    for _ in range(cfg.digital_count):
        p = [x.strip() for x in lines[idx].split(",")]
        cfg.digital_channels.append(DigitalChannel(
            index        = int(p[0]),
            name         = p[1] if len(p) > 1 else "",
            phase        = p[2] if len(p) > 2 else "",
            ccbm         = p[3] if len(p) > 3 else "",
            normal_state = int(p[4]) if len(p) > 4 and p[4] else 0,
        ))
        idx += 1

    cfg.frequency = float(lines[idx]) if idx < len(lines) else 50.0
    idx += 1

    n_rates = int(lines[idx]); idx += 1
    for _ in range(n_rates):
        p = lines[idx].split(",")
        cfg.sample_rates.append(SampleRate(
            rate=float(p[0]),
            end_sample=int(p[1]) if len(p) > 1 else 0,
        ))
        idx += 1

    if idx < len(lines):
        cfg.start_time = _parse_time(lines[idx]); idx += 1
    if idx < len(lines):
        cfg.trigger_time = _parse_time(lines[idx]); idx += 1
    if idx < len(lines):
        cfg.data_type = lines[idx].strip().upper(); idx += 1
    if idx < len(lines):
        try:
            cfg.time_mult = float(lines[idx])
        except ValueError:
            cfg.time_mult = 1.0
    return cfg


def parse_dat(path: str, cfg: ComtradeConfig) -> List[ComtradeSample]:
    samples: List[ComtradeSample] = []
    na, nd = cfg.analog_count, cfg.digital_count

    if cfg.data_type == "ASCII":
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                p = line.split(",")
                if len(p) < 2 + na + nd:
                    continue
                try:
                    num = int(p[0]); ts = float(p[1])
                    analog  = [int(p[2 + i]) for i in range(na)]
                    digital = [int(p[2 + na + i]) for i in range(nd)]
                    samples.append(ComtradeSample(
                        num, ts * cfg.time_mult, analog, digital))
                except (ValueError, IndexError):
                    continue
    elif cfg.data_type in ("BINARY", "BINARY32"):
        analog_size = 2 if cfg.data_type == "BINARY" else 4
        n_dig_words = (nd + 15) // 16
        rec_size = 8 + na * analog_size + n_dig_words * 2
        with open(path, "rb") as f:
            data = f.read()
        pos = 0
        while pos + rec_size <= len(data):
            num = struct.unpack_from("<I", data, pos)[0]
            ts  = struct.unpack_from("<I", data, pos + 4)[0]
            pos += 8
            analog = []
            for _ in range(na):
                if analog_size == 2:
                    v = struct.unpack_from("<h", data, pos)[0]
                else:
                    v = struct.unpack_from("<i", data, pos)[0]
                analog.append(v); pos += analog_size
            digital = []
            for _ in range(n_dig_words):
                w = struct.unpack_from("<H", data, pos)[0]; pos += 2
                for b in range(16):
                    if len(digital) < nd:
                        digital.append((w >> b) & 1)
            samples.append(ComtradeSample(
                num, ts * cfg.time_mult, analog, digital))
    else:
        raise ValueError(f"不支持的 COMTRADE 数据格式: {cfg.data_type}")
    return samples


def load_comtrade(cfg_path: str) -> ComtradeRecord:
    base = os.path.splitext(cfg_path)[0]
    dat_path = ""
    for ext in (".dat", ".DAT", ".Dat"):
        if os.path.exists(base + ext):
            dat_path = base + ext
            break
    cfg = parse_cfg(cfg_path)
    samples = parse_dat(dat_path, cfg) if dat_path else []
    return ComtradeRecord(config=cfg, samples=samples,
                          cfg_path=cfg_path, dat_path=dat_path)


def save_comtrade(record: ComtradeRecord, cfg_path: str) -> None:
    base = os.path.splitext(cfg_path)[0]
    dat_path = base + ".dat"
    cfg = record.config

    with open(cfg_path, "w", encoding="utf-8") as f:
        f.write(f"{cfg.station_name},{cfg.device_id},{cfg.rev_year}\n")
        f.write(f"{cfg.total_channels},{cfg.analog_count}A,{cfg.digital_count}D\n")
        for ch in cfg.analog_channels:
            f.write(f"{ch.index},{ch.name},{ch.phase},{ch.ccbm},{ch.unit},"
                    f"{ch.a:.10f},{ch.b:.10f},{ch.skew:.6f},"
                    f"{ch.min_val:g},{ch.max_val:g},"
                    f"{ch.primary:.6f},{ch.secondary:.6f},{ch.ps}\n")
        for ch in cfg.digital_channels:
            f.write(f"{ch.index},{ch.name},{ch.phase},{ch.ccbm},{ch.normal_state}\n")
        f.write(f"{cfg.frequency:.6f}\n")
        f.write(f"{len(cfg.sample_rates)}\n")
        for sr in cfg.sample_rates:
            f.write(f"{sr.rate:.6f},{sr.end_sample}\n")
        f.write((cfg.start_time.strftime("%d/%m/%Y,%H:%M:%S.%f")
                 if cfg.start_time else "01/01/2000,00:00:00.000000") + "\n")
        f.write((cfg.trigger_time.strftime("%d/%m/%Y,%H:%M:%S.%f")
                 if cfg.trigger_time else "01/01/2000,00:00:00.000000") + "\n")
        f.write("ASCII\n")
        f.write(f"{cfg.time_mult:.6f}\n")

    with open(dat_path, "w", encoding="utf-8") as f:
        for s in record.samples:
            row = [str(s.number), f"{s.timestamp:.6f}"]
            row += [str(int(v)) for v in s.analog]
            row += [str(int(v)) for v in s.digital]
            f.write(",".join(row) + "\n")