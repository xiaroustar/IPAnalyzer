import sys
import re
import threading
import time
import webbrowser
from datetime import datetime
from typing import Optional, List, Tuple, Dict
import json
import traceback
import sqlite3
from pathlib import Path
import os

import pyperclip
import requests
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QPushButton, QTextEdit,
                             QSystemTrayIcon, QMenu, QMessageBox, QTableWidget,
                             QTableWidgetItem, QTabWidget, QSplitter,
                             QHeaderView, QAbstractItemView, QDialog,
                             QFormLayout, QLineEdit, QCheckBox, QDoubleSpinBox,
                             QFileDialog, QMenu, QTextBrowser, QDialogButtonBox)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QSize, QThread, pyqtSignal
from PyQt6.QtGui import QIcon, QAction, QFont, QPixmap, QPainter, QColor, QBrush
from plyer import notification

# 修复 win10toast 导入警告
import warnings

warnings.filterwarnings("ignore", message="pkg_resources is deprecated")

try:
    import win10toast

    WIN10TOAST_AVAILABLE = True
except ImportError:
    WIN10TOAST_AVAILABLE = False
    print("win10toast 不可用，将使用其他通知方式")

from config import Config, DatabaseManager


class APIChecker(QThread):
    """API检查线程"""
    status_updated = pyqtSignal(str, str)  # (status, message)

    def __init__(self):
        super().__init__()
        self.api_url = "https://ipv4.ink"
        self.running = True

    def run(self):
        while self.running:
            try:
                # 测试连接API
                response = requests.get(f"{self.api_url}/", timeout=5)

                if response.status_code == 200:
                    self.status_updated.emit("connected", "API连接正常")
                else:
                    self.status_updated.emit("disconnected", f"API响应异常: {response.status_code}")

            except requests.exceptions.ConnectionError:
                self.status_updated.emit("disconnected", "网络连接失败")
            except requests.exceptions.Timeout:
                self.status_updated.emit("disconnected", "连接超时")
            except Exception as e:
                self.status_updated.emit("disconnected", f"连接错误: {str(e)}")

            # 每30秒检查一次
            for _ in range(30):
                if not self.running:
                    break
                time.sleep(1)

    def stop(self):
        self.running = False


class DetailDialog(QDialog):
    """详细信息对话框"""

    def __init__(self, title, content, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setFixedSize(600, 400)

        layout = QVBoxLayout(self)

        # 文本浏览器
        self.text_browser = QTextBrowser()
        self.text_browser.setPlainText(content)
        self.text_browser.setFont(QFont("Consolas", 10))

        # 按钮
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)

        layout.addWidget(self.text_browser)
        layout.addWidget(button_box)


class HistoryWindow(QDialog):
    """历史记录窗口"""

    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.setup_ui()
        self.load_history()

    def setup_ui(self):
        self.setWindowTitle("IP查询历史记录")
        self.setFixedSize(900, 500)

        layout = QVBoxLayout(self)

        # 控制按钮
        control_layout = QHBoxLayout()

        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self.load_history)

        self.clear_btn = QPushButton("清空记录")
        self.clear_btn.clicked.connect(self.clear_history)
        self.clear_btn.setStyleSheet("background-color: #ff4444; color: white;")

        self.export_btn = QPushButton("导出记录")
        self.export_btn.clicked.connect(self.export_history)

        control_layout.addWidget(self.refresh_btn)
        control_layout.addWidget(self.clear_btn)
        control_layout.addWidget(self.export_btn)
        control_layout.addStretch()

        layout.addLayout(control_layout)

        # 历史记录表格
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "时间", "IP地址", "类型", "国家", "省份", "城市", "运营商", "操作"
        ])

        # 设置表格属性
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        # 启用右键菜单
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)

        # 连接双击事件
        self.table.doubleClicked.connect(self.on_table_double_click)

        layout.addWidget(self.table)

    def load_history(self):
        """加载历史记录"""
        history = self.db_manager.get_history()
        self.table.setRowCount(len(history))

        for row, record in enumerate(history):
            # 时间
            time_item = QTableWidgetItem(record[1])
            self.table.setItem(row, 0, time_item)

            # IP地址
            ip_item = QTableWidgetItem(record[2])
            self.table.setItem(row, 1, ip_item)

            # IP类型
            type_item = QTableWidgetItem(record[3])
            self.table.setItem(row, 2, type_item)

            # 国家
            country_item = QTableWidgetItem(record[4] if record[4] else "未知")
            self.table.setItem(row, 3, country_item)

            # 省份
            province_item = QTableWidgetItem(record[5] if record[5] else "未知")
            self.table.setItem(row, 4, province_item)

            # 城市
            city_item = QTableWidgetItem(record[6] if record[6] else "未知")
            self.table.setItem(row, 5, city_item)

            # 运营商
            isp_item = QTableWidgetItem(record[7] if record[7] else "未知")
            self.table.setItem(row, 6, isp_item)

            # 操作按钮
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(0, 0, 0, 0)

            view_btn = QPushButton("查看")
            view_btn.clicked.connect(lambda checked, ip=record[2]: self.view_ip_details(ip))
            view_btn.setStyleSheet("padding: 2px 5px; font-size: 12px;")

            copy_btn = QPushButton("复制")
            copy_btn.clicked.connect(lambda checked, ip=record[2]: self.copy_ip(ip))
            copy_btn.setStyleSheet("padding: 2px 5px; font-size: 12px;")

            btn_layout.addWidget(view_btn)
            btn_layout.addWidget(copy_btn)
            self.table.setCellWidget(row, 7, btn_widget)

    def show_context_menu(self, position):
        """显示右键菜单"""
        row = self.table.rowAt(position.y())
        if row >= 0:
            menu = QMenu()

            # 获取选中行的IP地址
            ip = self.table.item(row, 1).text()

            # 添加菜单项
            copy_action = QAction("复制IP地址", self)
            copy_action.triggered.connect(lambda: self.copy_ip(ip))

            view_action = QAction("查看详情", self)
            view_action.triggered.connect(lambda: self.view_ip_details(ip))

            delete_action = QAction("删除记录", self)
            delete_action.triggered.connect(lambda: self.delete_record(row))

            menu.addAction(copy_action)
            menu.addAction(view_action)
            menu.addAction(delete_action)

            menu.exec(self.table.viewport().mapToGlobal(position))

    def on_table_double_click(self, index):
        """表格双击事件"""
        row = index.row()
        if row >= 0:
            # 获取该行所有数据
            time_str = self.table.item(row, 0).text()
            ip = self.table.item(row, 1).text()
            ip_type = self.table.item(row, 2).text()
            country = self.table.item(row, 3).text()
            province = self.table.item(row, 4).text()
            city = self.table.item(row, 5).text()
            isp = self.table.item(row, 6).text()

            # 构建详细内容
            details = f"查询时间: {time_str}\n"
            details += f"IP地址: {ip}\n"
            details += f"IP类型: {ip_type}\n"
            details += f"地理位置: {country} - {province} - {city}\n"
            details += f"网络运营商: {isp}\n"

            # 显示对话框
            dialog = DetailDialog(f"IP详情 - {ip}", details, self)
            dialog.exec()

    def delete_record(self, row):
        """删除单条记录"""
        ip = self.table.item(row, 1).text()
        time_str = self.table.item(row, 0).text()

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除IP地址为 {ip} 的记录吗？\n查询时间: {time_str}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            success = self.db_manager.delete_record_by_ip_and_time(ip, time_str)
            if success:
                self.load_history()
                QMessageBox.information(self, "成功", "记录已删除")
            else:
                QMessageBox.critical(self, "错误", "删除记录失败")

    def view_ip_details(self, ip):
        """查看IP详情"""
        webbrowser.open(f"https://ipv4.ink/{ip}")

    def copy_ip(self, ip):
        """复制IP地址"""
        pyperclip.copy(ip)
        QMessageBox.information(self, "成功", f"已复制IP地址: {ip}")

    def clear_history(self):
        """清空历史记录"""
        reply = QMessageBox.question(
            self, "确认清空",
            "确定要清空所有历史记录吗？此操作不可恢复！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            success = self.db_manager.clear_history()
            if success:
                self.load_history()
                QMessageBox.information(self, "成功", "历史记录已清空")
            else:
                QMessageBox.critical(self, "错误", "清空历史记录失败")

    def export_history(self):
        """导出历史记录"""
        try:
            # 使用文件对话框选择保存位置
            default_filename = f"ip_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "导出历史记录",
                default_filename,
                "JSON文件 (*.json);;所有文件 (*.*)"
            )

            if not file_path:
                return  # 用户取消

            history = self.db_manager.get_history(limit=1000)  # 导出所有记录
            export_data = []

            for record in history:
                export_data.append({
                    "time": record[1],
                    "ip": record[2],
                    "type": record[3],
                    "country": record[4],
                    "province": record[5],
                    "city": record[6],
                    "isp": record[7],
                    "query_time": record[8]
                })

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)

            QMessageBox.information(self, "导出成功", f"历史记录已导出到:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出失败: {str(e)}")


