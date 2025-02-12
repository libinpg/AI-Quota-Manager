import unittest
import os
import json
import tempfile
import tkinter as tk
import datetime
from threading import Timer
from unittest.mock import patch, MagicMock

# 假设你的主程序代码已经保存为模块，比如 ai_quota_manager.py
# 如果是在同一文件中，也可以直接引用下面这些名字
from ai_quota_manager import (
    load_config,
    save_config,
    AIPlatform,
    send_windows_notification,
    schedule_reset,
    Application,
    CONFIG_FILE,
    DEFAULT_CONFIG
)

# 用于测试的 Timer 类——立即执行，不等待延时
class ImmediateTimer:
    def __init__(self, delay, function, args=None, kwargs=None):
        self.delay = delay
        self.function = function
        self.args = args if args is not None else []
        self.kwargs = kwargs if kwargs is not None else {}
    def start(self):
        # 立即调用定时任务，不等待
        self.function(*self.args, **self.kwargs)

# DummyApp 用于传递给 schedule_reset 测试，提供 update_reset_time 方法
class DummyApp:
    def update_reset_time(self, platform):
        pass

class TestAIQuotaManager(unittest.TestCase):
    def setUp(self):
        # 为避免对实际文件系统产生影响，在临时目录下进行测试
        self.test_dir = tempfile.TemporaryDirectory()
        self.old_cwd = os.getcwd()
        os.chdir(self.test_dir.name)

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.test_dir.cleanup()

    def test_load_config_creates_file(self):
        # 测试当配置文件不存在时，load_config 能正确创建文件并写入默认配置
        if os.path.exists(CONFIG_FILE):
            os.remove(CONFIG_FILE)
        with patch('tkinter.messagebox.showinfo'):
            config = load_config()
        self.assertTrue(os.path.exists(CONFIG_FILE))
        self.assertIn("order", config)
        self.assertEqual(config["order"], DEFAULT_CONFIG["order"])

    def test_save_config_and_load(self):
        # 测试 save_config 写入的内容能被 load_config 正确读取
        test_config = {
            "TestPlatform": {"type": "daily", "reset_time": "12:00"},
            "order": ["TestPlatform"]
        }
        save_config(test_config)
        with open(CONFIG_FILE, 'r') as f:
            loaded = json.load(f)
        self.assertEqual(loaded, test_config)

    def test_ai_platform_initialization(self):
        # 测试 AIPlatform 类的初始化
        platform = AIPlatform("TestPlatform", "countdown", reset_minutes=90)
        self.assertEqual(platform.name, "TestPlatform")
        self.assertEqual(platform.reset_type, "countdown")
        self.assertEqual(platform.reset_minutes, 90)
        self.assertTrue(platform.is_available)

    def test_schedule_reset_countdown(self):
        # 测试倒计时模式下定时重置的逻辑
        platform = AIPlatform("TestPlatform", "countdown", reset_minutes=1)
        # 初始状态应为可用
        self.assertTrue(platform.is_available)
        dummy_app = DummyApp()
        with patch('threading.Timer', new=ImmediateTimer):
            with patch('win10toast.ToastNotifier') as mock_toast:
                schedule_reset(platform, dummy_app)
                # 由于 ImmediateTimer 立即执行，重置后平台状态应为可用
                self.assertTrue(platform.is_available)
                # 同时应发送通知
                instance = mock_toast.return_value
                instance.show_toast.assert_called_once_with(
                    "TestPlatform 的重置时间已到",
                    "您可以再次使用 TestPlatform。",
                    duration=10
                )

    def test_move_platform_up_down(self):
        # 测试平台上移和下移功能
        test_config = {
            "A": {"type": "countdown", "reset_minutes": 60},
            "B": {"type": "countdown", "reset_minutes": 120},
            "order": ["A", "B"]
        }
        app = Application(test_config)
        app.withdraw()  # 隐藏窗口以避免干扰测试
        try:
            self.assertEqual([p.name for p in app.platforms], ["A", "B"])
            # 将平台 A 下移，使顺序变为 [B, A]
            platform_a = app.platforms[0]
            app.move_platform_down(platform_a)
            self.assertEqual(app.config_data["order"], ["B", "A"])
            # 再将平台 A 上移恢复顺序
            app.move_platform_up(platform_a)
            self.assertEqual(app.config_data["order"], ["A", "B"])
        finally:
            app.destroy()

    def test_add_platform(self):
        # 测试通过 GUI 添加新平台的逻辑
        test_config = {"order": []}
        app = Application(test_config)
        app.withdraw()
        try:
            # 模拟在“添加新平台”区域输入平台名称
            app.new_platform_name.delete(0, tk.END)
            app.new_platform_name.insert(0, "NewPlatform")
            # 默认重置方式为 countdown，此处设置倒计时为 0 小时 1 分钟
            app.reset_type.set("countdown")
            app.new_hours.set(0)
            app.new_minutes.set(1)
            app.add_platform()
            # 检查平台列表和配置中均已存在新平台
            names = [p.name for p in app.platforms]
            self.assertIn("NewPlatform", names)
            self.assertIn("NewPlatform", app.config_data)
            self.assertEqual(app.config_data["NewPlatform"]["type"], "countdown")
            self.assertEqual(app.config_data["NewPlatform"]["reset_minutes"], 1)
        finally:
            app.destroy()

    def test_delete_platform(self):
        # 测试删除平台功能
        test_config = {
            "TestPlatform": {"type": "countdown", "reset_minutes": 60},
            "order": ["TestPlatform"]
        }
        app = Application(test_config)
        app.withdraw()
        try:
            self.assertEqual(len(app.platforms), 1)
            platform = app.platforms[0]
            # 模拟用户确认删除（askokcancel 返回 True）
            with patch('tkinter.messagebox.askokcancel', return_value=True):
                app.delete_platform(platform)
            self.assertEqual(len(app.platforms), 0)
            self.assertNotIn("TestPlatform", app.config_data)
        finally:
            app.destroy()

    def test_edit_platform(self):
        # 测试编辑平台功能
        test_config = {
            "TestPlatform": {"type": "countdown", "reset_minutes": 60},
            "order": ["TestPlatform"]
        }
        app = Application(test_config)
        app.withdraw()
        try:
            platform = app.platforms[0]
            # 打开编辑窗口
            app.open_edit_window(platform)
            # 找到由 Toplevel 创建的编辑窗口
            edit_windows = [w for w in app.winfo_children() if isinstance(w, tk.Toplevel)]
            self.assertTrue(len(edit_windows) > 0)
            edit_window = edit_windows[0]
            # 找到编辑窗口中的平台名称输入框
            entries = [w for w in edit_window.winfo_children() if isinstance(w, tk.Entry)]
            self.assertTrue(len(entries) > 0)
            platform_name_entry = entries[0]
            # 修改平台名称为 "EditedPlatform"
            platform_name_entry.delete(0, tk.END)
            platform_name_entry.insert(0, "EditedPlatform")
            # 找到“保存”按钮并模拟点击
            buttons = [w for w in edit_window.winfo_children() if isinstance(w, tk.Button) and w.cget("text") == "保存"]
            self.assertTrue(len(buttons) > 0)
            save_button = buttons[0]
            save_button.invoke()
            # 检查平台名称和配置是否更新
            names = [p.name for p in app.platforms]
            self.assertIn("EditedPlatform", names)
            self.assertNotIn("TestPlatform", names)
            self.assertIn("EditedPlatform", app.config_data)
            self.assertNotIn("TestPlatform", app.config_data)
        finally:
            app.destroy()

    def test_send_windows_notification(self):
        # 测试 Windows 通知是否调用正确（利用 patch 模拟 ToastNotifier）
        with patch('win10toast.ToastNotifier') as mock_toast:
            instance = mock_toast.return_value
            send_windows_notification("TestPlatform")
            instance.show_toast.assert_called_once_with(
                "TestPlatform 的重置时间已到",
                "您可以再次使用 TestPlatform。",
                duration=10
            )

if __name__ == "__main__":
    unittest.main()