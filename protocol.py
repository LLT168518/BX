# -*- coding: utf-8 -*-
"""FT1.2 帧编解码 + IEC 103 通用分类服务 ASDU 解析"""
import struct
from typing import List, Optional, Any
from dataclasses import dataclass

TYP_GENERAL     = 0x15
COT_GENERAL     = 0x2A
FUN_SYSTEM      = 0xFE
INF_GROUP_TITLE = 0xF0
INF_ENTRY       = 0xF1


@dataclass
class GeneralItem:
    group: int = 0
    entry: int = 0
    data_type: int = 0
    value: Any = ""
    description: str = ""

    def key(self) -> str:
        return f"{self.group}.{self.entry}"


class FrameCodec:
    @staticmethod
    def checksum(data: bytes) -> int:
        return sum(data) & 0xFF

    @staticmethod
    def build_fixed(ctrl: int, addr: int) -> bytes:
        body = bytes([ctrl, addr])
        return bytes([0x10]) + body + bytes([FrameCodec.checksum(body), 0x16])

    @staticmethod
    def build_variable(ctrl: bytes, addr: int, asdu: bytes) -> bytes:
        body = ctrl + bytes([addr]) + asdu
        L = len(body)
        return bytes([0x68, L, L]) + body + bytes([FrameCodec.checksum(body), 0x16])

    @staticmethod
    def parse(data: bytes) -> Optional[dict]:
        if len(data) < 5:
            return None
        if data[0] == 0x10:
            if len(data) != 5 or data[4] != 0x16:
                return None
            ctrl, addr, cs = data[1], data[2], data[3]
            if FrameCodec.checksum(bytes([ctrl, addr])) != cs:
                return None
            return {"type": "FIXED", "ctrl": ctrl, "addr": addr, "raw": data}
        if data[0] == 0x68:
            if len(data) < 8:
                return None
            L = data[1]
            if data[2] != L or len(data) < 4 + L + 2:
                return None
            body = data[3:3 + L]
            cs   = data[3 + L]
            if FrameCodec.checksum(body) != cs or data[3 + L + 1] != 0x16:
                return None
            return {"type": "VARIABLE", "ctrl": body[0], "addr": body[1],
                    "asdu": body[2:], "raw": data}
        return None

    @staticmethod
    def find_asdu(data: bytes) -> Optional[bytes]:
        for i in range(len(data) - 3):
            if data[i] in (0x0A, 0x15) and data[i + 1] == 0x81:
                return data[i:]
        return None


def decode_value(dtype: int, data: bytes) -> Any:
    try:
        if dtype in (0x01, 0x09, 0x0B):
            return int.from_bytes(data, "little", signed=True)
        if dtype == 0x0D and len(data) >= 4:
            return round(struct.unpack("<f", data[:4])[0], 6)
        if dtype == 0x07 and data:
            return data[0]
        if dtype == 0x02:
            return data.decode("gbk", errors="replace")
    except Exception:
        pass
    return data.hex() if data else ""


def parse_general_response(frame: bytes) -> List[GeneralItem]:
    asdu = FrameCodec.find_asdu(frame)
    if asdu is None or len(asdu) < 8 or asdu[0] != TYP_GENERAL:
        return []

    items: List[GeneralItem] = []
    pos = 3 + 1
    cur_group = 0

    while pos < len(asdu) - 2:
        if asdu[pos] != FUN_SYSTEM:
            pos += 1
            continue
        pos += 1
        if pos >= len(asdu):
            break
        inf = asdu[pos]; pos += 1

        if inf == INF_GROUP_TITLE:
            if pos >= len(asdu):
                break
            count = asdu[pos]; pos += 1
            for _ in range(count):
                if pos + 4 > len(asdu):
                    break
                g = asdu[pos]; pos += 1
                pos += 1
                dt = asdu[pos]; pos += 1
                dl = asdu[pos]; pos += 1
                desc = asdu[pos:pos + dl]; pos += dl
                try:
                    txt = desc.decode("gbk", errors="replace")
                except Exception:
                    txt = desc.hex()
                items.append(GeneralItem(group=g, entry=0,
                                         data_type=dt, description=txt))
            continue

        if inf == INF_ENTRY:
            if len(asdu) > 5:
                cur_group = asdu[5]
            while pos < len(asdu):
                if asdu[pos] != 0x02:
                    pos += 1
                    continue
                if pos + 4 > len(asdu):
                    break
                pos += 1
                entry = asdu[pos]; pos += 1
                pos += 1
                dt = asdu[pos]; pos += 1
                dl = asdu[pos]; pos += 1
                if pos + dl > len(asdu):
                    dl = len(asdu) - pos
                data = asdu[pos:pos + dl]; pos += dl

                if dt == 0x02 or (dl and all(b >= 0x20 for b in data)):
                    try:
                        txt = data.decode("gbk", errors="replace")
                    except Exception:
                        txt = data.hex()
                    items.append(GeneralItem(group=cur_group, entry=entry,
                                             data_type=dt, description=txt))
                else:
                    items.append(GeneralItem(group=cur_group, entry=entry,
                                             data_type=dt,
                                             value=decode_value(dt, data)))
            break

    return items