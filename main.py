# -*- coding: utf-8 -*-
import sys
import os
import time
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QToolButton, QLabel, QLineEdit, QPushButton, QTableWidget, 
    QTableWidgetItem, QHeaderView, QSplitter, QTreeWidget, 
    QTreeWidgetItem, QStatusBar, QFrame, QMessageBox, QAbstractItemView,
    QDialog, QFormLayout, QSpinBox, QDoubleSpinBox, QCheckBox, 
    QDialogButtonBox, QStyle, QTabWidget, QTableWidgetItem
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QIcon, QFont, QColor, QPainter, QPen

# ================= 导入项目原有模块 =================
try:
    from settings import SettingStore, ConnSettings
    from master import SimulatedMaster
    from protocol import FrameCodec, parse_general_response, GeneralItem
except ImportError as e:
    print(f"警告: 部分核心模块未找到，请检查目录结构。错误: {e}")
    class ConnSettings: pass
    class SettingStore: 
        def load(self): return ConnSettings()
        def save(self, s): pass
    class SimulatedMaster: 
        def __init__(self, *args, **kwargs): self.items = []
        def set_log_callback(self, cb): pass
        def run(self): return True, "模拟成功"
        def save_report(self, path): pass
    class FrameCodec:
        @staticmethod
        def parse(data): return {"type": "UNKNOWN", "raw": data}
    def parse_general_response(data): return []
    class GeneralItem:
        def __init__(self): self.group=0; self.entry=0; self.data_type=0; self.value=""; self.description=""


