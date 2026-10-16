# -*- coding: utf-8 -*-
import sys
import os
import time
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QToolButton, QLabel, QLineEdit, QPushButton, QTableWidget, 
    QTableWidgetItem, QHeaderView, QSplitter, QTreeWidget, 
    QTreeWidgetItem, QStatusBar, QFrame, QMessageBox, QAbstractItemView
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QIcon, QFont, QColor, QPainter, QPen, QBrush

# ================= 导入项目原有模块（若未就绪，请保持注释或用占位符） =================
try:
    from settings import SettingStore
    from master import SimulatedMaster
    from protocol import FrameCodec, parse_general_response
except ImportError as e:
    print(f"警告: 部分核心模块未找到，请检查目录结构。错误: {e}")

# ================= 自定义带水印的表格 =================
class WatermarkTableWidget(QTableWidget):
    """重写 paintEvent，实现空数据时居中显示'双击交互报文可解析'水印"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.watermark_text = "双击交互报文可解析"

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.rowCount() == 0:
            painter = QPainter(self.viewport())
            painter.setPen(QPen(QColor(150, 150, 150), 1))
            font = QFont("Microsoft YaHei", 10)
            painter.setFont(font)
            painter.drawText(self.viewport().rect(), Qt.AlignCenter, self.watermark_text)


# ================= 通讯工作线程 (防止界面卡死) =================
class CommWorker(QThread):
    log_signal = pyqtSignal(str, str)     # level, message
    result_signal = pyqtSignal(bool, str) # success, summary
    
    def __init__(self, task_type, config=None, message=None):
        super().__init__()
        self.task_type = task_type
        self.config = config
        self.message = message

    def run(self):
        try:
            if self.task_type == "SEND":
                # TODO: 接入 protocol.py 中的实际发送逻辑
                self.log_signal.emit("TX", f"发送报文: {self.message}")
                time.sleep(0.5) # 模拟网络延迟
                self.result_signal.emit(True, "发送成功")
                
            elif self.task_type == "GENERAL_CALL":
                # TODO: 接入 master.py 的 SimulatedMaster 逻辑
                self.log_signal.emit("INFO", "启动总召...")
                time.sleep(1) # 模拟总召耗时
                self.result_signal.emit(True, "总召完成，发现 0 组数据")
                
        except Exception as e:
            self.result_signal.emit(False, str(e))


# ================= 主窗口 =================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("模拟主站南网旧版本")
        self.resize(1280, 768)
        
        self.store = SettingStore("config")
        self.conn_settings = self.store.load()
        self.master = None
        self.worker = None

        self._init_ui()
        self._bind_events()
        self._update_status("请先进行通讯参数配置（工具栏）", is_error=True)

    def _init_ui(self):
        # 1. 主布局
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 2. 顶部工具栏
        toolbar_widget = QWidget()
        toolbar_widget.setStyleSheet("background-color: #f5f6f7; border-bottom: 1px solid #d9d9d9;")
        self.toolbar_layout = QHBoxLayout(toolbar_widget)
        self.toolbar_layout.setContentsMargins(5, 5, 5, 5)
        self.toolbar_layout.setSpacing(2)
        
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
            # 使用系统内置图标占位，实际可替换为 icons 目录下的图标
            btn.setIcon(QIcon.fromTheme("application-x-executable")) 
            btn.setFixedSize(72, 58)
            btn.setStyleSheet("""
                QToolButton { border: 1px solid transparent; border-radius: 3px; color: #333; font-size: 11px; }
                QToolButton:hover { background-color: #e6f7ff; border: 1px solid #91d5ff; }
                QToolButton:pressed { background-color: #bae7ff; }
            """)
            # 给按钮绑定信号（示例）
            if name == "总召状态量":
                btn.clicked.connect(lambda checked, n=name: self._on_start_general_call())
            self.toolbar_layout.addWidget(btn)
            
        self.toolbar_layout.addStretch()
        main_layout.addWidget(toolbar_widget)

        # 3. 主体分割器
        splitter = QSplitter(Qt.Horizontal)
        
        # -- 3.1 左侧边栏 --
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        left_header = QLabel("子站配置")
        left_header.setStyleSheet("background-color: #fafafa; border-bottom: 1px solid #e8e8e8; padding: 6px 10px; font-weight: bold; color: #333;")
        self.tree_devices = QTreeWidget()
        self.tree_devices.setHeaderHidden(True)
        self.tree_devices.setStyleSheet("QTreeWidget { border: none; background-color: #ffffff; }")
        
        # 添加示例树节点
        root_node = QTreeWidgetItem(self.tree_devices, ["默认子站"])
        QTreeWidgetItem(root_node, ["保护装置1 (CA=1)"])
        QTreeWidgetItem(root_node, ["保护装置2 (CA=2)"])
        self.tree_devices.expandAll()
        
        left_layout.addWidget(left_header)
        left_layout.addWidget(self.tree_devices)
        splitter.addWidget(left_widget)

        # -- 3.2 右侧主工作区 --
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # 输入控制栏
        input_frame = QFrame()
        input_frame.setStyleSheet("background-color: #fafafa; border-bottom: 1px solid #d9d9d9;")
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(10, 8, 10, 8)
        input_layout.setSpacing(8)

        input_layout.addWidget(QLabel("输入报文"))
        self.input_msg = QLineEdit()
        self.input_msg.setPlaceholderText("请输入报文...")
        self.input_msg.setStyleSheet("padding: 4px 8px; border: 1px solid #d9d9d9; border-radius: 2px; font-family: Consolas;")
        
        self.btn_parse = QPushButton("解析")
        self.btn_send = QPushButton("发送")
        
        # 右侧连接控制
        self.btn_disconnect = QPushButton("断开连接")
        self.btn_reconnect = QPushButton("重新连接")

        for btn in [self.btn_parse, self.btn_send, self.btn_disconnect, self.btn_reconnect]:
            btn.setStyleSheet("""
                QPushButton { background-color: #ffffff; border: 1px solid #d9d9d9; border-radius: 2px; padding: 4px 15px; color: #333; }
                QPushButton:hover { color: #40a9ff; border-color: #40a9ff; }
                QPushButton:pressed { color: #096dd9; border-color: #096dd9; }
            """)

        input_layout.addWidget(self.input_msg, 1)
        input_layout.addWidget(self.btn_parse)
        input_layout.addWidget(self.btn_send)
        input_layout.addStretch(1) # 弹性空间
        input_layout.addWidget(self.btn_disconnect)
        input_layout.addWidget(self.btn_reconnect)
        
        right_layout.addWidget(input_frame)

        # 报文表格
        self.table = WatermarkTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["交互时间", "互方", "交互内容", "交互报文"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers) # 表格只读
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch) # 报文列撑满
        
        self.table.setStyleSheet("""
            QTableWidget { border: none; gridline-color: #f0f0f0; }
            QHeaderView::section { background-color: #fafafa; border-bottom: 1px solid #d9d9d9; border-right: 1px solid #f0f0f0; padding: 6px; font-weight: normal; color: #666; }
            QTableWidget::item { padding: 4px; }
        """)
        
        right_layout.addWidget(self.table, 1)
        splitter.addWidget(right_widget)
        
        splitter.setSizes([200, 1080])
        main_layout.addWidget(splitter, 1)

        # 4. 底部状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.setStyleSheet("QStatusBar { background-color: #f5f6f7; border-top: 1px solid #d9d9d9; } QStatusBar::item { border: none; }")
        
        self.lbl_comm_status = QLabel()
        self.lbl_io_status = QLabel("收发状态：无数据交互")
        
        self.status_bar.addWidget(self.lbl_comm_status)
        self.status_bar.addPermanentWidget(self.lbl_io_status)

    def _bind_events(self):
        """绑定事件与槽函数"""
        self.btn_parse.clicked.connect(self._on_parse_message)
        self.btn_send.clicked.connect(self._on_send_message)
        self.btn_disconnect.clicked.connect(self._on_disconnect)
        self.btn_reconnect.clicked.connect(self._on_reconnect)
        self.table.itemDoubleClicked.connect(self._on_table_double_click)

    # ================= 状态更新 =================
    def _update_status(self, text, is_error=False):
        self.lbl_comm_status.setText(f"通讯状态：{text}")
        color = "#d32f2f" if is_error else "#389e0d" # 红色或绿色
        self.lbl_comm_status.setStyleSheet(f"color: {color}; font-weight: bold;")

    # ================= 业务逻辑槽函数 =================

    def _on_parse_message(self):
        msg = self.input_msg.text().strip()
        if not msg:
            QMessageBox.warning(self, "提示", "请输入报文！")
            return
        # TODO: 调用 protocol.py 的解析逻辑
        QMessageBox.information(self, "解析结果", f"正在解析报文：\n{msg}\n\n(此处接入 FrameCodec.parse 逻辑)")

    def _on_send_message(self):
        msg = self.input_msg.text().strip()
        if not msg:
            QMessageBox.warning(self, "提示", "请输入报文！")
            return
        
        # 更新表格
        self._append_table_row("主站", "发送报文", msg)
        self.input_msg.clear()
        self.lbl_io_status.setText("收发状态：数据交互中")
        
        # 启动线程发送
        self.worker = CommWorker("SEND", message=msg)
        self.worker.log_signal.connect(self._append_table_row)
        self.worker.start()

    def _on_start_general_call(self):
        self._update_status("正在执行总召...", is_error=False)
        self.worker = CommWorker("GENERAL_CALL")
        self.worker.log_signal.connect(self._append_table_row)
        self.worker.result_signal.connect(self._on_worker_result)
        self.worker.start()

    def _on_disconnect(self):
        self._update_status("已断开连接", is_error=True)

    def _on_reconnect(self):
        self._update_status("连接中...", is_error=False)
        # TODO: 接入 master.py 的实际连接逻辑
        
    def _on_table_double_click(self, item):
        row = item.row()
        msg = self.table.item(row, 3).text()
        QMessageBox.information(self, "报文解析", f"双击解析报文：\n{msg}\n\n(此处接入详细解析视图)")

    def _append_table_row(self, level, message):
        """向表格追加记录"""
        row = self.table.rowCount()
        self.table.insertRow(row)
        
        now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.table.setItem(row, 0, QTableWidgetItem(now))
        self.table.setItem(row, 1, QTableWidgetItem("主站" if level in ["TX", "INFO"] else "子站"))
        self.table.setItem(row, 2, QTableWidgetItem(level))
        self.table.setItem(row, 3, QTableWidgetItem(message))
        
        self.table.scrollToBottom()

    def _on_worker_result(self, success, summary):
        if success:
            self._update_status("已完成", is_error=False)
        else:
            self._update_status(f"失败: {summary}", is_error=True)


if __name__ == "__main__":
    # 适配高分屏
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    
    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei", 9))
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())