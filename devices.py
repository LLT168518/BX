# -*- coding: utf-8 -*-
import json
from pathlib import Path
from typing import List, Dict, Any
from dataclasses import dataclass, field


@dataclass
class ExpectedEntry:
    number: int
    description: str = ""
    type: int = 0
    unit: str = ""


@dataclass
class ExpectedGroup:
    number: int
    name: str = ""
    entries: List[ExpectedEntry] = field(default_factory=list)


@dataclass
class ExpectedDevice:
    address: int
    name: str = ""
    model: str = ""
    groups: List[ExpectedGroup] = field(default_factory=list)


class DeviceMap:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.devices: Dict[int, ExpectedDevice] = {}
        self.load()

    def load(self):
        self.devices = {}
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return
        for d in data.get("devices", []):
            groups = []
            for g in d.get("groups", []):
                entries = [ExpectedEntry(
                    number=e.get("number", 0),
                    description=e.get("description", ""),
                    type=e.get("type", 0),
                    unit=e.get("unit", "")) for e in g.get("entries", [])]
                groups.append(ExpectedGroup(
                    number=g.get("number", 0),
                    name=g.get("name", ""),
                    entries=entries))
            self.devices[d.get("address", 0)] = ExpectedDevice(
                address=d.get("address", 0),
                name=d.get("name", ""),
                model=d.get("model", ""),
                groups=groups)

    def save(self):
        out = {"version": "1.0", "devices": []}
        for dev in self.devices.values():
            d = {"address": dev.address, "name": dev.name,
                 "model": dev.model, "groups": []}
            for g in dev.groups:
                gg = {"number": g.number, "name": g.name, "entries": []}
                for e in g.entries:
                    gg["entries"].append({
                        "number": e.number,
                        "description": e.description,
                        "type": e.type,
                        "unit": e.unit,
                    })
                d["groups"].append(gg)
            out["devices"].append(d)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    def build_from_items(self, ca: int, device_name: str, items) -> None:
        groups = {}
        for it in items:
            if it.entry <= 0:
                if it.group not in groups:
                    groups[it.group] = ExpectedGroup(
                        number=it.group, name=it.description)
                else:
                    groups[it.group].name = it.description
                continue
            g = groups.setdefault(it.group, ExpectedGroup(number=it.group))
            g.entries.append(ExpectedEntry(
                number=it.entry,
                description=it.description,
                type=it.data_type))
        self.devices[ca] = ExpectedDevice(
            address=ca,
            name=device_name or f"CA={ca}",
            groups=[groups[k] for k in sorted(groups.keys())])

    def compare(self, ca: int, actual_items) -> List[Dict[str, Any]]:
        dev = self.devices.get(ca)
        if not dev:
            return [{"status": "no_map", "key": "-",
                     "expected": "", "actual": f"装置 {ca} 未在点表中"}]
        expected = {}
        for g in dev.groups:
            for e in g.entries:
                expected[f"{g.number}.{e.number}"] = e
        actual = {}
        for it in actual_items:
            if it.entry > 0:
                actual[it.key()] = it

        results = []
        for key in sorted(expected.keys(),
                          key=lambda k: tuple(int(x) for x in k.split("."))):
            exp = expected[key]
            act = actual.get(key)
            if act is None:
                results.append({"status": "missing", "key": key,
                                "expected": exp.description, "actual": ""})
                continue
            if exp.description and act.description:
                if exp.description.strip() != act.description.strip():
                    results.append({"status": "mismatch", "key": key,
                                    "expected": exp.description,
                                    "actual": act.description})
                else:
                    results.append({"status": "ok", "key": key,
                                    "expected": exp.description,
                                    "actual": act.description})
            else:
                results.append({"status": "ok", "key": key,
                                "expected": exp.description,
                                "actual": act.description or str(act.value)})
        for key in sorted(actual.keys(),
                          key=lambda k: tuple(int(x) for x in k.split("."))):
            if key not in expected:
                results.append({"status": "extra", "key": key,
                                "expected": "",
                                "actual": actual[key].description
                                          or str(actual[key].value)})
        return results