class ClipboardHistoryWindow(QDialog):
    """剪贴板历史记录窗口"""

    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.setup_ui()
        self.load_clipboard_history()

    def setup_ui(self):
        self.setWindowTitle("剪贴板历史记录")
        self.setFixedSize(900, 500)

        layout = QVBoxLayout(self)

        # 控制按钮
        control_layout = QHBoxLayout()

        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self.load_clipboard_history)

        self.clear_btn = QPushButton("清空记录")
        self.clear_btn.clicked.connect(self.clear_clipboard_history)
        self.clear_btn.setStyleSheet("background-color: #ff4444; color: white;")

        self.export_btn = QPushButton("导出记录")
        self.export_btn.clicked.connect(self.export_clipboard_history)

        control_layout.addWidget(self.refresh_btn)
        control_layout.addWidget(self.clear_btn)
        control_layout.addWidget(self.export_btn)
        control_layout.addStretch()

        layout.addLayout(control_layout)

        # 历史记录表格
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels([
            "时间", "剪贴板内容", "包含IP", "操作"
        ])

        # 设置表格属性
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        # 启用右键菜单
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)

        # 连接双击事件
        self.table.doubleClicked.connect(self.on_table_double_click)

        layout.addWidget(self.table)

    def load_clipboard_history(self):
        """加载剪贴板历史记录"""
        history = self.db_manager.get_clipboard_history()
        self.table.setRowCount(len(history))

        for row, record in enumerate(history):
            # 时间
            time_item = QTableWidgetItem(record[1])
            self.table.setItem(row, 0, time_item)

            # 剪贴板内容
            content = record[2]
            # 截断长内容
            if len(content) > 100:
                display_content = content[:100] + "..."
            else:
                display_content = content
            content_item = QTableWidgetItem(display_content)
            content_item.setToolTip(content)  # 鼠标悬停显示完整内容
            self.table.setItem(row, 1, content_item)

            # 包含IP
            contains_ip = record[3]
            ip_item = QTableWidgetItem("是" if contains_ip else "否")
            self.table.setItem(row, 2, ip_item)

            # 操作按钮
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(0, 0, 0, 0)

            copy_btn = QPushButton("复制")
            copy_btn.clicked.connect(lambda checked, content=content: self.copy_content(content))
            copy_btn.setStyleSheet("padding: 2px 5px; font-size: 12px;")

            view_btn = QPushButton("查看")
            view_btn.clicked.connect(lambda checked, content=content: self.view_content(content))
            view_btn.setStyleSheet("padding: 2px 5px; font-size: 12px;")

            btn_layout.addWidget(view_btn)
            btn_layout.addWidget(copy_btn)
            self.table.setCellWidget(row, 3, btn_widget)

    def show_context_menu(self, position):
        """显示右键菜单"""
        row = self.table.rowAt(position.y())
        if row >= 0:
            menu = QMenu()

            # 获取选中行的数据
            content = self.table.item(row, 1).toolTip() or self.table.item(row, 1).text()

            # 添加菜单项
            copy_action = QAction("复制内容", self)
            copy_action.triggered.connect(lambda: self.copy_content(content))

            view_action = QAction("查看详情", self)
            view_action.triggered.connect(lambda: self.view_content(content))

            delete_action = QAction("删除记录", self)
            delete_action.triggered.connect(lambda: self.delete_record(row))

            menu.addAction(copy_action)
            menu.addAction(view_action)
            menu.addAction(delete_action)

            menu.exec(self.table.viewport().mapToGlobal(position))

    def on_table_double_click(self, index):
        """表格双击事件"""
        row = index.row()
        if row >= 0:
            # 获取该行所有数据
            time_str = self.table.item(row, 0).text()
            content = self.table.item(row, 1).toolTip() or self.table.item(row, 1).text()
            contains_ip = self.table.item(row, 2).text()

            # 构建详细内容
            details = f"记录时间: {time_str}\n"
            details += f"包含IP: {contains_ip}\n"
            details += f"内容长度: {len(content)} 字符\n"
            details += f"\n完整内容:\n{'-' * 40}\n{content}\n{'-' * 40}"

            # 显示对话框
            dialog = DetailDialog("剪贴板内容详情", details, self)
            dialog.exec()

    def delete_record(self, row):
        """删除单条记录"""
        time_str = self.table.item(row, 0).text()
        content_preview = self.table.item(row, 1).text()

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除这条记录吗？\n时间: {time_str}\n内容: {content_preview}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            success = self.db_manager.delete_clipboard_record_by_time(time_str)
            if success:
                self.load_clipboard_history()
                QMessageBox.information(self, "成功", "记录已删除")
            else:
                QMessageBox.critical(self, "错误", "删除记录失败")

    def copy_content(self, content):
        """复制内容"""
        pyperclip.copy(content)
        QMessageBox.information(self, "成功", "已复制内容到剪贴板")

    def view_content(self, content):
        """查看内容详情"""
        dialog = DetailDialog("剪贴板内容详情", content, self)
        dialog.exec()

    def clear_clipboard_history(self):
        """清空剪贴板历史记录"""
        reply = QMessageBox.question(
            self, "确认清空",
            "确定要清空所有剪贴板历史记录吗？此操作不可恢复！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            success = self.db_manager.clear_clipboard_history()
            if success:
                self.load_clipboard_history()
                QMessageBox.information(self, "成功", "剪贴板历史记录已清空")
            else:
                QMessageBox.critical(self, "错误", "清空历史记录失败")

    def export_clipboard_history(self):
        """导出剪贴板历史记录"""
        try:
            # 使用文件对话框选择保存位置
            default_filename = f"clipboard_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "导出剪贴板历史记录",
                default_filename,
                "JSON文件 (*.json);;所有文件 (*.*)"
            )

            if not file_path:
                return  # 用户取消

            history = self.db_manager.get_clipboard_history(limit=1000)
            export_data = []

            for record in history:
                export_data.append({
                    "time": record[1],
                    "content": record[2],
                    "contains_ip": bool(record[3])
                })

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)

            QMessageBox.information(self, "导出成功", f"剪贴板历史记录已导出到:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出失败: {str(e)}")


class UpdateChecker(QThread):
    """更新检查线程"""
    update_available = pyqtSignal(dict)  # 传递更新信息
    check_completed = pyqtSignal(bool, str)  # (是否有更新, 消息)

    def __init__(self, config):
        super().__init__()
        self.config = config

    def run(self):
        try:
            # 检查更新
            print("正在检查更新...")
            remote_info = self.config.check_for_updates()
            print(f"获取到的更新信息: {remote_info}")

            if remote_info and 'version' in remote_info:
                remote_version = remote_info['version']
                print(f"远程版本: {remote_version}, 本地版本: {self.config.app_version}")

                if self.config.is_new_version_available(remote_version):
                    print(f"发现新版本: {remote_version}")
                    # 确保在主线程中发射信号
                    self.update_available.emit(remote_info)
                    self.check_completed.emit(True, f"发现新版本 {remote_version}")
                else:
                    print("当前已是最新版本")
                    self.check_completed.emit(False, "当前已是最新版本")
            else:
                print("检查更新失败或无更新信息")
                self.check_completed.emit(False, "检查更新失败或网络错误")

        except Exception as e:
            print(f"检查更新异常: {e}")
            self.check_completed.emit(False, f"检查更新失败: {str(e)}")


