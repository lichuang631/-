import ctypes
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Optional


def _enable_dpi_awareness() -> None:
    """让窗口坐标和截屏像素尽量一致，避免 Windows 缩放导致截错区域。"""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass


_enable_dpi_awareness()


class ScrcpyWindowCapture:
    """启动 scrcpy 投屏窗口，并用 mss 捕获窗口客户区作为 OpenCV 画面源。"""

    def __init__(
        self,
        scrcpy_path: str,
        window_title: str = "DamaiGrabberScrcpy",
        device_serial: str = "",
        max_fps: int = 30,
        video_bit_rate: str = "4M",
        startup_timeout: float = 10.0,
        always_on_top: bool = True,
        fallback_screenshot: bool = True,
    ):
        self.scrcpy_path = scrcpy_path
        self.window_title = window_title
        self.device_serial = device_serial
        self.max_fps = max_fps
        self.video_bit_rate = video_bit_rate
        self.startup_timeout = startup_timeout
        self.always_on_top = always_on_top
        self.fallback_screenshot = fallback_screenshot
        self.process: Optional[subprocess.Popen] = None
        self.hwnd: Optional[int] = None
        self._mss = None
        self._np = None
        self._cv2 = None
        self._started_by_us = False

    def start(self, on_log: Callable[[str], None]) -> bool:
        if sys.platform != "win32":
            on_log("视频流识别仅支持 Windows，已回退普通截图模式")
            return False

        try:
            import cv2
            import mss
            import numpy as np
        except ImportError as e:
            on_log(f"视频流识别缺少依赖 {e.name}，请先安装 mss，已回退普通截图模式")
            return False

        path = Path(self.scrcpy_path)
        if not path.exists():
            on_log(f"scrcpy路径不存在: {self.scrcpy_path}，已回退普通截图模式")
            return False

        self._cv2 = cv2
        self._np = np
        self._mss = mss.mss()

        self.hwnd = self._find_window()
        if self.hwnd:
            on_log("已复用现有 scrcpy 投屏窗口作为视频识别画面源")
            return True

        cmd = [
            str(path),
            "--window-title",
            self.window_title,
            "--no-audio",
            "--max-fps",
            str(self.max_fps),
            "--video-bit-rate",
            self.video_bit_rate,
        ]
        if self.always_on_top:
            cmd.append("--always-on-top")
        if self.device_serial:
            cmd.extend(["-s", self.device_serial])

        env = os.environ.copy()
        env["PATH"] = f"{path.parent};{env.get('PATH', '')}"
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            self.process = subprocess.Popen(
                cmd,
                cwd=str(path.parent),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
                creationflags=creationflags,
            )
            self._started_by_us = True
        except Exception as e:
            on_log(f"scrcpy启动失败: {e}，已回退普通截图模式")
            return False

        end_at = time.time() + self.startup_timeout
        while time.time() < end_at:
            self.hwnd = self._find_window()
            if self.hwnd:
                on_log("scrcpy视频识别画面源已启动")
                return True
            time.sleep(0.05)

        on_log("scrcpy窗口启动超时，已回退普通截图模式")
        return False

    def grab_bgr(self):
        if not self._mss or not self._np or not self._cv2:
            return None

        if not self.hwnd:
            self.hwnd = self._find_window()
        if not self.hwnd:
            return None
        if self._is_window_minimized(self.hwnd):
            return None

        rect = self._client_screen_rect(self.hwnd)
        if not rect:
            return None

        left, top, right, bottom = rect
        width = right - left
        height = bottom - top
        if width < 120 or height < 240:
            return None

        try:
            frame = self._mss.grab(
                {"left": left, "top": top, "width": width, "height": height}
            )
            bgra = self._np.array(frame)
            if self._is_bad_frame(bgra):
                return None
            return self._cv2.cvtColor(bgra, self._cv2.COLOR_BGRA2BGR)
        except Exception:
            return None

    def stop(self) -> None:
        try:
            if self._mss:
                self._mss.close()
        except Exception:
            pass
        self._mss = None
        if self.process and self._started_by_us and self.process.poll() is None:
            try:
                self.process.terminate()
                self.process.wait(timeout=1)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass

    def _find_window(self) -> Optional[int]:
        if sys.platform != "win32":
            return None

        user32 = ctypes.windll.user32
        matches: list[int] = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def enum_proc(hwnd, _):
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            if self.window_title in buffer.value:
                matches.append(int(hwnd))
                return False
            return True

        user32.EnumWindows(enum_proc, 0)
        return matches[0] if matches else None

    def _is_window_minimized(self, hwnd: int) -> bool:
        if sys.platform != "win32":
            return False
        try:
            return bool(ctypes.windll.user32.IsIconic(hwnd))
        except Exception:
            return False

    def _is_bad_frame(self, bgra) -> bool:
        if self._np is None:
            return False
        try:
            sample = bgra[::20, ::20, :3]
            if sample.size == 0:
                return True
            mean = float(sample.mean())
            # 最小化、锁屏或异常遮挡时常见近黑画面，直接触发上层截图兜底。
            return mean < 3.0
        except Exception:
            return False

    def _client_screen_rect(self, hwnd: int) -> Optional[tuple[int, int, int, int]]:
        if sys.platform != "win32":
            return None

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        user32 = ctypes.windll.user32
        rect = RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
            return None
        point = POINT(0, 0)
        if not user32.ClientToScreen(hwnd, ctypes.byref(point)):
            return None
        return (
            int(point.x),
            int(point.y),
            int(point.x + rect.right - rect.left),
            int(point.y + rect.bottom - rect.top),
        )