# ================= 1. 通讯参数配置弹窗 =================
class CommSettingsDialog(QDialog):
    def __init__(self, current_settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("通讯参数配置")
        self.setFixedSize(380, 420)
        self.settings = current_settings
        self.setFont(QFont("Microsoft YaHei", 10))

        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        form_layout = QFormLayout()
        form_layout.setSpacing(12)
        form_layout.setLabelAlignment(Qt.AlignRight)

        self.input_ip = QLineEdit(getattr(self.settings, 'ip', "169.254.200.224"))
        self.input_port = QSpinBox()
        self.input_port.setRange(1, 65535)
        self.input_port.setValue(getattr(self.settings, 'port', 2406))
        
        self.input_addr = QSpinBox()
        self.input_addr.setRange(0, 255)
        self.input_addr.setValue(getattr(self.settings, 'device_addr', 1))

        self.input_timeout = QDoubleSpinBox()
        self.input_timeout.setRange(0.1, 60.0)
        self.input_timeout.setValue(getattr(self.settings, 'timeout', 1.0))

        self.input_group_start = QSpinBox()
        self.input_group_start.setRange(1, 100)
        self.input_group_start.setValue(getattr(self.settings, 'group_start', 10))

        self.input_group_end = QSpinBox()
        self.input_group_end.setRange(1, 100)
        self.input_group_end.setValue(getattr(self.settings, 'group_end', 30))

        self.chk_check_comm = QCheckBox("判通讯正常（先复位并等待确认）")
        self.chk_check_comm.setChecked(getattr(self.settings, 'check_comm', True))

        form_layout.addRow("目标 IP 地址：", self.input_ip)
        form_layout.addRow("目标端口：", self.input_port)
        form_layout.addRow("装置地址 (CA)：", self.input_addr)
        form_layout.addRow("接收超时 (秒)：", self.input_timeout)
        form_layout.addRow("总召起始组：", self.input_group_start)
        form_layout.addRow("总召结束组：", self.input_group_end)
        form_layout.addRow("", self.chk_check_comm)

        layout.addLayout(form_layout)
        layout.addStretch()

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.button(QDialogButtonBox.Ok).setText("保存")
        btn_box.button(QDialogButtonBox.Cancel).setText("取消")
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def get_settings(self):
        self.settings.ip = self.input_ip.text().strip()
        self.settings.port = self.input_port.value()
        self.settings.device_addr = self.input_addr.value()
        self.settings.timeout = self.input_timeout.value()
        self.settings.group_start = self.input_group_start.value()
        self.settings.group_end = self.input_group_end.value()
        self.settings.check_comm = self.chk_check_comm.isChecked()
        return self.settings


# ================= 2. 报文详情解析弹窗 =================
class MessageDetailDialog(QDialog):
    def __init__(self, raw_hex_str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("报文详细解析")
        self.resize(650, 550)
        self.raw_hex_str = raw_hex_str.strip()
        self.setFont(QFont("Microsoft YaHei", 10))

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        raw_layout = QHBoxLayout()
        raw_layout.addWidget(QLabel("原始报文(Hex):"))
        self.txt_raw = QLineEdit(self.raw_hex_str)
        self.txt_raw.setReadOnly(True)
        self.txt_raw.setStyleSheet("font-family: Consolas; font-size: 13px; color: #d32f2f; font-weight: bold; padding: 4px;")
        raw_layout.addWidget(self.txt_raw, 1)
        layout.addLayout(raw_layout)

        layout.addWidget(QLabel("解析结果:"))
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["字段", "值", "说明"])
        self.tree.setColumnWidth(0, 180)
        self.tree.setColumnWidth(1, 150)
        self.tree.setStyleSheet("QTreeWidget { font-family: Consolas, 'Microsoft YaHei'; font-size: 13px; }")
        self.tree.setAlternatingRowColors(True)
        layout.addWidget(self.tree, 1)

        btn_close = QPushButton("关闭")
        btn_close.setFixedWidth(100)
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, 0, Qt.AlignRight)

        self._parse_and_show()

    def _parse_and_show(self):
        try:
            hex_clean = self.raw_hex_str.replace(" ", "").replace("\n", "")
            data = bytes.fromhex(hex_clean)
        except ValueError:
            self.tree.addTopLevelItem(QTreeWidgetItem(["错误", "非法的 Hex 格式", ""]))
            return

        try:
            parsed = FrameCodec.parse(data)
        except Exception as e:
            parsed = None
            self.tree.addTopLevelItem(QTreeWidgetItem(["解析异常", str(e), ""]))

        if not parsed:
            self.tree.addTopLevelItem(QTreeWidgetItem(["提示", "无法识别的报文帧格式", "请检查报文是否完整"]))
            return

        frame_type = parsed.get("type", "UNKNOWN")
        root_item = QTreeWidgetItem([f"帧类型", frame_type, "固定帧 (0x10)" if frame_type == "FIXED" else "可变帧 (0x68)"])
        self.tree.addTopLevelItem(root_item)

        ctrl = parsed.get("ctrl", 0)
        addr = parsed.get("addr", 0)
        
        if frame_type == "FIXED":
            dir_bit = (ctrl >> 7) & 1
            prm_bit = (ctrl >> 6) & 1
            fcb_bit = (ctrl >> 5) & 1
            fcv_bit = (ctrl >> 4) & 1
            func_code = ctrl & 0x0F
            ctrl_detail = f"方向:{'主站->子站' if dir_bit else '子站->主站'} 启动位:{prm_bit} FCB:{fcb_bit} FCV:{fcv_bit} 功能码:{func_code:02X}"
            QTreeWidgetItem(root_item, ["控制域", f"0x{ctrl:02X}", ctrl_detail])
        else:
            QTreeWidgetItem(root_item, ["控制域", f"0x{ctrl:02X}", f"发送序号 N(S):{(ctrl>>5)&0x07} 接收序号 N(R):{(ctrl>>1)&0x07}"])
            
        QTreeWidgetItem(root_item, ["地址域", f"0x{addr:02X}", f"链路地址 (CA): {addr}"])

        if frame_type == "VARIABLE" and "asdu" in parsed:
            asdu = parsed["asdu"]
            asdu_item = QTreeWidgetItem(root_item, ["ASDU数据", asdu.hex(" "), f"长度: {len(asdu)} 字节"])
            
            if len(asdu) >= 3:
                type_id = asdu[0]
                vsq = asdu[1]
                cot = asdu[2]
                QTreeWidgetItem(asdu_item, ["类型标识 (TI)", f"0x{type_id:02X}", f"总召(0x15) 或 其它类型"])
                QTreeWidgetItem(asdu_item, ["可变结构限定词 (VSQ)", f"0x{vsq:02X}", f"信息体个数: {vsq & 0x7F}, 顺序: {(vsq>>7)&1}"])
                QTreeWidgetItem(asdu_item, ["传送原因 (COT)", f"0x{cot:02X}", f"总召(0x2A) 或 激活确认等"])

                if type_id == 0x15:
                    general_items = parse_general_response(data)
                    if general_items:
                        items_node = QTreeWidgetItem(asdu_item, ["信息体列表", f"共 {len(general_items)} 条", ""])
                        for it in general_items:
                            QTreeWidgetItem(items_node, [it.key(), str(it.value), it.description])
                    else:
                        QTreeWidgetItem(asdu_item, ["信息体列表", "无解析数据或解析失败", ""])

        self.tree.expandAll()


