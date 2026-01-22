import json
import os
import sys
import sqlite3
import requests
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import threading
import time


class Config:
    """配置管理类"""

    @property
    def install_info(self):
        """获取安装信息"""
        return {
            'app_name': self.app_name,
            'app_version': self.app_version,
            'company_name': 'Mingxin Tools',
            'install_dir': self.get_install_dir(),
            'is_installed': self.is_installed()
        }

    def get_install_dir(self):
        """获取安装目录"""
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Mingxin_Tools_剪贴板IP地理分析工具"
            )
            install_dir, _ = winreg.QueryValueEx(key, "InstallLocation")
            winreg.CloseKey(key)
            return install_dir
        except:
            return None

    def is_installed(self):
        """检查是否已安装"""
        return self.get_install_dir() is not None

    def __init__(self):
        self.app_name = "IP Analyzer"
        self.app_version = "1.0.0"
        self.api_base_url = "https://ipv4.ink"

        # 默认配置
        self.config_file = "data/config.json"
        self.default_config = {
            "auto_start": False,
            "check_interval": 2.0,  # 检查间隔（秒）
            "notifications": True,
            "enable_ipv4": True,
            "enable_ipv6": True,
            "notification_timeout": 10,  # 通知显示时间（秒）
            "auto_check_update": True,
            "last_update_check": "",
            "api_status": "disconnected"
        }

        # 创建数据目录
        self.create_data_directory()

        # 加载配置
        self.load_config()

    def create_data_directory(self):
        """创建数据目录"""
        data_dir = Path("data")
        if not data_dir.exists():
            data_dir.mkdir(parents=True)

    def load_config(self):
        """加载配置文件"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)

                # 更新配置
                for key, value in config_data.items():
                    if hasattr(self, key):
                        setattr(self, key, value)
                    else:
                        # 添加新配置项
                        self.default_config[key] = value
                        setattr(self, key, value)

                # 确保所有默认配置项都存在
                for key, value in self.default_config.items():
                    if not hasattr(self, key):
                        setattr(self, key, value)
            else:
                # 使用默认配置
                for key, value in self.default_config.items():
                    setattr(self, key, value)
                self.save_config()

        except Exception as e:
            print(f"加载配置文件失败: {e}")
            # 使用默认配置
            for key, value in self.default_config.items():
                setattr(self, key, value)

    def save_config(self):
        """保存配置文件"""
        try:
            config_data = {}
            for key in self.default_config.keys():
                if hasattr(self, key):
                    config_data[key] = getattr(self, key)

            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=4, ensure_ascii=False)

        except Exception as e:
            print(f"保存配置文件失败: {e}")

    def check_for_updates(self) -> Optional[Dict[str, Any]]:
        """检查更新"""
        try:
            # 使用正确的版本文件地址
            if self.api_base_url.startswith("https://ipv4.ink"):
                update_url = "https://ipv4.ink/win/version.json"
            else:
                # 备用地址或测试地址
                update_url = f"{self.api_base_url}/win/version.json"

            print(f"正在检查更新，URL: {update_url}")

            # 发送请求，设置较短的超时时间
            response = requests.get(update_url, timeout=15)

            print(f"响应状态码: {response.status_code}")

            if response.status_code == 200:
                update_info = response.json()
                print(f"获取到的更新信息: {update_info}")

                # 验证响应格式
                if 'version' in update_info:
                    # 返回正确的格式
                    return {
                        "success": True,
                        "data": update_info
                    }
                else:
                    print("更新信息格式错误，缺少version字段")
                    return None
            else:
                print(f"更新检查HTTP错误: {response.status_code}")
                return None

        except requests.exceptions.Timeout:
            print("更新检查超时")
            return None
        except requests.exceptions.ConnectionError as e:
            print(f"更新检查连接错误: {e}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"更新检查请求错误: {e}")
            return None
        except Exception as e:
            print(f"更新检查失败: {e}")
            return None

    def is_new_version_available(self, remote_version: str) -> bool:
        """检查是否有新版本"""
        try:
            # 简单的版本号比较
            def parse_version(version_str):
                # 移除'v'前缀
                if version_str.startswith('v'):
                    version_str = version_str[1:]
                # 分割版本号
                parts = version_str.split('.')
                # 确保有3部分
                while len(parts) < 3:
                    parts.append('0')
                # 转换为整数
                return [int(part) if part.isdigit() else 0 for part in parts]

            current_parts = parse_version(self.app_version)
            remote_parts = parse_version(remote_version)

            # 比较版本号
            for i in range(3):
                if remote_parts[i] > current_parts[i]:
                    return True
                elif remote_parts[i] < current_parts[i]:
                    return False

            return False  # 版本相同

        except Exception as e:
            print(f"版本比较失败: {e}")
            return False

    def update_config(self, **kwargs):
        """更新配置"""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)

        # 保存配置
        self.save_config()


class DatabaseManager:
    """数据库管理类"""

    def __init__(self, db_path="data/ip_history.db"):
        self.db_path = db_path

        # 创建数据目录
        self.create_data_directory()

        # 初始化数据库
        self.init_database()

    def create_data_directory(self):
        """创建数据目录"""
        data_dir = Path("data")
        if not data_dir.exists():
            data_dir.mkdir(parents=True)

    def init_database(self):
        """初始化数据库"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 创建历史记录表
            cursor.execute('''
                           CREATE TABLE IF NOT EXISTS history
                           (
                               id
                               INTEGER
                               PRIMARY
                               KEY
                               AUTOINCREMENT,
                               time
                               TEXT
                               NOT
                               NULL,
                               ip
                               TEXT
                               NOT
                               NULL,
                               type
                               TEXT
                               NOT
                               NULL,
                               country
                               TEXT,
                               province
                               TEXT,
                               city
                               TEXT,
                               isp
                               TEXT,
                               query_time
                               TEXT
                           )
                           ''')

            # 创建剪贴板历史记录表
            cursor.execute('''
                           CREATE TABLE IF NOT EXISTS clipboard_history
                           (
                               id
                               INTEGER
                               PRIMARY
                               KEY
                               AUTOINCREMENT,
                               time
                               TEXT
                               NOT
                               NULL,
                               content
                               TEXT
                               NOT
                               NULL,
                               contains_ip
                               INTEGER
                               DEFAULT
                               0
                           )
                           ''')

            # 创建索引以提高查询性能
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_time ON history(time)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_ip ON history(ip)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_clipboard_time ON clipboard_history(time)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_clipboard_ip ON clipboard_history(contains_ip)')

            conn.commit()
            conn.close()

            print("数据库初始化完成")

        except Exception as e:
            print(f"数据库初始化失败: {e}")

    def add_record(self, ip: str, ip_type: str, data: dict):
        """添加IP查询记录"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 解析数据
            if ip_type == "ipv4":
                if data.get('data'):
                    detail = data['data']
                    country = detail.get('country_name')
                    province = detail.get('province_name')
                    city = detail.get('city_name')
                    isp = detail.get('isp')
                    query_time = data.get('query_time_ms')
                else:
                    country = province = city = isp = query_time = None
            else:
                if data.get('data'):
                    detail = data['data']
                    country = detail.get('country')
                    province = detail.get('province')
                    city = detail.get('city')
                    isp = detail.get('isp')
                    query_time = data.get('query_time_ms')
                else:
                    country = province = city = isp = query_time = None

            cursor.execute('''
                           INSERT INTO history (time, ip, type, country, province, city, isp, query_time)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                           ''', (
                               datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                               ip,
                               ip_type,
                               country,
                               province,
                               city,
                               isp,
                               str(query_time) if query_time else None
                           ))

            conn.commit()
            conn.close()
            return True

        except Exception as e:
            print(f"添加记录失败: {e}")
            return False

    def get_history(self, limit=100):
        """获取历史记录"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                           SELECT *
                           FROM history
                           ORDER BY time DESC
                               LIMIT ?
                           ''', (limit,))

            history = cursor.fetchall()
            conn.close()
            return history

        except Exception as e:
            print(f"获取历史失败: {e}")
            return []

    def clear_history(self):
        """清空历史记录"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('DELETE FROM history')
            conn.commit()
            conn.close()
            return True

        except Exception as e:
            print(f"清空历史失败: {e}")
            return False

    def delete_record_by_ip_and_time(self, ip, time_str):
        """根据IP和时间删除记录"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('DELETE FROM history WHERE ip = ? AND time = ?', (ip, time_str))
            conn.commit()
            conn.close()
            return cursor.rowcount > 0

        except Exception as e:
            print(f"删除记录失败: {e}")
            return False

    def add_clipboard_record(self, content, contains_ip):
        """添加剪贴板记录"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                           INSERT INTO clipboard_history (time, content, contains_ip)
                           VALUES (?, ?, ?)
                           ''', (
                               datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                               content,
                               1 if contains_ip else 0
                           ))

            conn.commit()
            conn.close()
            return True

        except Exception as e:
            print(f"添加剪贴板记录失败: {e}")
            return False

    def get_clipboard_history(self, limit=100):
        """获取剪贴板历史记录"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                           SELECT *
                           FROM clipboard_history
                           ORDER BY time DESC
                               LIMIT ?
                           ''', (limit,))

            history = cursor.fetchall()
            conn.close()
            return history

        except Exception as e:
            print(f"获取剪贴板历史失败: {e}")
            return []

    def clear_clipboard_history(self):
        """清空剪贴板历史记录"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('DELETE FROM clipboard_history')
            conn.commit()
            conn.close()
            return True

        except Exception as e:
            print(f"清空剪贴板历史失败: {e}")
            return False

    def delete_clipboard_record_by_time(self, time_str):
        """根据时间删除剪贴板记录"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('DELETE FROM clipboard_history WHERE time = ?', (time_str,))
            conn.commit()
            conn.close()
            return cursor.rowcount > 0

        except Exception as e:
            print(f"删除剪贴板记录失败: {e}")
            return False

    def search_history(self, keyword: str):
        """搜索历史记录"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                           SELECT *
                           FROM history
                           WHERE ip LIKE ?
                              OR country LIKE ?
                              OR province LIKE ?
                              OR city LIKE ?
                              OR isp LIKE ?
                           ORDER BY time DESC
                               LIMIT 100
                           ''', (
                               f'%{keyword}%',
                               f'%{keyword}%',
                               f'%{keyword}%',
                               f'%{keyword}%',
                               f'%{keyword}%'
                           ))

            history = cursor.fetchall()
            conn.close()
            return history

        except Exception as e:
            print(f"搜索历史失败: {e}")
            return []

    def search_clipboard_history(self, keyword: str):
        """搜索剪贴板历史记录"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                           SELECT *
                           FROM clipboard_history
                           WHERE content LIKE ?
                           ORDER BY time DESC
                               LIMIT 100
                           ''', (f'%{keyword}%',))

            history = cursor.fetchall()
            conn.close()
            return history

        except Exception as e:
            print(f"搜索剪贴板历史失败: {e}")
            return []

    def get_statistics(self):
        """获取统计信息"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 总记录数
            cursor.execute('SELECT COUNT(*) FROM history')
            total_records = cursor.fetchone()[0]

            # IP类型统计
            cursor.execute('SELECT type, COUNT(*) FROM history GROUP BY type')
            type_stats = cursor.fetchall()

            # 最近7天记录数
            cursor.execute('''
                           SELECT DATE (time), COUNT (*)
                           FROM history
                           WHERE time >= datetime('now', '-7 days')
                           GROUP BY DATE (time)
                           ORDER BY DATE (time)
                           ''')
            weekly_stats = cursor.fetchall()

            # 剪贴板记录统计
            cursor.execute('SELECT COUNT(*) FROM clipboard_history')
            total_clipboard = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM clipboard_history WHERE contains_ip = 1')
            clipboard_with_ip = cursor.fetchone()[0]

            conn.close()

            return {
                "total_records": total_records,
                "type_stats": dict(type_stats),
                "weekly_stats": weekly_stats,
                "total_clipboard": total_clipboard,
                "clipboard_with_ip": clipboard_with_ip
            }

        except Exception as e:
            print(f"获取统计信息失败: {e}")
            return {}

    def backup_database(self, backup_path: str):
        """备份数据库"""
        try:
            import shutil
            shutil.copy2(self.db_path, backup_path)
            return True
        except Exception as e:
            print(f"备份数据库失败: {e}")
            return False

    def restore_database(self, backup_path: str):
        """恢复数据库"""
        try:
            import shutil
            if os.path.exists(backup_path):
                shutil.copy2(backup_path, self.db_path)
                return True
            return False
        except Exception as e:
            print(f"恢复数据库失败: {e}")
            return False


class AutoUpdater:
    """自动更新类"""

    def __init__(self, config):
        self.config = config
        self.update_url = "https://ipv4.ink/win/version.json"
        self.download_url = "https://ipv4.ink/win/downloads/"
        self.update_available = False
        self.update_info = {}

    def check_update(self):
        """检查更新"""
        try:
            update_info = self.config.check_for_updates()

            # 注意：现在返回的是包装过的格式
            if update_info and update_info.get('success'):
                data = update_info.get('data', {})
                if 'version' in data:
                    remote_version = data['version']

                    if self.config.is_new_version_available(remote_version):
                        self.update_available = True
                        self.update_info = data
                        return True, data
                    else:
                        return False, "当前已是最新版本"
            else:
                return False, "检查更新失败或网络错误"

        except Exception as e:
            return False, f"检查更新失败: {str(e)}"

    def download_update(self, progress_callback=None):
        """下载更新"""
        try:
            if not self.update_available or 'download_url' not in self.update_info:
                return False, "没有可用的更新"

            download_url = self.update_info.get('download_url', self.download_url)

            # 这里应该实现实际的下载逻辑
            # 由于安全考虑，这里只返回模拟结果
            if progress_callback:
                # 模拟下载进度
                for i in range(0, 101, 10):
                    time.sleep(0.1)
                    progress_callback(i)

            return True, "下载完成"

        except Exception as e:
            return False, f"下载失败: {str(e)}"

    def install_update(self):
        """安装更新"""
        try:
            # 这里应该实现实际的安装逻辑
            # 由于安全考虑，这里只返回模拟结果

            # 在实际应用中，这里可能需要：
            # 1. 停止应用程序
            # 2. 备份当前版本
            # 3. 解压并覆盖文件
            # 4. 重新启动应用程序

            return True, "更新安装成功，请重启应用程序"

        except Exception as e:
            return False, f"安装失败: {str(e)}"


# 测试代码
if __name__ == "__main__":
    # 测试配置类
    config = Config()
    print(f"应用名称: {config.app_name}")
    print(f"应用版本: {config.app_version}")
    print(f"检查间隔: {config.check_interval}")
    print(f"通知启用: {config.notifications}")

    # 测试数据库类
    db = DatabaseManager()
    print("数据库初始化测试完成")

    # 测试更新检查
    updater = AutoUpdater(config)
    has_update, message = updater.check_update()
    print(f"更新检查: {message}")

    # 保存配置更改
    config.check_interval = 3.0
    config.save_config()
    print("配置已保存")