class SettingsWindow(QDialog):
    """设置窗口"""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.parent_window = parent
        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        self.setWindowTitle("设置")
        self.setFixedSize(450, 400)

        layout = QVBoxLayout(self)

        # 自启动设置
        self.auto_start_cb = QCheckBox("开机自启动")
        self.auto_start_cb.stateChanged.connect(self.on_auto_start_changed)
        layout.addWidget(self.auto_start_cb)

        # 自启动状态标签
        self.auto_start_status = QLabel("状态: 检测中...")
        self.auto_start_status.setStyleSheet("color: #666; font-size: 10pt;")
        layout.addWidget(self.auto_start_status)

        # 分隔线
        line1 = QWidget()
        line1.setFixedHeight(1)
        line1.setStyleSheet("background-color: #ddd;")
        layout.addWidget(line1)

        # 剪贴板检查间隔
        interval_widget = QWidget()
        interval_layout = QHBoxLayout(interval_widget)
        interval_layout.setContentsMargins(0, 0, 0, 0)

        interval_label = QLabel("检查间隔:")
        self.interval_spin = QDoubleSpinBox()
        self.interval_spin.setRange(0.5, 10.0)
        self.interval_spin.setSingleStep(0.5)
        self.interval_spin.setSuffix(" 秒")

        interval_layout.addWidget(interval_label)
        interval_layout.addStretch()
        interval_layout.addWidget(self.interval_spin)
        layout.addWidget(interval_widget)

        # 通知设置
        self.notify_cb = QCheckBox("显示桌面通知")
        layout.addWidget(self.notify_cb)

        # IP类型设置
        ip_type_widget = QWidget()
        ip_type_layout = QHBoxLayout(ip_type_widget)
        ip_type_layout.setContentsMargins(0, 0, 0, 0)

        ip_type_label = QLabel("检测类型:")
        self.ipv4_cb = QCheckBox("IPv4")
        self.ipv6_cb = QCheckBox("IPv6")

        ip_type_layout.addWidget(ip_type_label)
        ip_type_layout.addWidget(self.ipv4_cb)
        ip_type_layout.addWidget(self.ipv6_cb)
        ip_type_layout.addStretch()
        layout.addWidget(ip_type_widget)

        # 通知超时时间
        timeout_widget = QWidget()
        timeout_layout = QHBoxLayout(timeout_widget)
        timeout_layout.setContentsMargins(0, 0, 0, 0)

        timeout_label = QLabel("通知显示:")
        self.timeout_spin = QDoubleSpinBox()
        self.timeout_spin.setRange(3, 30)
        self.timeout_spin.setSingleStep(1)
        self.timeout_spin.setSuffix(" 秒")

        timeout_layout.addWidget(timeout_label)
        timeout_layout.addStretch()
        timeout_layout.addWidget(self.timeout_spin)
        layout.addWidget(timeout_widget)

        # 分隔线
        line2 = QWidget()
        line2.setFixedHeight(1)
        line2.setStyleSheet("background-color: #ddd;")
        layout.addWidget(line2)

        # 更新设置
        self.auto_update_cb = QCheckBox("自动检查更新")
        layout.addWidget(self.auto_update_cb)

        # 检查更新按钮
        self.check_update_btn = QPushButton("立即检查更新")
        self.check_update_btn.clicked.connect(self.check_update)
        self.check_update_btn.setStyleSheet("background-color: #3498db; color: white; padding: 5px;")
        layout.addWidget(self.check_update_btn)

        # 添加弹性空间
        layout.addStretch()

        # 按钮
        button_layout = QHBoxLayout()

        self.save_btn = QPushButton("保存设置")
        self.save_btn.clicked.connect(self.save_settings)
        self.save_btn.setStyleSheet("background-color: #27ae60; color: white; padding: 8px;")

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        self.cancel_btn.setStyleSheet("padding: 8px;")

        button_layout.addWidget(self.save_btn)
        button_layout.addWidget(self.cancel_btn)

        layout.addLayout(button_layout)

    def load_settings(self):
        """加载设置"""
        self.auto_start_cb.setChecked(self.config.auto_start)
        self.interval_spin.setValue(self.config.check_interval)
        self.notify_cb.setChecked(self.config.notifications)
        self.ipv4_cb.setChecked(getattr(self.config, 'enable_ipv4', True))
        self.ipv6_cb.setChecked(getattr(self.config, 'enable_ipv6', True))
        self.timeout_spin.setValue(getattr(self.config, 'notification_timeout', 10))
        self.auto_update_cb.setChecked(getattr(self.config, 'auto_check_update', True))

        # 更新自启动状态显示
        self.update_auto_start_status()

    def update_auto_start_status(self):
        """更新自启动状态显示"""
        try:
            if hasattr(self.parent_window, 'check_autostart_status'):
                is_set = self.parent_window.check_autostart_status()
                if is_set:
                    self.auto_start_status.setText("状态: ✅ 已设置开机自启动")
                    self.auto_start_status.setStyleSheet("color: #27ae60; font-size: 10pt;")
                else:
                    if self.config.auto_start:
                        self.auto_start_status.setText("状态: ⚠️ 配置未生效，请重新保存设置")
                        self.auto_start_status.setStyleSheet("color: #f39c12; font-size: 10pt;")
                    else:
                        self.auto_start_status.setText("状态: ⭕ 未设置开机自启动")
                        self.auto_start_status.setStyleSheet("color: #666; font-size: 10pt;")
        except Exception as e:
            self.auto_start_status.setText(f"状态: ❌ 检测失败 ({str(e)})")
            self.auto_start_status.setStyleSheet("color: #e74c3c; font-size: 10pt;")

    def on_auto_start_changed(self):
        """当自启动设置改变时"""
        self.update_auto_start_status()

    def check_update(self):
        """检查更新"""
        if hasattr(self.parent_window, 'check_for_updates'):
            self.parent_window.check_for_updates(silent=False)

    def save_settings(self):
        """保存设置"""
        old_auto_start = self.config.auto_start
        new_auto_start = self.auto_start_cb.isChecked()

        # 更新配置
        self.config.auto_start = new_auto_start
        self.config.check_interval = self.interval_spin.value()
        self.config.notifications = self.notify_cb.isChecked()
        self.config.enable_ipv4 = self.ipv4_cb.isChecked()
        self.config.enable_ipv6 = self.ipv6_cb.isChecked()
        self.config.notification_timeout = self.timeout_spin.value()
        self.config.auto_check_update = self.auto_update_cb.isChecked()

        # 保存配置
        self.config.save_config()

        # 如果自启动设置发生变化，更新注册表
        if old_auto_start != new_auto_start:
            if hasattr(self.parent_window, 'set_autostart'):
                success = self.parent_window.set_autostart(new_auto_start)
                if success:
                    QMessageBox.information(self, "成功",
                                            f"开机自启动已{'启用' if new_auto_start else '禁用'}")
                else:
                    QMessageBox.warning(self, "提示",
                                        f"开机自启动设置{'失败' if new_auto_start else '已清除'}")

        self.accept()


class NotificationManager:
    """增强的通知管理器"""

    def __init__(self, app_name="IP Analyzer", parent=None):
        self.app_name = app_name
        self.parent = parent
        self.last_ip = None
        self.last_ip_url = None
        self.notification_methods = []

        # 初始化所有可用的通知方法
        self.init_notification_methods()

    def init_notification_methods(self):
        """初始化通知方法"""
        self.notification_methods = []

        # 方法1: 使用plyer (基础)
        try:
            self.notification_methods.append(("plyer", self.show_plyer_notification))
            print("✓ Plyer通知可用")
        except:
            print("✗ Plyer通知不可用")

        # 方法2: 使用win10toast (Windows 10+)
        if WIN10TOAST_AVAILABLE:
            try:
                self.toaster = win10toast.ToastNotifier()
                self.notification_methods.append(("win10toast", self.show_win10toast_notification))
                print("✓ Win10Toast通知可用")
            except Exception as e:
                print(f"✗ Win10Toast通知不可用: {e}")
                self.toaster = None
        else:
            print("✗ Win10Toast不可用（未安装）")

        # 方法3: 使用系统托盘消息
        try:
            if self.parent and hasattr(self.parent, 'tray_icon'):
                self.notification_methods.append(("tray", self.show_tray_notification))
                print("系统托盘通知可用")
        except:
            print("系统托盘通知不可用")

        # 方法4: 使用自定义窗口
        try:
            self.notification_methods.append(("custom", self.show_custom_notification))
            print("自定义通知可用")
        except:
            print("自定义通知不可用")

    def show_notification(self, title, message, ip=None, duration=10):
        """显示通知"""
        self.last_ip = ip
        if ip:
            self.last_ip_url = f"https://ipv4.ink/{ip}"

        if not self.notification_methods:
            print("没有可用的通知方法")
            return False

        # 尝试所有可用的通知方法
        for method_name, method_func in self.notification_methods:
            try:
                print(f"尝试使用 {method_name} 显示通知")
                if method_func(title, message, duration):
                    return True
            except Exception as e:
                print(f"{method_name} 通知失败: {str(e)}")
                continue

        print("所有通知方法都失败了")
        return False

    def show_plyer_notification(self, title, message, duration):
        """使用plyer显示通知"""
        try:
            notification.notify(
                title=title,
                message=message,
                app_name=self.app_name,
                timeout=duration,
                app_icon=None,
                toast=False
            )
            print("✓ Plyer通知发送成功")
            return True
        except Exception as e:
            print(f"Plyer通知失败: {e}")
            return False

    def show_win10toast_notification(self, title, message, duration):
        """使用win10toast显示通知"""
        try:
            self.toaster.show_toast(
                title=title,
                msg=message,
                duration=duration,
                icon_path=None,
                threaded=True,
                callback_on_click=self.on_notification_click
            )
            print("✓ Win10Toast通知发送成功")
            return True
        except Exception as e:
            print(f"Win10Toast通知失败: {e}")
            return False

    def show_tray_notification(self, title, message, duration):
        """使用系统托盘显示通知"""
        try:
            if self.parent and hasattr(self.parent, 'tray_icon'):
                self.parent.tray_icon.showMessage(
                    title,
                    message,
                    QSystemTrayIcon.MessageIcon.Information,
                    duration * 1000  # 转换为毫秒
                )
                print("系统托盘通知发送成功")
                return True
        except Exception as e:
            print(f"系统托盘通知失败: {e}")
        return False

    def show_custom_notification(self, title, message, duration):
        """显示自定义通知窗口（备选方案）"""
        try:
            # 在单独的线程中显示，避免阻塞主线程
            thread = threading.Thread(
                target=self._show_custom_notification_thread,
                args=(title, message, duration),
                daemon=True
            )
            thread.start()
            return True
        except Exception as e:
            print(f"自定义通知失败: {e}")
            return False

    def _show_custom_notification_thread(self, title, message, duration):
        """自定义通知线程"""
        try:
            # 创建一个简单的提示
            print(f"\n{'=' * 50}")
            print(f"通知: {title}")
            print(f"内容: {message}")
            print(f"{'=' * 50}\n")

            # 模拟通知显示时间
            time.sleep(min(duration, 5))
        except:
            pass

    def on_notification_click(self):
        """通知点击回调"""
        if self.last_ip_url:
            print(f"通知被点击，打开: {self.last_ip_url}")
            webbrowser.open(self.last_ip_url)