# ================= 3. 新增：遥测遥信详情弹窗 =================
class TelemetrySignalDialog(QDialog):
    def __init__(self, items, parent=None):
        super().__init__(parent)
        self.setWindowTitle("遥测遥信数据")
        self.resize(800, 600)
        self.items = items
        self.setFont(QFont("Microsoft YaHei", 10))

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("QTabWidget::pane { border: 1px solid #ccc; } QTabBar::tab { padding: 8px 15px; font-size: 13px; }")

        # 分类列表
        self.telemetry_items = []  # 遥测 (测量值: 0x09, 0x0B, 0x0D)
        self.signal_items = []     # 遥信 (状态量: 0x01, 0x03)

        self._classify_items()

        # 构建两个页签
        self._build_tab("遥测 (测量值)", self.telemetry_items, "telemetry")
        self._build_tab("遥信 (状态量)", self.signal_items, "signal")

        layout.addWidget(self.tab_widget)

        btn_close = QPushButton("关闭")
        btn_close.setFixedWidth(100)
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, 0, Qt.AlignRight)

    def _classify_items(self):
        """根据 IEC 103 类型标识对数据进行分类"""
        for it in self.items:
            # 遥信：单点信息(0x01), 双点信息(0x03)
            if it.data_type in (0x01, 0x03):
                self.signal_items.append(it)
            # 遥测：归一化值(0x09), 标度化值(0x0B), 短浮点数(0x0D)
            elif it.data_type in (0x09, 0x0B, 0x0D):
                self.telemetry_items.append(it)
            # 其他类型为了不丢失数据，也可以放到遥测或专门一栏，这里统一暂放遥测
            else:
                self.telemetry_items.append(it)

    def _build_tab(self, title, item_list, tab_name):
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["组号", "条目号", "类型 (Hex)", "值", "描述"])
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(35)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setFont(QFont("Consolas", 11))
        table.setAlternatingRowColors(True)
        
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        header.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))

        table.setRowCount(len(item_list))
        for row, it in enumerate(item_list):
            table.setItem(row, 0, QTableWidgetItem(str(it.group)))
            table.setItem(row, 1, QTableWidgetItem(str(it.entry)))
            table.setItem(row, 2, QTableWidgetItem(f"0x{it.data_type:02X}"))
            table.setItem(row, 3, QTableWidgetItem(str(it.value)))
            table.setItem(row, 4, QTableWidgetItem(it.description))

        self.tab_widget.addTab(table, f"{title} ({len(item_list)}条)")


