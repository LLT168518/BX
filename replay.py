# -*- coding: utf-8 -*-
import time
from PyQt5.QtCore import QThread, pyqtSignal
from comtrade import ComtradeRecord


class ReplayWorker(QThread):
    log_sig      = pyqtSignal(str)
    progress_sig = pyqtSignal(int, int, float)
    sample_sig   = pyqtSignal(int, list, list)
    finished_sig = pyqtSignal(bool)

    def __init__(self, record: ComtradeRecord, speed: float = 1.0,
                 loop: bool = False, parent=None):
        super().__init__(parent)
        self.record = record
        self.speed = max(speed, 0.01)
        self.loop = loop
        self._stop = False
        self._pause = False

    def stop(self):
        self._stop = True

    def pause(self):
        self._pause = True

    def resume(self):
        self._pause = False

    def run(self):
        if not self.record or not self.record.samples:
            self.log_sig.emit("无可回放数据")
            self.finished_sig.emit(False)
            return
        r = self.record
        total = len(r.samples)
        self.log_sig.emit(
            f"开始回放: {total} 个样本, 速度 {self.speed}x, 重复={self.loop}")
        try:
            while True:
                prev_ts = None
                for i, s in enumerate(r.samples):
                    if self._stop:
                        self.log_sig.emit("回放已停止")
                        self.finished_sig.emit(False)
                        return
                    while self._pause and not self._stop:
                        time.sleep(0.05)
                    if prev_ts is not None:
                        dt_us = (s.timestamp - prev_ts) / self.speed
                        time.sleep(max(0.0, min(dt_us / 1_000_000.0, 1.0)))
                    prev_ts = s.timestamp
                    self.sample_sig.emit(s.number, list(s.analog), list(s.digital))
                    self.progress_sig.emit(i + 1, total, s.timestamp)
                if not self.loop:
                    break
                self.log_sig.emit("一轮回放结束，重新开始...")
            self.log_sig.emit("回放完成")
            self.finished_sig.emit(True)
        except Exception as e:
            self.log_sig.emit(f"回放异常: {e}")
            self.finished_sig.emit(False)