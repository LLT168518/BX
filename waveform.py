# -*- coding: utf-8 -*-
import pyqtgraph as pg
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget,
    QListWidgetItem, QLabel, QComboBox, QDoubleSpinBox, QCheckBox
)
from comtrade import ComtradeRecord


class WaveformWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.record = None
        self._vline = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("通道类型:"))
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItems(["模拟量", "数字量"])
        self.cmb_mode.currentIndexChanged.connect(self._refresh_channels)
        top.addWidget(self.cmb_mode)

        top.addWidget(QLabel("时间缩放:"))
        self.spin_zoom = QDoubleSpinBox()
        self.spin_zoom.setRange(0.01, 1000.0)
        self.spin_zoom.setValue(1.0)
        self.spin_zoom.valueChanged.connect(self.redraw)
        top.addWidget(self.spin_zoom)

        self.chk_norm = QCheckBox("归一化堆叠")
        self.chk_norm.setChecked(True)
        self.chk_norm.stateChanged.connect(self.redraw)
        top.addWidget(self.chk_norm)

        self.btn_clear = QPushButton("清空选择")
        self.btn_clear.clicked.connect(self._clear_selection)
        top.addWidget(self.btn_clear)
        top.addStretch()
        root.addLayout(top)

        chbox = QHBoxLayout()
        chbox.addWidget(QLabel("已加载通道:"))
        self.list_ch = QListWidget()
        self.list_ch.setMaximumHeight(110)
        self.list_ch.setSelectionMode(QListWidget.MultiSelection)
        self.list_ch.itemSelectionChanged.connect(self.redraw)
        chbox.addWidget(self.list_ch, 1)
        root.addLayout(chbox)

        self.plot = pg.PlotWidget()
        self.plot.setBackground("w")
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        self.plot.setLabel("bottom", "时间 (ms)")
        self.plot.setLabel("left", "幅值")
        self.plot.addLegend(offset=(-10, 10))
        root.addWidget(self.plot, 1)

    def set_record(self, record: ComtradeRecord):
        self.record = record
        self._refresh_channels()

    def _refresh_channels(self):
        self.list_ch.clear()
        if not self.record:
            return
        if self.cmb_mode.currentText() == "模拟量":
            for i, ch in enumerate(self.record.config.analog_channels):
                item = QListWidgetItem(f"{ch.index} - {ch.name} [{ch.unit}]")
                item.setData(Qt.UserRole, ("analog", i))
                self.list_ch.addItem(item)
        else:
            for i, ch in enumerate(self.record.config.digital_channels):
                item = QListWidgetItem(f"{ch.index} - {ch.name}")
                item.setData(Qt.UserRole, ("digital", i))
                self.list_ch.addItem(item)
        if self.list_ch.count() > 0:
            self.list_ch.item(0).setSelected(True)
        self.redraw()

    def _clear_selection(self):
        self.list_ch.clearSelection()
        self.redraw()

    def redraw(self):
        self.plot.clear()
        self._vline = None
        if not self.record or not self.record.samples:
            return
        r = self.record
        zoom = max(self.spin_zoom.value(), 0.01)
        x = [s.timestamp / 1000.0 / zoom for s in r.samples]

        selected = self.list_ch.selectedItems()
        if not selected:
            return

        normalize = self.chk_norm.isChecked()
        stack = 0.0
        palette = pg.intColor

        for k, it in enumerate(selected):
            kind, idx = it.data(Qt.UserRole)
            color = palette(k, hues=12)
            if kind == "analog":
                ch = r.config.analog_channels[idx]
                y = [ch.to_primary(s.analog[idx]) for s in r.samples]
                if normalize:
                    ymin, ymax = min(y), max(y)
                    if ymax - ymin > 1e-12:
                        y = [(v - ymin) / (ymax - ymin) for v in y]
                    else:
                        y = [0.5] * len(y)
                    y = [v + stack for v in y]
                    stack += 1.2
                self.plot.plot(x, y, pen=pg.mkPen(color, width=1.4), name=ch.name)
            else:
                ch = r.config.digital_channels[idx]
                y = [s.digital[idx] for s in r.samples]
                if normalize:
                    y = [v * 0.8 + stack for v in y]
                    stack += 1.2
                self.plot.plot(x, y, pen=pg.mkPen(color, width=1.4),
                               name=ch.name, stepMode=True)

    def highlight_sample(self, sample_number: int):
        if not self.record or not self.record.samples:
            return
        idx = sample_number - 1
        if idx < 0 or idx >= len(self.record.samples):
            return
        s = self.record.samples[idx]
        zoom = max(self.spin_zoom.value(), 0.01)
        x_ms = s.timestamp / 1000.0 / zoom
        if self._vline is None:
            self._vline = self.plot.addLine(
                x=x_ms, pen=pg.mkPen("r", width=1, style=Qt.DashLine))
        else:
            self._vline.setValue(x_ms)