# -*- coding: utf-8 -*-
import socket
import time
from typing import Optional, List, Tuple, Callable
from protocol import FrameCodec, parse_general_response, GeneralItem


class SimulatedMaster:
    def __init__(self, host: str, port: int, device_addr: int = 1,
                 check_comm: bool = True, timeout: float = 1.0,
                 group_start: int = 10, group_end: int = 30):
        self.host = host
        self.port = port
        self.addr = device_addr
        self.check_comm = check_comm
        self.timeout = timeout
        self.group_start = group_start
        self.group_end = group_end
        self.sock: Optional[socket.socket] = None
        self.logs: List[str] = []
        self.items: List[GeneralItem] = []
        self.raw_frames: List[dict] = []
        self._stop = False
        self._log_cb: Optional[Callable[[str, str], None]] = None

    def set_log_callback(self, cb):
        self._log_cb = cb

    def _log(self, level: str, msg: str):
        line = f"[{time.strftime('%H:%M:%S')}][{level}] {msg}"
        self.logs.append(line)
        if self._log_cb:
            try:
                self._log_cb(level, msg)
            except Exception:
                pass

    def _connect(self) -> bool:
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(3.0)
            self.sock.connect((self.host, self.port))
            self._log("OK", f"已连接 {self.host}:{self.port}")
            return True
        except Exception as e:
            self._log("ERR", f"连接失败: {e}")
            return False

    def _close(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def _send(self, data: bytes, desc: str) -> bool:
        if not self.check_comm:
            self._log("SIM-TX", f"{desc}: {data.hex(' ')}")
            return True
        if not self.sock:
            return False
        try:
            self.sock.sendall(data)
            self._log("TX", f"{desc}: {data.hex(' ')}")
            return True
        except Exception as e:
            self._log("ERR", f"发送失败: {e}")
            return False

    def _recv(self, timeout: Optional[float] = None) -> Optional[bytes]:
        if not self.check_comm:
            self._log("SIM-RX", "模拟应答 (视为成功)")
            return b""
        if not self.sock:
            return None
        t = timeout if timeout is not None else self.timeout
        self.sock.settimeout(t)
        try:
            data = self.sock.recv(4096)
            if data:
                self._log("RX", f"{len(data)} 字节: {data.hex(' ')}")
                parsed = FrameCodec.parse(data)
                if parsed:
                    self.raw_frames.append(parsed)
                return data
        except socket.timeout:
            self._log("WARN", f"接收超时 {t}s")
        except Exception as e:
            self._log("ERR", f"接收异常: {e}")
        return None

    def _reset_cu(self) -> bool:
        frame = FrameCodec.build_fixed(0x40, self.addr)
        if not self._send(frame, "复位通讯单元"):
            return False
        if not self.check_comm:
            return True
        resp = self._recv()
        if resp and len(resp) >= 5 and resp[0] == 0x10:
            ctrl = resp[1]
            if (ctrl & 0xE0) == 0x20 or ctrl == 0x00:
                self._log("OK", "复位确认")
                return True
        self._log("ERR", "复位无有效确认")
        return False

    def _reset_fcb(self):
        self._send(FrameCodec.build_fixed(0x47, self.addr), "复位FCB")
        if self.check_comm:
            self._recv(timeout=0.5)

    def _request_class1(self):
        self._send(FrameCodec.build_fixed(0x7A, self.addr), "召唤1级数据")
        if self.check_comm:
            self._recv()

    def _read_group_title(self) -> bool:
        asdu = bytes([0x15, 0x81, 0x2A, 0x00, 0xFE, 0xF0, 0x00, 0x02])
        frame = FrameCodec.build_variable(bytes([0x68, 0x53, 0x01]),
                                          self.addr, asdu)
        if not self._send(frame, "读全部组标题"):
            return False
        if not self.check_comm:
            return True
        resp = self._recv(timeout=2.0)
        if resp:
            self.items.extend(parse_general_response(resp))
            return True
        return False

    def _read_group(self, group: int) -> bool:
        asdu = bytes([0x15, 0x81, 0x2A, 0x00, 0xFE, 0xF1,
                      0x01, 0x01, 0x01, 0x00, group])
        frame = FrameCodec.build_variable(bytes([0x68, 0x73, 0x01]),
                                          self.addr, asdu)
        self._send(frame, f"读组{group}描述")
        if self.check_comm:
            resp = self._recv()
            if resp:
                self.items.extend(parse_general_response(resp))

        asdu = bytes([0x15, 0x81, 0x2A, 0x01, group, 0xFE, 0xF1,
                      0xE2, 0x01, 0xDC, 0x00, 0x01])
        frame = FrameCodec.build_variable(bytes([0xAA, 0x03, 0x86, 0x03]),
                                          self.addr, asdu)
        self._send(frame, f"读组{group}值")
        if self.check_comm:
            resp = self._recv()
            if resp:
                self.items.extend(parse_general_response(resp))
        return True

    def stop(self):
        self._stop = True

    def run(self) -> Tuple[bool, str]:
        mode = "判通讯正常" if self.check_comm else "不判通讯正常"
        self._log("INFO", f"===== 模拟主站启动 [{mode}] =====")
        try:
            if self.check_comm and not self._connect():
                return False, f"[{mode}] 连接失败"
            if not self._reset_cu():
                return False, f"[{mode}] 复位通讯单元失败"
            self._reset_fcb()
            self._request_class1()
            self._read_group_title()

            groups_ok = 0
            for g in range(self.group_start, self.group_end + 1):
                if self._stop:
                    break
                self._read_group(g)
                groups_ok += 1

            if self.check_comm and groups_ok == 0:
                return False, f"[{mode}] 未读取到任何组"
            return True, f"[{mode}] 完成，{groups_ok}组/{len(self.items)}项"
        except Exception as e:
            self._log("ERR", f"异常: {e}")
            return False, f"[{mode}] 异常: {e}"
        finally:
            self._close()

    def save_report(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            f.write("=" * 70 + "\n")
            f.write("保信子站测试报告\n")
            f.write(f"目标: {self.host}:{self.port}  装置地址: {self.addr}\n")
            f.write(f"模式: {'判通讯正常' if self.check_comm else '不判通讯正常'}\n")
            f.write(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 70 + "\n\n")
            f.write("--- 通讯日志 ---\n")
            for line in self.logs:
                f.write(line + "\n")
            f.write("\n--- 解析数据 ---\n")
            f.write(f"{'组.条目':<12}{'类型':<8}{'值':<22}{'描述'}\n")
            f.write("-" * 80 + "\n")
            for it in self.items:
                f.write(f"{it.key():<12}0x{it.data_type:02X}   "
                        f"{str(it.value):<22}{it.description}\n")
            f.write(f"\n--- 原始帧 ({len(self.raw_frames)}) ---\n")
            for fr in self.raw_frames:
                f.write(f"{fr['type']}  ctrl=0x{fr['ctrl']:02X}  "
                        f"raw={fr['raw'].hex(' ')}\n")
        self._log("OK", f"报告已保存: {path}")