# ================= 4. 自定义带水印的表格 =================
class WatermarkTableWidget(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.watermark_text = "双击交互报文可解析"
        self.setAlternatingRowColors(True)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.rowCount() == 0:
            painter = QPainter(self.viewport())
            painter.setPen(QPen(QColor(150, 150, 150), 1))
            painter.setFont(QFont("Microsoft YaHei", 12))
            painter.drawText(self.viewport().rect(), Qt.AlignCenter, self.watermark_text)


# ================= 5. 通讯工作线程 =================
class CommWorker(QThread):
    log_signal = pyqtSignal(str, str)
    result_signal = pyqtSignal(bool, str)
    data_signal = pyqtSignal(list) # 新增：用于回传总召的详细数据
    
    def __init__(self, task_type, settings=None, message=None):
        super().__init__()
        self.task_type = task_type
        self.settings = settings
        self.message = message

    def run(self):
        try:
            if self.task_type == "SEND":
                self.log_signal.emit("TX", self.message)
                time.sleep(0.2)
                self.result_signal.emit(True, "发送完成")

            elif self.task_type == "GENERAL_CALL":
                if not self.settings:
                    self.result_signal.emit(False, "未配置通讯参数")
                    return

                master = SimulatedMaster(
                    host=self.settings.ip,
                    port=self.settings.port,
                    device_addr=self.settings.device_addr,
                    check_comm=self.settings.check_comm,
                    timeout=self.settings.timeout,
                    group_start=self.settings.group_start,
                    group_end=self.settings.group_end
                )
                master.set_log_callback(lambda level, msg: self.log_signal.emit(level, msg))
                success, summary = master.run()
                
                # === 关键：将 SimulatedMaster 中解析出的 items 传给 UI ===
                if success and hasattr(master, 'items'):
                    self.data_signal.emit(master.items)
                elif success:
                    self.data_signal.emit([]) # 防止没有 items 属性时报错

                if success:
                    report_dir = "reports"
                    os.makedirs(report_dir, exist_ok=True)
                    report_path = os.path.join(report_dir, f"general_call_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
                    master.save_report(report_path)
                    summary += f"\n报告已保存至: {report_path}"
                
                self.result_signal.emit(success, summary)

        except Exception as e:
            self.log_signal.emit("ERR", f"总召异常: {str(e)}")
            self.result_signal.emit(False, str(e))


# ================= 6. 主窗口 =================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("模拟主站南网旧版本")
        self.resize(1366, 800)
        
        self.store = SettingStore("config")
        self.conn_settings = self.store.load()
        self.worker = None
        self.called_items = []  # 保存总召召唤上来的数据

        self._init_ui()
        self._bind_events()
        self._check_initial_status()

    def _check_initial_status(self):
        if hasattr(self.conn_settings, 'ip') and self.conn_settings.ip:
            self._update_status(f"参数已加载 ({self.conn_settings.ip}:{self.conn_settings.port})，等待连接", is_error=False)
        else:
            self._update_status("请先进行通讯参数配置（工具栏）", is_error=True)

    def _init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 顶部工具栏
        toolbar_widget = QWidget()
        toolbar_widget.setStyleSheet("background-color: #f5f6f7; border-bottom: 1px solid #d9d9d9;")
        self.toolbar_layout = QHBoxLayout(toolbar_widget)
        self.toolbar_layout.setContentsMargins(8, 8, 8, 8)
        self.toolbar_layout.setSpacing(6)
        
        btn_names = [
            "打开本地子站配置", "保存子站配置", "通讯参数配置", "子站配置",
            "报文交互", "总召状态量", "更新连接状态", "发送校时报文",
            "全站总召归", "告警监视窗", "录波操作", "故障历史信息",
            "通用文件服务", "简要录波列表", "配置检查", "遥测遥信", "联系我们"
        ]
        
        for name in btn_names:
            btn = QToolButton()
            btn.setText(name)
            btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            btn.setIcon(self.style().standardIcon(QStyle.SP_ComputerIcon)) 
            btn.setFixedSize(85, 65)
            btn.setStyleSheet("""
                QToolButton { border: 1px solid #b0b0b0; border-radius: 4px; background-color: #fdfdfd; color: #333; font-size: 12px; padding: 2px; }
                QToolButton:hover { background-color: #e6f7ff; border: 1px solid #40a9ff; color: #0050b3; }
                QToolButton:pressed { background-color: #bae7ff; border: 1px solid #096dd9; }
            """)
            
            if name == "通讯参数配置":
                btn.clicked.connect(self._on_open_comm_settings)
            elif name == "总召状态量":
                btn.clicked.connect(self._on_start_general_call)
            elif name == "遥测遥信":
                btn.clicked.connect(self._on_show_telemetry_signal)  # 绑定新按钮
                
            self.toolbar_layout.addWidget(btn)
            
        self.toolbar_layout.addStretch()
        main_layout.addWidget(toolbar_widget)

        # 主体分割器
        splitter = QSplitter(Qt.Horizontal)
        
        # 左侧边栏
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        
        left_header = QLabel("子站配置")
        left_header.setStyleSheet("background-color: #fafafa; border-bottom: 1px solid #e8e8e8; padding: 10px; font-weight: bold; font-size: 13px; color: #333;")
        self.tree_devices = QTreeWidget()
        self.tree_devices.setHeaderHidden(True)
        self.tree_devices.setFont(QFont("Microsoft YaHei", 10))
        self.tree_devices.setStyleSheet("QTreeWidget { border: none; background-color: #ffffff; } QTreeWidget::item { height: 30px; }")
        
        root_node = QTreeWidgetItem(self.tree_devices, ["默认子站"])
        QTreeWidgetItem(root_node, ["保护装置1 (CA=1)"])
        QTreeWidgetItem(root_node, ["保护装置2 (CA=2)"])
        self.tree_devices.expandAll()
        
        left_layout.addWidget(left_header)
        left_layout.addWidget(self.tree_devices)
        splitter.addWidget(left_widget)

        # 右侧工作区
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        input_frame = QFrame()
        input_frame.setStyleSheet("background-color: #fafafa; border-bottom: 1px solid #d9d9d9;")
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(15, 12, 15, 12)
        input_layout.setSpacing(12)

        lbl_input = QLabel("输入报文")
        lbl_input.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        input_layout.addWidget(lbl_input)
        
        self.input_msg = QLineEdit()
        self.input_msg.setPlaceholderText("请输入报文...")
        self.input_msg.setFont(QFont("Consolas", 11))
        self.input_msg.setStyleSheet("padding: 6px 10px; border: 1px solid #b0b0b0; border-radius: 3px;")
        self.input_msg.setMinimumHeight(35)
        
        self.btn_parse = QPushButton("解析")
        self.btn_send = QPushButton("发送")
        self.btn_disconnect = QPushButton("断开连接")
        self.btn_reconnect = QPushButton("重新连接")

        for btn in [self.btn_parse, self.btn_send, self.btn_disconnect, self.btn_reconnect]:
            btn.setMinimumHeight(35)
            btn.setMinimumWidth(80)
            btn.setFont(QFont("Microsoft YaHei", 10))
            btn.setStyleSheet("""
                QPushButton { background-color: #ffffff; border: 1px solid #b0b0b0; border-radius: 3px; color: #333; }
                QPushButton:hover { color: #40a9ff; border-color: #40a9ff; background-color: #f0f7ff; }
                QPushButton:pressed { color: #096dd9; border-color: #096dd9; background-color: #d6e4ff; }
            """)

        input_layout.addWidget(self.input_msg, 1)
        input_layout.addWidget(self.btn_parse)
        input_layout.addWidget(self.btn_send)
        input_layout.addStretch(1)
        input_layout.addWidget(self.btn_disconnect)
        input_layout.addWidget(self.btn_reconnect)
        right_layout.addWidget(input_frame)

        self.table = WatermarkTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["交互时间", "互方", "交互内容", "交互报文"])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(35)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setFont(QFont("Consolas", 11))
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        
        self.table.setStyleSheet("""
            QTableWidget { border: none; gridline-color: #e0e0e0; }
            QHeaderView::section { background-color: #f0f0f0; border-bottom: 1px solid #b0b0b0; border-right: 1px solid #d9d9d9; padding: 8px; color: #333; }
            QTableWidget::item { padding: 6px; }
            QTableWidget::item:alternate { background-color: #f9fbfd; }
        """)
        right_layout.addWidget(self.table, 1)
        
        splitter.addWidget(right_widget)
        splitter.setSizes([220, 1140])
        main_layout.addWidget(splitter, 1)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.setStyleSheet("QStatusBar { background-color: #f5f6f7; border-top: 1px solid #b0b0b0; } QStatusBar::item { border: none; }")
        self.status_bar.setFont(QFont("Microsoft YaHei", 10))
        self.status_bar.setFixedHeight(30)
        
        self.lbl_comm_status = QLabel()
        self.lbl_io_status = QLabel("收发状态：无数据交互")
        self.status_bar.addWidget(self.lbl_comm_status)
        self.status_bar.addPermanentWidget(self.lbl_io_status)

    def _bind_events(self):
        self.btn_parse.clicked.connect(self._on_parse_message)
        self.btn_send.clicked.connect(self._on_send_message)
        self.btn_disconnect.clicked.connect(self._on_disconnect)
        self.btn_reconnect.clicked.connect(self._on_reconnect)
        self.table.itemDoubleClicked.connect(self._on_table_double_click)

    def _update_status(self, text, is_error=False):
        self.lbl_comm_status.setText(f"通讯状态：{text}")
        color = "#d32f2f" if is_error else "#389e0d"
        self.lbl_comm_status.setStyleSheet(f"color: {color}; font-weight: bold;")

    def _on_open_comm_settings(self):
        dialog = CommSettingsDialog(self.conn_settings, self)
        if dialog.exec_() == QDialog.Accepted:
            self.conn_settings = dialog.get_settings()
            self.store.save(self.conn_settings)
            self._update_status(f"参数已保存 ({self.conn_settings.ip}:{self.conn_settings.port})", is_error=False)
            QMessageBox.information(self, "成功", "通讯参数已保存！")

    def _on_parse_message(self):
        msg = self.input_msg.text().strip()
        if not msg:
            QMessageBox.warning(self, "提示", "请输入报文！")
            return
        dialog = MessageDetailDialog(msg, self)
        dialog.exec_()

    def _on_send_message(self):
        msg = self.input_msg.text().strip()
        if not msg:
            QMessageBox.warning(self, "提示", "请输入报文！")
            return
        self._append_table_row("TX", msg)
        self.input_msg.clear()
        self.lbl_io_status.setText("收发状态：数据交互中")

    def _on_start_general_call(self):
        if not hasattr(self.conn_settings, 'ip') or not self.conn_settings.ip:
            QMessageBox.warning(self, "未配置", "请先点击工具栏的【通讯参数配置】设置子站 IP 和端口！")
            return
        
        reply = QMessageBox.question(self, "确认", 
                                     f"即将连接子站 {self.conn_settings.ip}:{self.conn_settings.port} 执行总召，是否继续？",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if reply == QMessageBox.No:
            return

        self._update_status("正在执行总召...", is_error=False)
        self.lbl_io_status.setText("收发状态：正在总召")
        self.table.setRowCount(0)
        self.called_items.clear() # 清空之前的数据

        self.worker = CommWorker("GENERAL_CALL", settings=self.conn_settings)
        self.worker.log_signal.connect(self._append_table_row)
        self.worker.result_signal.connect(self._on_general_call_finished)
        self.worker.data_signal.connect(self._on_receive_items) # 接收数据
        self.worker.start()

    def _on_receive_items(self, items):
        """接收总召回来的数据并缓存"""
        self.called_items = items

    def _on_general_call_finished(self, success, summary):
        if success:
            self._update_status("总召已完成", is_error=False)
            self.lbl_io_status.setText("收发状态：无数据交互")
            QMessageBox.information(self, "总召结果", summary)
        else:
            self._update_status(f"总召失败: {summary}", is_error=True)
            self.lbl_io_status.setText("收发状态：总召失败")
            QMessageBox.critical(self, "总召失败", summary)

    # ================= 新增：显示遥测遥信数据 =================
    def _on_show_telemetry_signal(self):
        if not self.called_items:
            QMessageBox.information(self, "提示", "暂未召唤到数据。请先执行【总召状态量】操作。")
            return
        
        dialog = TelemetrySignalDialog(self.called_items, self)
        dialog.exec_()

    def _on_disconnect(self):
        self._update_status("已断开连接", is_error=True)
        self.lbl_io_status.setText("收发状态：已断开")

    def _on_reconnect(self):
        self._update_status("连接中...", is_error=False)
        self.lbl_io_status.setText("收发状态：正在重连")

    def _on_table_double_click(self, item):
        row = item.row()
        raw_msg = self.table.item(row, 3).text()
        if not raw_msg:
            return
        dialog = MessageDetailDialog(raw_msg, self)
        dialog.exec_()

    def _append_table_row(self, level, message):
        row = self.table.rowCount()
        self.table.insertRow(row)
        
        now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.table.setItem(row, 0, QTableWidgetItem(now))
        peer = "主站" if level == "TX" else ("子站" if level == "RX" else "系统")
        self.table.setItem(row, 1, QTableWidgetItem(peer))
        self.table.setItem(row, 2, QTableWidgetItem(level))
        self.table.setItem(row, 3, QTableWidgetItem(message))
        
        self.table.scrollToBottom()


if __name__ == "__main__":
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    
    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei", 10))
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())