class IPAnalyzer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = Config()
        self.db_manager = DatabaseManager()
        self.notification_manager = NotificationManager(self.config.app_name, self)

        self.current_ip = None
        self.last_clipboard_content = ""
        self.api_connected = False

        self.setup_ui()
        self.setup_tray()
        self.start_api_checker()
        self.start_clipboard_monitor()

        # 根据配置设置自启动
        self.setup_autostart()

        # 检查更新（如果启用）
        if self.config.auto_check_update:
            QTimer.singleShot(3000, lambda: self.check_for_updates(silent=True))

    def setup_autostart(self):
        """根据配置设置开机自启动"""
        try:
            if self.config.auto_start:
                # 只有配置为True时才设置自启动
                success = self.set_autostart(True)
                if success:
                    self.add_log("已设置开机自启动", "success")
                else:
                    self.add_log("设置开机自启动失败", "warning")
            else:
                # 检查是否已设置，如果已设置则清除
                current_status = self.check_autostart_status()
                if current_status:
                    success = self.set_autostart(False)
                    if success:
                        self.add_log("已清除开机自启动", "info")

        except Exception as e:
            self.add_log(f"自启动设置错误: {str(e)}", "error")

    def set_autostart(self, enable: bool) -> bool:
        """设置开机自启动"""
        try:
            import winreg

            # 获取程序路径
            if getattr(sys, 'frozen', False):
                # 打包后的exe
                app_path = sys.executable
            else:
                # 开发环境中的python脚本
                app_path = sys.executable
                script_path = os.path.abspath(__file__)
                app_path = f'"{app_path}" "{script_path}"'

            # 处理路径中的空格（确保有引号）
            if ' ' in app_path and not app_path.startswith('"'):
                app_path = f'"{app_path}"'

            app_name = self.config.app_name

            key = winreg.HKEY_CURRENT_USER
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"

            try:
                # 尝试打开注册表键（需要64位访问权限）
                reg_key = winreg.OpenKey(key, key_path, 0,
                                         winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY)

                if enable:
                    # 添加开机启动项
                    winreg.SetValueEx(reg_key, app_name, 0, winreg.REG_SZ, app_path)
                    self.add_log(f"已添加开机自启动: {app_path}", "info")
                else:
                    # 删除开机启动项
                    try:
                        winreg.DeleteValue(reg_key, app_name)
                        self.add_log(f"已移除开机自启动", "info")
                    except FileNotFoundError:
                        # 启动项不存在
                        pass

                winreg.CloseKey(reg_key)

                # 更新配置
                self.config.auto_start = enable
                self.config.save_config()

                return True

            except PermissionError:
                self.add_log("权限不足，请以管理员身份运行程序", "error")
                return False
            except Exception as e:
                self.add_log(f"设置自启动失败: {str(e)}", "error")
                return False

        except Exception as e:
            self.add_log(f"自启动设置错误: {str(e)}", "error")
            return False

    def check_autostart_status(self) -> bool:
        """检查当前是否已设置开机自启动"""
        try:
            import winreg

            app_name = self.config.app_name
            key = winreg.HKEY_CURRENT_USER
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"

            try:
                # 打开注册表键
                reg_key = winreg.OpenKey(key, key_path, 0,
                                         winreg.KEY_READ | winreg.KEY_WOW64_64KEY)

                # 尝试读取值
                try:
                    value, _ = winreg.QueryValueEx(reg_key, app_name)
                    winreg.CloseKey(reg_key)

                    if value:
                        # 验证路径是否有效
                        current_path = value.strip('"')

                        # 获取当前程序路径
                        if getattr(sys, 'frozen', False):
                            expected_path = sys.executable
                        else:
                            expected_path = f'{sys.executable} "{os.path.abspath(__file__)}"'

                        expected_path = expected_path.strip('"')

                        # 比较路径（规范化路径进行比较）
                        if os.path.exists(current_path):
                            return True
                        else:
                            # 路径无效，可能需要更新
                            return False
                    return False

                except FileNotFoundError:
                    winreg.CloseKey(reg_key)
                    return False

            except Exception as e:
                print(f"检查自启动状态失败: {str(e)}")
                return False

        except Exception as e:
            print(f"检查自启动状态错误: {str(e)}")
            return False

    def setup_ui(self):
        """设置用户界面"""
        self.setWindowTitle(f"{self.config.app_name} v{self.config.app_version}")
        self.setFixedSize(600, 450)

        # 设置窗口图标
        self.setWindowIcon(self.create_app_icon())

        # 创建标签页
        self.tab_widget = QTabWidget()
        self.setCentralWidget(self.tab_widget)

        # 主页标签
        self.setup_main_tab()

        # 历史记录标签
        self.setup_history_tab()

        # 剪贴板历史记录标签
        self.setup_clipboard_history_tab()

    def setup_main_tab(self):
        """设置主页标签"""
        main_widget = QWidget()
        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # 标题
        title_label = QLabel(self.config.app_name)
        title_font = QFont("Microsoft YaHei", 18, QFont.Weight.Bold)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #2c3e50;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        # 分隔线
        line = QWidget()
        line.setFixedHeight(1)
        line.setStyleSheet("background-color: #ddd;")
        layout.addWidget(line)

        # API状态显示
        status_widget = QWidget()
        status_layout = QHBoxLayout(status_widget)
        status_layout.setContentsMargins(0, 0, 0, 0)

        status_label = QLabel("API状态:")
        status_label.setFont(QFont("Microsoft YaHei", 10))

        self.status_indicator = QLabel("●")
        self.status_indicator.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        self.status_indicator.setStyleSheet("color: #f39c12;")  # 橙色表示检测中

        self.api_status_label = QLabel("正在检测...")
        self.api_status_label.setFont(QFont("Microsoft YaHei", 10))

        status_layout.addWidget(status_label)
        status_layout.addWidget(self.status_indicator)
        status_layout.addWidget(self.api_status_label)
        status_layout.addStretch()
        layout.addWidget(status_widget)

        # 当前IP显示
        ip_widget = QWidget()
        ip_layout = QHBoxLayout(ip_widget)
        ip_layout.setContentsMargins(0, 0, 0, 0)

        ip_title = QLabel("当前IP:")
        ip_title.setFont(QFont("Microsoft YaHei", 10))

        self.current_ip_label = QLabel("无")
        self.current_ip_label.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        self.current_ip_label.setStyleSheet("color: #27ae60;")

        self.copy_ip_btn = QPushButton("复制")
        self.copy_ip_btn.clicked.connect(self.copy_current_ip)
        self.copy_ip_btn.setEnabled(False)
        self.copy_ip_btn.setStyleSheet("padding: 2px 8px; font-size: 11px;")

        self.view_ip_btn = QPushButton("查看")
        self.view_ip_btn.clicked.connect(self.view_current_ip)
        self.view_ip_btn.setEnabled(False)
        self.view_ip_btn.setStyleSheet("padding: 2px 8px; font-size: 11px;")

        ip_layout.addWidget(ip_title)
        ip_layout.addWidget(self.current_ip_label)
        ip_layout.addStretch()
        ip_layout.addWidget(self.copy_ip_btn)
        ip_layout.addWidget(self.view_ip_btn)
        layout.addWidget(ip_widget)

        # IP详情显示
        detail_widget = QWidget()
        detail_layout = QVBoxLayout(detail_widget)
        detail_layout.setContentsMargins(0, 10, 0, 0)

        detail_title = QLabel("IP详情:")
        detail_title.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        detail_layout.addWidget(detail_title)

        self.ip_detail_text = QTextEdit()
        self.ip_detail_text.setReadOnly(True)
        self.ip_detail_text.setFont(QFont("Microsoft YaHei", 9))
        self.ip_detail_text.setMaximumHeight(100)
        self.ip_detail_text.setStyleSheet("""
            QTextEdit {
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 5px;
                background-color: #f8f9fa;
            }
        """)
        detail_layout.addWidget(self.ip_detail_text)

        layout.addWidget(detail_widget)

        # 日志区域
        log_widget = QWidget()
        log_layout = QVBoxLayout(log_widget)
        log_layout.setContentsMargins(0, 10, 0, 0)

        log_title = QLabel("最近日志:")
        log_title.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        log_layout.addWidget(log_title)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        self.log_text.setMaximumHeight(120)
        self.log_text.setStyleSheet("""
            QTextEdit {
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 5px;
                background-color: #f8f9fa;
            }
        """)
        log_layout.addWidget(self.log_text)

        layout.addWidget(log_widget)

        # 按钮区域
        button_widget = QWidget()
        button_layout = QHBoxLayout(button_widget)
        button_layout.setContentsMargins(0, 10, 0, 0)

        self.settings_btn = QPushButton("设置")
        self.settings_btn.clicked.connect(self.show_settings)

        self.history_btn = QPushButton("历史记录")
        self.history_btn.clicked.connect(self.show_history_window)

        self.clipboard_history_btn = QPushButton("剪贴板记录")
        self.clipboard_history_btn.clicked.connect(self.show_clipboard_history_window)

        self.minimize_btn = QPushButton("最小化")
        self.minimize_btn.clicked.connect(self.minimize_to_tray)

        self.exit_btn = QPushButton("退出")
        self.exit_btn.clicked.connect(self.close_application)
        self.exit_btn.setStyleSheet("background-color: #e74c3c; color: white;")

        button_layout.addWidget(self.settings_btn)
        button_layout.addWidget(self.history_btn)
        button_layout.addWidget(self.clipboard_history_btn)
        button_layout.addWidget(self.minimize_btn)
        button_layout.addWidget(self.exit_btn)

        layout.addWidget(button_widget)

        self.tab_widget.addTab(main_widget, "主页")

    def setup_history_tab(self):
        """设置历史记录标签"""
        history_widget = QWidget()
        layout = QVBoxLayout(history_widget)

        # 控制按钮
        control_widget = QWidget()
        control_layout = QHBoxLayout(control_widget)

        self.refresh_history_btn = QPushButton("刷新")
        self.refresh_history_btn.clicked.connect(self.refresh_history)

        self.clear_history_btn = QPushButton("清空")
        self.clear_history_btn.clicked.connect(self.clear_all_history)
        self.clear_history_btn.setStyleSheet("background-color: #ff4444; color: white;")

        self.export_history_btn = QPushButton("导出")
        self.export_history_btn.clicked.connect(self.export_history)

        control_layout.addWidget(self.refresh_history_btn)
        control_layout.addWidget(self.clear_history_btn)
        control_layout.addWidget(self.export_history_btn)
        control_layout.addStretch()

        layout.addWidget(control_widget)

        # 历史记录表格
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(7)
        self.history_table.setHorizontalHeaderLabels([
            "时间", "IP地址", "类型", "国家", "省份", "城市", "运营商"
        ])

        # 设置表格属性
        header = self.history_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)

        self.history_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        # 启用右键菜单
        self.history_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.history_table.customContextMenuRequested.connect(self.show_history_context_menu)

        # 连接双击事件
        self.history_table.doubleClicked.connect(self.on_history_double_click)

        layout.addWidget(self.history_table)

        self.tab_widget.addTab(history_widget, "历史记录")

        # 加载历史记录
        self.refresh_history()

    def setup_clipboard_history_tab(self):
        """设置剪贴板历史记录标签"""
        clipboard_widget = QWidget()
        layout = QVBoxLayout(clipboard_widget)

        # 控制按钮
        control_widget = QWidget()
        control_layout = QHBoxLayout(control_widget)

        self.refresh_clipboard_btn = QPushButton("刷新")
        self.refresh_clipboard_btn.clicked.connect(self.refresh_clipboard_history)

        self.clear_clipboard_btn = QPushButton("清空")
        self.clear_clipboard_btn.clicked.connect(self.clear_all_clipboard_history)
        self.clear_clipboard_btn.setStyleSheet("background-color: #ff4444; color: white;")

        self.export_clipboard_btn = QPushButton("导出")
        self.export_clipboard_btn.clicked.connect(self.export_clipboard_history)

        control_layout.addWidget(self.refresh_clipboard_btn)
        control_layout.addWidget(self.clear_clipboard_btn)
        control_layout.addWidget(self.export_clipboard_btn)
        control_layout.addStretch()

        layout.addWidget(control_widget)

        # 剪贴板历史记录表格
        self.clipboard_table = QTableWidget()
        self.clipboard_table.setColumnCount(4)
        self.clipboard_table.setHorizontalHeaderLabels([
            "时间", "剪贴板内容", "包含IP", "操作"
        ])

        # 设置表格属性
        header = self.clipboard_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        self.clipboard_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.clipboard_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        # 启用右键菜单
        self.clipboard_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.clipboard_table.customContextMenuRequested.connect(self.show_clipboard_context_menu)

        # 连接双击事件
        self.clipboard_table.doubleClicked.connect(self.on_clipboard_double_click)

        layout.addWidget(self.clipboard_table)

        self.tab_widget.addTab(clipboard_widget, "剪贴板历史")

        # 加载剪贴板历史记录
        self.refresh_clipboard_history()

    def show_history_context_menu(self, position):
        """显示历史记录表格的右键菜单"""
        row = self.history_table.rowAt(position.y())
        if row >= 0:
            menu = QMenu()

            # 获取选中行的IP地址
            ip = self.history_table.item(row, 1).text()

            # 添加菜单项
            copy_action = QAction("复制IP地址", self)
            copy_action.triggered.connect(lambda: self.copy_ip_from_table(ip))

            view_action = QAction("查看详情", self)
            view_action.triggered.connect(lambda: self.view_ip_from_table(ip))

            delete_action = QAction("删除记录", self)
            delete_action.triggered.connect(lambda: self.delete_history_record(row))

            menu.addAction(copy_action)
            menu.addAction(view_action)
            menu.addAction(delete_action)

            menu.exec(self.history_table.viewport().mapToGlobal(position))

    def show_clipboard_context_menu(self, position):
        """显示剪贴板表格的右键菜单"""
        row = self.clipboard_table.rowAt(position.y())
        if row >= 0:
            menu = QMenu()

            # 获取选中行的内容
            content_item = self.clipboard_table.item(row, 1)
            content = content_item.toolTip() if content_item.toolTip() else content_item.text()

            # 添加菜单项
            copy_action = QAction("复制内容", self)
            copy_action.triggered.connect(lambda: self.copy_clipboard_content(content))

            view_action = QAction("查看详情", self)
            view_action.triggered.connect(lambda: self.view_clipboard_content(content))

            delete_action = QAction("删除记录", self)
            delete_action.triggered.connect(lambda: self.delete_clipboard_record(row))

            menu.addAction(copy_action)
            menu.addAction(view_action)
            menu.addAction(delete_action)

            menu.exec(self.clipboard_table.viewport().mapToGlobal(position))

    def on_history_double_click(self, index):
        """历史记录表格双击事件"""
        row = index.row()
        if row >= 0:
            # 获取该行所有数据
            time_str = self.history_table.item(row, 0).text()
            ip = self.history_table.item(row, 1).text()
            ip_type = self.history_table.item(row, 2).text()
            country = self.history_table.item(row, 3).text()
            province = self.history_table.item(row, 4).text()
            city = self.history_table.item(row, 5).text()
            isp = self.history_table.item(row, 6).text()

            # 构建详细内容
            details = f"查询时间: {time_str}\n"
            details += f"IP地址: {ip}\n"
            details += f"IP类型: {ip_type}\n"
            details += f"地理位置: {country} - {province} - {city}\n"
            details += f"网络运营商: {isp}\n"

            # 显示对话框
            dialog = DetailDialog(f"IP详情 - {ip}", details, self)
            dialog.exec()

    def on_clipboard_double_click(self, index):
        """剪贴板表格双击事件"""
        row = index.row()
        if row >= 0:
            # 获取该行所有数据
            time_str = self.clipboard_table.item(row, 0).text()
            content_item = self.clipboard_table.item(row, 1)
            content = content_item.toolTip() if content_item.toolTip() else content_item.text()
            contains_ip = self.clipboard_table.item(row, 2).text()

            # 构建详细内容
            details = f"记录时间: {time_str}\n"
            details += f"包含IP: {contains_ip}\n"
            details += f"内容长度: {len(content)} 字符\n"
            details += f"\n完整内容:\n{'-' * 40}\n{content}\n{'-' * 40}"

            # 显示对话框
            dialog = DetailDialog("剪贴板内容详情", details, self)
            dialog.exec()

    def copy_ip_from_table(self, ip):
        """从表格复制IP"""
        pyperclip.copy(ip)
        self.add_log(f"已复制IP地址: {ip}", "success")

    def view_ip_from_table(self, ip):
        """从表格查看IP"""
        webbrowser.open(f"https://ipv4.ink/{ip}")

    def delete_history_record(self, row):
        """删除历史记录"""
        ip = self.history_table.item(row, 1).text()
        time_str = self.history_table.item(row, 0).text()

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除IP地址为 {ip} 的记录吗？\n查询时间: {time_str}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            success = self.db_manager.delete_record_by_ip_and_time(ip, time_str)
            if success:
                self.refresh_history()
                self.add_log(f"已删除记录: {ip}", "success")
            else:
                self.add_log("删除记录失败", "error")

    def copy_clipboard_content(self, content):
        """复制剪贴板内容"""
        pyperclip.copy(content)
        self.add_log("已复制内容到剪贴板", "success")

    def view_clipboard_content(self, content):
        """查看剪贴板内容"""
        dialog = DetailDialog("剪贴板内容详情", content, self)
        dialog.exec()

    def delete_clipboard_record(self, row):
        """删除剪贴板记录"""
        time_str = self.clipboard_table.item(row, 0).text()
        content_preview = self.clipboard_table.item(row, 1).text()

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除这条记录吗？\n时间: {time_str}\n内容: {content_preview}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            success = self.db_manager.delete_clipboard_record_by_time(time_str)
            if success:
                self.refresh_clipboard_history()
                self.add_log("已删除剪贴板记录", "success")
            else:
                self.add_log("删除剪贴板记录失败", "error")

    def create_app_icon(self):
        """创建应用程序图标"""
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 绘制背景圆形
        gradient = QColor(66, 133, 244)
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(2, 2, 60, 60)

        # 绘制IP文字
        painter.setPen(QColor(255, 255, 255))
        font = painter.font()
        font.setPointSize(20)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "IP")

        painter.end()
        return QIcon(pixmap)

    def setup_tray(self):
        """设置系统托盘"""
        try:
            self.tray_icon = QSystemTrayIcon(self)
            icon = self.create_app_icon()
            self.tray_icon.setIcon(icon)

            # 创建托盘菜单
            tray_menu = QMenu()

            # 显示窗口
            show_action = QAction("显示主窗口", self)
            show_action.triggered.connect(self.show_window)
            tray_menu.addAction(show_action)

            # 查看历史
            history_action = QAction("查看历史记录", self)
            history_action.triggered.connect(self.show_history_window)
            tray_menu.addAction(history_action)

            # 查看剪贴板历史
            clipboard_history_action = QAction("查看剪贴板记录", self)
            clipboard_history_action.triggered.connect(self.show_clipboard_history_window)
            tray_menu.addAction(clipboard_history_action)

            tray_menu.addSeparator()

            # 手动检测
            check_action = QAction("手动检测剪贴板", self)
            check_action.triggered.connect(self.manual_check)
            tray_menu.addAction(check_action)

            # 测试API
            test_api_action = QAction("测试API连接", self)
            test_api_action.triggered.connect(self.test_api_connection)
            tray_menu.addAction(test_api_action)

            tray_menu.addSeparator()

            # 设置
            settings_action = QAction("设置", self)
            settings_action.triggered.connect(self.show_settings)
            tray_menu.addAction(settings_action)

            # 关于
            about_action = QAction("关于", self)
            about_action.triggered.connect(self.show_about)
            tray_menu.addAction(about_action)

            tray_menu.addSeparator()

            # 退出
            exit_action = QAction("退出", self)
            exit_action.triggered.connect(self.close_application)
            tray_menu.addAction(exit_action)

            self.tray_icon.setContextMenu(tray_menu)

            # 托盘图标提示
            self.tray_icon.setToolTip(f"{self.config.app_name}\nIP地理分析工具")

            # 显示托盘图标
            if not self.tray_icon.isVisible():
                self.tray_icon.show()

            # 连接点击事件
            self.tray_icon.activated.connect(self.on_tray_activated)

            self.add_log("系统托盘图标已初始化", "success")

        except Exception as e:
            self.add_log(f"设置系统托盘失败: {str(e)}", "error")

    def on_tray_activated(self, reason):
        """托盘图标点击事件"""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_window()
        elif reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_window()

    def start_api_checker(self):
        """启动API检查器"""
        self.api_checker = APIChecker()
        self.api_checker.status_updated.connect(self.update_api_status)
        self.api_checker.start()

    def update_api_status(self, status, message):
        """更新API状态"""
        self.api_connected = (status == "connected")
        self.config.api_status = status

        def update_ui():
            if status == "connected":
                self.status_indicator.setStyleSheet("color: #27ae60;")
                self.api_status_label.setStyleSheet("color: #27ae60;")
            else:
                self.status_indicator.setStyleSheet("color: #e74c3c;")
                self.api_status_label.setStyleSheet("color: #e74c3c;")

            self.api_status_label.setText(message)

            # 只记录状态变化的日志
            if hasattr(self, 'last_api_status') and self.last_api_status != status:
                self.add_log(f"API状态: {message}",
                             "success" if status == "connected" else "error")

            self.last_api_status = status

        QTimer.singleShot(0, update_ui)

    def start_clipboard_monitor(self):
        """启动剪贴板监控"""
        self.clipboard_timer = QTimer()
        self.clipboard_timer.timeout.connect(self.check_clipboard)
        self.clipboard_timer.start(int(self.config.check_interval * 1000))
        self.add_log(f"剪贴板监控已启动，间隔: {self.config.check_interval}秒", "info")

    def check_clipboard(self):
        """检查剪贴板内容"""
        try:
            clipboard_content = pyperclip.paste().strip()

            if not clipboard_content or clipboard_content == self.last_clipboard_content:
                return

            # 保存剪贴板历史
            contains_ip = len(self.extract_ips_from_text(clipboard_content)) > 0
            self.db_manager.add_clipboard_record(clipboard_content, contains_ip)

            # 如果剪贴板历史标签页是当前页，刷新显示
            if self.tab_widget.currentIndex() == 2:  # 剪贴板历史标签页
                self.refresh_clipboard_history()

            self.last_clipboard_content = clipboard_content

            # 从文本中提取IP地址
            ips_found = self.extract_ips_from_text(clipboard_content)

            if ips_found:
                for ip, ip_type in ips_found:
                    if ip != self.current_ip:
                        self.current_ip = ip
                        self.update_current_ip_display(ip)
                        self.add_log(f"检测到{ip_type.upper()}: {ip}", "info")

                        # 查询IP信息
                        threading.Thread(
                            target=self.query_ip_info,
                            args=(ip, ip_type),
                            daemon=True
                        ).start()
                        break
            else:
                self.update_current_ip_display(None)

        except Exception as e:
            self.add_log(f"剪贴板监控错误: {str(e)}", "error")

    def extract_ips_from_text(self, text: str) -> List[Tuple[str, str]]:
        """从文本中提取IP地址"""
        ips_found = []

        # IPv4正则表达式
        ipv4_pattern = r'\b(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.' \
                       r'(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.' \
                       r'(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.' \
                       r'(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'

        # IPv6正则表达式 - 修复版本
        # 匹配标准的IPv6地址格式，排除单独的 "::"
        ipv6_pattern = r'(?:(?:[A-Fa-f0-9]{1,4}:){7}[A-Fa-f0-9]{1,4}|' \
                       r'(?:[A-Fa-f0-9]{1,4}:){1,6}:(?:[A-Fa-f0-9]{1,4}:){0,5}[A-Fa-f0-9]{1,4}|' \
                       r'[A-Fa-f0-9]{1,4}::(?:[A-Fa-f0-9]{1,4}:){0,5}[A-Fa-f0-9]{1,4}|' \
                       r'::(?:[A-Fa-f0-9]{1,4}:){0,6}[A-Fa-f0-9]{1,4}|' \
                       r'(?:[A-Fa-f0-9]{1,4}:){1,7}:)'

        # 查找IPv4
        if self.config.enable_ipv4:
            ipv4_matches = re.finditer(ipv4_pattern, text)
            for match in ipv4_matches:
                ip = match.group()
                if self.is_valid_ipv4(ip):
                    ips_found.append((ip, "ipv4"))

        # 查找IPv6
        if self.config.enable_ipv6:
            ipv6_matches = re.finditer(ipv6_pattern, text, re.IGNORECASE)
            for match in ipv6_matches:
                ip = match.group()
                # 排除单独的 "::" 或 ":::" 等无效格式
                if self.is_valid_ipv6(ip):
                    ips_found.append((ip, "ipv6"))

        return ips_found

    def is_valid_ipv4(self, ip: str) -> bool:
        """验证IPv4地址有效性"""
        try:
            parts = ip.split('.')
            if len(parts) != 4:
                return False

            for part in parts:
                num = int(part)
                if num < 0 or num > 255:
                    return False
                if part.startswith('0') and len(part) > 1:
                    return False

            return True
        except:
            return False

    def is_valid_ipv6(self, ip: str) -> bool:
        """验证IPv6地址有效性"""
        try:
            # 排除单独的 "::" 或 ":::" 等无效格式
            if ip == "::" or ip == ":::":
                return False

            if ':::' in ip:
                return False

            if ip.count('::') > 1:
                return False

            # 分割成各个部分
            if '::' in ip:
                # 处理双冒号缩写
                parts = ip.split(':')
                if ip.startswith('::'):
                    parts = parts[1:]
                if ip.endswith('::'):
                    parts = parts[:-1]

                # 计算应有部分数量
                double_colon_parts = 8 - len([p for p in parts if p])

                # 确保总部分数不超过8
                if len([p for p in parts if p]) + double_colon_parts > 8:
                    return False
            else:
                # 标准格式
                parts = ip.split(':')
                if len(parts) != 8:
                    return False

            # 验证每个部分（如果有）
            for part in ip.split(':'):
                if part:
                    # 部分长度1-4个十六进制字符
                    if len(part) > 4:
                        return False

                    # 验证十六进制
                    try:
                        int(part, 16)
                    except ValueError:
                        return False

            return True
        except:
            return False

    def update_current_ip_display(self, ip: Optional[str]):
        """更新当前IP显示"""

        def update():
            if ip:
                self.current_ip_label.setText(ip)
                self.current_ip_label.setStyleSheet("color: #27ae60; font-weight: bold;")
                self.copy_ip_btn.setEnabled(True)
                self.view_ip_btn.setEnabled(True)
            else:
                self.current_ip_label.setText("无")
                self.current_ip_label.setStyleSheet("color: #666;")
                self.copy_ip_btn.setEnabled(False)
                self.view_ip_btn.setEnabled(False)
                self.ip_detail_text.clear()

        QTimer.singleShot(0, update)

    def copy_current_ip(self):
        """复制当前IP"""
        if self.current_ip:
            pyperclip.copy(self.current_ip)
            self.add_log(f"已复制IP: {self.current_ip}", "success")

    def view_current_ip(self):
        """查看当前IP详情"""
        if self.current_ip:
            webbrowser.open(f"https://ipv4.ink/{self.current_ip}")

    def query_ip_info(self, ip, ip_type):
        """查询IP信息"""
        try:
            if ip_type == "ipv4":
                url = f"{self.config.api_base_url}/ipv4?ip={ip}"
            else:
                url = f"{self.config.api_base_url}/ipv6?ip={ip}"

            response = requests.get(url, timeout=10)
            data = response.json()

            if response.status_code == 200:
                # 保存到历史记录
                self.save_to_history(ip, ip_type, data)
                # 显示通知和详情
                self.show_ip_details(ip, ip_type, data)
                self.add_log(f"IP查询成功: {ip}", "success")
            else:
                self.add_log(f"IP查询失败: {data.get('msg', '未知错误')}", "error")

        except Exception as e:
            self.add_log(f"IP查询错误: {str(e)}", "error")

    def save_to_history(self, ip: str, ip_type: str, data: dict):
        """保存到历史记录"""
        try:
            self.db_manager.add_record(ip, ip_type, data)
            # 如果历史记录标签页是当前页，刷新显示
            if self.tab_widget.currentIndex() == 1:  # 历史记录标签页
                self.refresh_history()
        except Exception as e:
            self.add_log(f"保存历史记录失败: {str(e)}", "error")

    def show_ip_details(self, ip: str, ip_type: str, data: dict):
        """显示IP详情"""
        try:
            # 解析数据
            if ip_type == "ipv4":
                if data.get('data'):
                    detail = data['data']
                    location = f"{detail.get('country_name', '未知')} - " \
                               f"{detail.get('province_name', '未知')} - " \
                               f"{detail.get('city_name', '未知')}"
                    isp = detail.get('isp', '未知')
                    coordinates = f"经纬度: {detail.get('latitude', '未知')}, " \
                                  f"{detail.get('longitude', '未知')}"
                    query_time = data.get('query_time_ms', '未知')
                else:
                    location = isp = coordinates = "数据解析失败"
                    query_time = "未知"
            else:
                if data.get('data'):
                    detail = data['data']
                    location = f"{detail.get('country', '未知')} - " \
                               f"{detail.get('province', '未知')} - " \
                               f"{detail.get('city', '未知')}"
                    isp = detail.get('isp', '未知')
                    coordinates = f"经纬度: {detail.get('latitude', '未知')}, " \
                                  f"{detail.get('longitude', '未知')}"
                    query_time = data.get('query_time_ms', '未知')
                else:
                    location = isp = coordinates = "数据解析失败"
                    query_time = "未知"

            # 更新详情显示
            detail_text = f"IP地址: {ip}\n"
            detail_text += f"地理位置: {location}\n"
            detail_text += f"网络运营商: {isp}\n"
            if coordinates and "未知" not in coordinates:
                detail_text += f"{coordinates}\n"
            detail_text += f"查询耗时: {query_time}ms\n"
            detail_text += f"查询时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

            def update_detail():
                self.ip_detail_text.setPlainText(detail_text)

            QTimer.singleShot(0, update_detail)

            # 显示通知
            if self.config.notifications:
                message = f"IP: {ip}\n位置: {location}\n运营商: {isp}"
                if coordinates and "未知" not in coordinates:
                    message += f"\n{coordinates}"

                self.notification_manager.show_notification(
                    title=f"IP地址检测 - {ip}",
                    message=message,
                    ip=ip,
                    duration=self.config.notification_timeout
                )

        except Exception as e:
            self.add_log(f"显示IP详情错误: {str(e)}", "error")

    def add_log(self, message: str, log_type: str = "info"):
        """添加日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")

        colors = {
            "info": "#3498db",
            "success": "#27ae60",
            "warning": "#f39c12",
            "error": "#e74c3c",
        }

        color = colors.get(log_type, "#3498db")
        log_message = f'[{timestamp}] {message}'

        def update_log():
            self.log_text.append(log_message)
            scrollbar = self.log_text.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

        QTimer.singleShot(0, update_log)

    def show_settings(self):
        """显示设置窗口"""
        settings_window = SettingsWindow(self.config, self)
        if settings_window.exec():
            self.add_log("设置已保存", "success")
            # 重启剪贴板监控
            self.clipboard_timer.stop()
            self.start_clipboard_monitor()

    def show_history_window(self):
        """显示历史记录窗口"""
        history_window = HistoryWindow(self.db_manager, self)
        history_window.exec()

    def show_clipboard_history_window(self):
        """显示剪贴板历史记录窗口"""
        clipboard_window = ClipboardHistoryWindow(self.db_manager, self)
        clipboard_window.exec()

    def refresh_history(self):
        """刷新历史记录"""
        try:
            history = self.db_manager.get_history()
            self.history_table.setRowCount(len(history))

            for row, record in enumerate(history):
                # 时间
                self.history_table.setItem(row, 0, QTableWidgetItem(record[1]))
                # IP地址
                self.history_table.setItem(row, 1, QTableWidgetItem(record[2]))
                # IP类型
                self.history_table.setItem(row, 2, QTableWidgetItem(record[3]))
                # 国家
                self.history_table.setItem(row, 3, QTableWidgetItem(record[4] if record[4] else "未知"))
                # 省份
                self.history_table.setItem(row, 4, QTableWidgetItem(record[5] if record[5] else "未知"))
                # 城市
                self.history_table.setItem(row, 5, QTableWidgetItem(record[6] if record[6] else "未知"))
                # 运营商
                self.history_table.setItem(row, 6, QTableWidgetItem(record[7] if record[7] else "未知"))

            self.add_log(f"历史记录已刷新，共 {len(history)} 条记录", "success")
        except Exception as e:
            self.add_log(f"刷新历史记录失败: {str(e)}", "error")

    def refresh_clipboard_history(self):
        """刷新剪贴板历史记录"""
        try:
            history = self.db_manager.get_clipboard_history()
            self.clipboard_table.setRowCount(len(history))

            for row, record in enumerate(history):
                # 时间
                self.clipboard_table.setItem(row, 0, QTableWidgetItem(record[1]))

                # 剪贴板内容
                content = record[2]
                # 截断长内容
                if len(content) > 100:
                    display_content = content[:100] + "..."
                else:
                    display_content = content
                content_item = QTableWidgetItem(display_content)
                content_item.setToolTip(content)  # 鼠标悬停显示完整内容
                self.clipboard_table.setItem(row, 1, content_item)

                # 包含IP
                contains_ip = record[3]
                ip_item = QTableWidgetItem("是" if contains_ip else "否")
                self.clipboard_table.setItem(row, 2, ip_item)

                # 操作按钮
                btn_widget = QWidget()
                btn_layout = QHBoxLayout(btn_widget)
                btn_layout.setContentsMargins(0, 0, 0, 0)

                copy_btn = QPushButton("复制")
                copy_btn.clicked.connect(lambda checked, content=content: self.copy_clipboard_content(content))
                copy_btn.setStyleSheet("padding: 2px 5px; font-size: 12px;")

                view_btn = QPushButton("查看")
                view_btn.clicked.connect(lambda checked, content=content: self.view_clipboard_content(content))
                view_btn.setStyleSheet("padding: 2px 5px; font-size: 12px;")

                btn_layout.addWidget(view_btn)
                btn_layout.addWidget(copy_btn)
                self.clipboard_table.setCellWidget(row, 3, btn_widget)

            self.add_log(f"剪贴板历史记录已刷新，共 {len(history)} 条记录", "success")
        except Exception as e:
            self.add_log(f"刷新剪贴板历史记录失败: {str(e)}", "error")

    def clear_all_history(self):
        """清空所有历史记录"""
        reply = QMessageBox.question(
            self, "确认清空",
            "确定要清空所有历史记录吗？此操作不可恢复！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                success = self.db_manager.clear_history()
                if success:
                    self.refresh_history()
                    QMessageBox.information(self, "成功", "历史记录已清空")
                    self.add_log("历史记录已清空", "success")
                else:
                    QMessageBox.critical(self, "错误", "清空历史记录失败")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"清空失败: {str(e)}")

    def clear_all_clipboard_history(self):
        """清空所有剪贴板历史记录"""
        reply = QMessageBox.question(
            self, "确认清空",
            "确定要清空所有剪贴板历史记录吗？此操作不可恢复！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                success = self.db_manager.clear_clipboard_history()
                if success:
                    self.refresh_clipboard_history()
                    QMessageBox.information(self, "成功", "剪贴板历史记录已清空")
                    self.add_log("剪贴板历史记录已清空", "success")
                else:
                    QMessageBox.critical(self, "错误", "清空剪贴板历史记录失败")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"清空失败: {str(e)}")

    def export_history(self):
        """导出历史记录"""
        try:
            # 使用文件对话框选择保存位置
            default_filename = f"ip_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "导出历史记录",
                default_filename,
                "JSON文件 (*.json);;CSV文件 (*.csv);;所有文件 (*.*)"
            )

            if not file_path:
                return  # 用户取消

            history = self.db_manager.get_history(limit=1000)

            if file_path.endswith('.csv'):
                # 导出为CSV
                import csv
                with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    writer.writerow(['时间', 'IP地址', '类型', '国家', '省份', '城市', '运营商', '查询耗时(ms)'])

                    for record in history:
                        writer.writerow([
                            record[1],  # 时间
                            record[2],  # IP地址
                            record[3],  # 类型
                            record[4] if record[4] else "未知",  # 国家
                            record[5] if record[5] else "未知",  # 省份
                            record[6] if record[6] else "未知",  # 城市
                            record[7] if record[7] else "未知",  # 运营商
                            record[8] if record[8] else ""  # 查询耗时
                        ])
            else:
                # 导出为JSON
                export_data = []

                for record in history:
                    export_data.append({
                        "time": record[1],
                        "ip": record[2],
                        "type": record[3],
                        "country": record[4],
                        "province": record[5],
                        "city": record[6],
                        "isp": record[7],
                        "query_time": record[8]
                    })

                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(export_data, f, indent=2, ensure_ascii=False)

            QMessageBox.information(self, "导出成功", f"历史记录已导出到:\n{file_path}")
            self.add_log(f"历史记录已导出到: {file_path}", "success")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出失败: {str(e)}")
            self.add_log(f"导出失败: {str(e)}", "error")

    def export_clipboard_history(self):
        """导出剪贴板历史记录"""
        try:
            # 使用文件对话框选择保存位置
            default_filename = f"clipboard_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "导出剪贴板历史记录",
                default_filename,
                "JSON文件 (*.json);;CSV文件 (*.csv);;所有文件 (*.*)"
            )

            if not file_path:
                return  # 用户取消

            history = self.db_manager.get_clipboard_history(limit=1000)

            if file_path.endswith('.csv'):
                # 导出为CSV
                import csv
                with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    writer.writerow(['时间', '内容', '包含IP'])

                    for record in history:
                        writer.writerow([
                            record[1],  # 时间
                            record[2],  # 内容
                            "是" if record[3] else "否"  # 包含IP
                        ])
            else:
                # 导出为JSON
                export_data = []

                for record in history:
                    export_data.append({
                        "time": record[1],
                        "content": record[2],
                        "contains_ip": bool(record[3])
                    })

                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(export_data, f, indent=2, ensure_ascii=False)

            QMessageBox.information(self, "导出成功", f"剪贴板历史记录已导出到:\n{file_path}")
            self.add_log(f"剪贴板历史记录已导出到: {file_path}", "success")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出失败: {str(e)}")
            self.add_log(f"导出失败: {str(e)}", "error")

    # 添加检查更新方法到 IPAnalyzer 类
    def check_for_updates(self, silent=False):
        """检查更新"""
        try:
            if not silent:
                self.add_log("正在检查更新...", "info")

            # 标记是否为静默检查
            if silent:
                self._update_silent = True

            self.update_checker = UpdateChecker(self.config)
            self.update_checker.update_available.connect(self.on_update_available)
            self.update_checker.check_completed.connect(self.on_update_check_completed)
            self.update_checker.start()

        except Exception as e:
            if not silent:
                self.add_log(f"检查更新失败: {str(e)}", "error")
            print(f"启动更新检查失败: {e}")

    def on_update_available(self, update_info):
        """发现新版本"""
        try:
            # 确保在主线程中执行UI操作
            def show_update_dialog():
                try:
                    remote_version = update_info.get('version', '未知')
                    download_url = update_info.get('download_url', '')
                    changelog = update_info.get('changelog', '暂无更新说明')

                    # 记录最后检查时间
                    self.config.last_update_check = datetime.now().isoformat()
                    self.config.save_config()

                    # 显示更新对话框
                    message = f"发现新版本: v{remote_version}\n\n"
                    message += f"当前版本: v{self.config.app_version}\n\n"
                    message += f"更新内容:\n{changelog}\n\n"
                    message += "是否立即访问下载页面？"

                    reply = QMessageBox.information(
                        self,
                        "发现新版本",
                        message,
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.Yes
                    )

                    if reply == QMessageBox.StandardButton.Yes and download_url:
                        webbrowser.open(download_url)

                except Exception as e:
                    print(f"显示更新对话框错误: {e}")
                    # 显示简单的错误消息
                    QMessageBox.warning(self, "错误", f"显示更新信息时出错: {str(e)}")

            # 使用QTimer确保在主线程中执行
            QTimer.singleShot(0, show_update_dialog)

        except Exception as e:
            self.add_log(f"处理更新信息错误: {str(e)}", "error")

    def on_update_check_completed(self, has_update, message):
        """更新检查完成"""

        def update_completed():
            if not has_update:
                # 如果不是静默检查，显示消息
                if not hasattr(self, '_update_silent') or not self._update_silent:
                    self.add_log(message, "info")

            # 清理静默标记
            if hasattr(self, '_update_silent'):
                delattr(self, '_update_silent')

        QTimer.singleShot(0, update_completed)

    def manual_check(self):
        """手动检测剪贴板"""
        self.add_log("手动检测剪贴板...", "info")
        self.check_clipboard()

    def test_api_connection(self):
        """测试API连接"""
        self.add_log("测试API连接...", "info")
        self.api_checker.status_updated.emit("checking", "正在测试连接...")

        def test():
            try:
                response = requests.get(f"{self.config.api_base_url}/", timeout=5)
                if response.status_code == 200:
                    self.api_checker.status_updated.emit("connected", "API连接正常")
                else:
                    self.api_checker.status_updated.emit("disconnected", f"API响应异常: {response.status_code}")
            except Exception as e:
                self.api_checker.status_updated.emit("disconnected", f"连接错误: {str(e)}")

        threading.Thread(target=test, daemon=True).start()

    def show_about(self):
        """显示关于对话框"""
        about_text = f"""
        {self.config.app_name} v{self.config.app_version}

        IP地址分析工具

        功能特点:
        • 自动监控剪贴板中的IP地址
        • 支持IPv4和IPv6地址检测
        • 查询IP地理位置和运营商信息
        • 桌面通知提醒
        • 历史记录保存
        • 开机自启动
        • 自动更新检测

        技术支持: https://ipv4.ink
        开源地址：https://github.com/xiaroustar/IPanalyzer
        QQ交流群：721926462
        联系微信：wordsafe

        © 2025-2026 Mingxin IP Analyzer
        """

        # 修复：移除重复的QMessageBox调用
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("关于")
        msg_box.setText(about_text)

        # 添加自定义按钮
        check_update_btn = msg_box.addButton("检查更新", QMessageBox.ButtonRole.ActionRole)
        close_btn = msg_box.addButton("关闭", QMessageBox.ButtonRole.RejectRole)

        # 显示消息框并等待响应
        msg_box.exec()

        # 检查哪个按钮被点击
        clicked_button = msg_box.clickedButton()
        if clicked_button == check_update_btn:
            self.check_for_updates(silent=False)

    def show_window(self):
        """显示主窗口"""
        self.show()
        self.raise_()
        self.activateWindow()

    def minimize_to_tray(self):
        """最小化到托盘"""
        self.hide()
        self.add_log("已最小化到系统托盘", "info")

    def close_application(self):
        """关闭应用程序"""
        self.add_log("正在退出程序...", "info")
        self.config.save_config()

        if hasattr(self, 'api_checker'):
            self.api_checker.stop()
            self.api_checker.wait()

        if hasattr(self, 'tray_icon'):
            self.tray_icon.hide()

        QApplication.quit()

    def closeEvent(self, event):
        """关闭事件"""
        event.ignore()
        self.minimize_to_tray()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Mingxin")
    app.setApplicationDisplayName("ipv4.ink")
    app.setQuitOnLastWindowClosed(False)

    window = IPAnalyzer()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()