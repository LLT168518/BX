# -*- coding: utf-8 -*-
"""保信子站通用测试工具 — PyQt5 主界面"""
import sys
import os
from pathlib import Path

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QTextCursor, QColor
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QRadioButton, QButtonGroup,
    QTableWidget, QTableWidgetItem, QTextEdit, QSplitter, QGroupBox,
    QMessageBox, QFileDialog, QSpinBox, QAbstractItemView,
    QHeaderView, QStatusBar, QCheckBox
)

from master import SimulatedMaster
from protocol import GeneralItem


# ---------- 工作线程 ----------
class MasterWorker(QThread):
    log_sig  = pyqtSignal(str, str)     # level, message
    done_sig = pyqtSignal(bool, str)

    def __init__(self, master: SimulatedMaster, parent=None):
        super().__init__(parent)
        self.master = master
        self.master.set_log_callback(self._emit_log)

    def _emit_log(self, level, msg):
        self.log_sig.emit(level, msg)

    def run(self):
        ok, summary = self.master.run()
        self.done_sig.emit(ok, summary)

    def stop(self):
        self.master.stop()


# ---------- 主窗口 ----------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("保信子站通用测试工具 — 华北103 / 国网103")
        self.resize(1380, 880)

        self.worker = None
        self._build_ui()
        self._load_config()
        self._apply_qss()

    # ---------- UI ----------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # === 顶部控制条 ===
        top = QGroupBox("连接配置")
        tl = QHBoxLayout(top)

        tl.addWidget(QLabel("IP:"))
        self.ed_ip = QLineEdit("169.254.200.224")
        self.ed_ip.setFixedWidth(150)
        tl.addWidget(self.ed_ip)

        tl.addWidget(QLabel("端口:"))
        self.ed_port = QLineEdit("2406")
        self.ed_port.setFixedWidth(80)
        tl.addWidget(self.ed_port)

        tl.addWidget(QLabel("装置地址:"))
        self.ed_addr = QLineEdit("1")
        self.ed_addr.setFixedWidth(60)
        tl.addWidget(self.ed_addr)

        tl.addSpacing(10)
        tl.addWidget(QLabel("组号范围:"))
        self.sp_start = QSpinBox(); self.sp_start.setRange(0, 255)
        self.sp_start.setValue(10); self.sp_start.setFixedWidth(60)
        tl.addWidget(self.sp_start)
        tl.addWidget(QLabel("~"))
        self.sp_end = QSpinBox(); self.sp_end.setRange(0, 255)
        self.sp_end.setValue(30); self.sp_end.setFixedWidth(60)
        tl.addWidget(self.sp_end)

        tl.addSpacing(10)
        tl.addWidget(QLabel("模式:"))
        self.rb_check   = QRadioButton("判通讯正常")
        self.rb_nocheck = QRadioButton("不判通讯正常")
        self.rb_check.setChecked(True)
        self.bg = QButtonGroup(self)
        self.bg.addButton(self.rb_check)
        self.bg.addButton(self.rb_nocheck)
        tl.addWidget(self.rb_check)
        tl.addWidget(self.rb_nocheck)

        tl.addStretch()

        self.btn_run = QPushButton("开始测试")
        self.btn_run.clicked.connect(self.on_run)
        tl.addWidget(self.btn_run)

        self.btn_stop = QPushButton("停止")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.on_stop)
        tl.addWidget(self.btn_stop)

        self.btn_report = QPushButton("导出报告")
        self.btn_report.setEnabled(False)
        self.btn_report.clicked.connect(self.on_export)
        tl.addWidget(self.btn_report)

        root.addWidget(top)

        # === 中部：日志 + 表格 ===
        splitter = QSplitter(Qt.Horizontal)

        # 左：日志
        gb_log = QGroupBox("通讯日志")
        lv = QVBoxLayout(gb_log)
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setFont(QFont("Consolas", 9))
        lv.addWidget(self.txt_log)
        splitter.addWidget(gb_log)

        # 右：数据表
        gb_tab = QGroupBox("解析数据")
        tv = QVBoxLayout(gb_tab)
        self.tbl = QTableWidget(0, 5)
        self.tbl.setHorizontalHeaderLabels(
            ["组.条目", "类型", "值", "描述", "原始"])
        self.tbl.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.Stretch)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        tv.addWidget(self.tbl)
        splitter.addWidget(gb_tab)

        splitter.setSizes([620, 700])
        root.addWidget(splitter, 1)

        # === 状态栏 ===
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("就绪")

    def _apply_qss(self):
        qss = Path(__file__).parent / "config" / "css.qss"
        if qss.exists():
            try:
                self.setStyleSheet(qss.read_text(encoding="utf-8"))
            except Exception:
                pass

    def _load_config(self):
        ip_file = Path(__file__).parent / "config" / "ip.txt"
        if ip_file.exists():
            try:
                lines = [l.strip() for l in ip_file.read_text(
                    encoding="utf-8").splitlines() if l.strip()]
                if len(lines) >= 1: self.ed_ip.setText(lines[0])
                if len(lines) >= 2: self.ed_port.setText(lines[1])
                if len(lines) >= 3: self.ed_addr.setText(lines[2])
            except Exception:
                pass

    # ---------- 日志 ----------
    def _append_log(self, level: str, msg: str):
        colors = {
            "INFO": "#404040", "OK": "#008000", "WARN": "#b07000",
            "ERR":  "#c00000", "TX":  "#802880", "RX":  "#249B9B",
            "SIM-TX": "#802880", "SIM-RX": "#249B9B",
        }
        color = colors.get(level, "#333")
        ts = __import__("time").strftime("%H:%M:%S")
        self.txt_log.append(
            f'<span style="color:{color}">[{ts}][{level}] {msg}</span>')
        self.txt_log.moveCursor(QTextCursor.End)

    # ---------- 运行 ----------
    def on_run(self):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "提示", "测试正在进行中...")
            return
        try:
            port = int(self.ed_port.text().strip())
            addr = int(self.ed_addr.text().strip(), 0)
        except ValueError:
            QMessageBox.warning(self, "参数错误", "端口/地址必须为数字")
            return

        self.txt_log.clear()
        self.tbl.setRowCount(0)

        master = SimulatedMaster(
            host=self.ed_ip.text().strip(),
            port=port,
            device_addr=addr,
            check_comm=self.rb_check.isChecked(),
            group_start=self.sp_start.value(),
            group_end=self.sp_end.value(),
        )
        self._current_master = master

        self.worker = MasterWorker(master)
        self.worker.log_sig.connect(self._append_log)
        self.worker.done_sig.connect(self._on_done)
        self.worker.start()

        self.btn_run.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.btn_report.setEnabled(False)
        self.statusBar().showMessage("测试运行中...")

    def on_stop(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.statusBar().showMessage("正在停止...")

    def _on_done(self, ok: bool, summary: str):
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.btn_report.setEnabled(True)
        self.statusBar().showMessage(summary)
        self._populate_table()
        if ok:
            QMessageBox.information(self, "完成", summary)
        else:
            QMessageBox.warning(self, "失败", summary)

    def _populate_table(self):
        items = getattr(self._current_master, "items", [])
        self.tbl.setRowCount(0)
        for it in items:
            r = self.tbl.rowCount()
            self.tbl.insertRow(r)
            self.tbl.setItem(r, 0, QTableWidgetItem(it.key()))
            self.tbl.setItem(r, 1, QTableWidgetItem(f"0x{it.data_type:02X}"))
            self.tbl.setItem(r, 2, QTableWidgetItem(str(it.value)))
            self.tbl.setItem(r, 3, QTableWidgetItem(it.description))
            self.tbl.setItem(r, 4, QTableWidgetItem(""))

    def on_export(self):
        if not getattr(self, "_current_master", None):
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "保存报告", "test_report.txt", "Text (*.txt)")
        if not path:
            return
        self._current_master.save_report(path)
        QMessageBox.information(self, "完成", f"已保存: {path}")


# ---------- 入口 ----------
def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei", 9))
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()