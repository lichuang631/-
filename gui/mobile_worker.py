import time
from datetime import datetime
from pathlib import Path
import shutil
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

from core.timer import NTPTimer
from core.mobile_grabber import MobileDevice, MobileGrabber, GrabResult
from core.run_recorder import RunRecorder


class MobileGrabWorker(QThread):
    log_message = pyqtSignal(str)
    status_changed = pyqtSignal(str)
    countdown_tick = pyqtSignal(float)
    grab_finished = pyqtSignal(bool, str)

    def __init__(
        self,
        device_serial: str,
        target_time: datetime,
        ntp_servers: list,
        ntp_timeout: int,
        grab_config: dict,
    ):
        super().__init__()
        self.device_serial = device_serial
        self.target_timestamp = target_time.timestamp()
        self.ntp_servers = ntp_servers
        self.ntp_timeout = ntp_timeout
        self.grab_config = grab_config
        self._stop_flag = False
        self.run_dir: Optional[Path] = None
        self.log_path: Optional[Path] = None
        try:
            self.run_dir = Path("runs") / datetime.now().strftime("%Y%m%d_%H%M%S")
            self.run_dir.mkdir(parents=True, exist_ok=True)
            self.log_path = self.run_dir / "run.log"
            self._cleanup_old_runs()
        except Exception:
            self.run_dir = None
            self.log_path = None

    def _cleanup_old_runs(self) -> None:
        keep_runs = int(self.grab_config.get("recording_keep_runs", 10))
        if keep_runs <= 0:
            return
        root = Path("runs")
        if not root.exists():
            return
        run_dirs = [
            item
            for item in root.iterdir()
            if item.is_dir() and item.name != self.run_dir.name
        ]
        run_dirs.sort(key=lambda item: item.stat().st_mtime, reverse=True)
        for old_dir in run_dirs[max(0, keep_runs - 1):]:
            try:
                shutil.rmtree(old_dir)
            except Exception:
                pass

    def _log(self, message: str) -> None:
        self.log_message.emit(message)
        if not self.log_path:
            return
        try:
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(f"[{ts}] {message}\n")
        except Exception:
            pass

    def run(self):
        try:
            self._execute()
        except Exception as e:
            self._log(f"异常: {e}")
            self.grab_finished.emit(False, f"异常: {e}")

    def _execute(self):
        self._log("抢票模式: 移动端(APP)")
        if self.log_path:
            self._log(f"运行日志已保存: {self.log_path.resolve()}")

        recorder = None
        if self.run_dir:
            recorder = RunRecorder(
                self.run_dir,
                enabled=self.grab_config.get("recording_enabled", True),
                fps=self.grab_config.get("recording_fps", 10),
                max_width=self.grab_config.get("recording_max_width", 720),
                queue_size=self.grab_config.get("recording_queue_size", 60),
            )
            recorder.save_config_snapshot(self.grab_config)
            if recorder.start():
                self._log(f"复盘录像已开启: {recorder.video_path.resolve()}")
            else:
                self._log("复盘录像未开启或OpenCV不可用，仅保存运行日志")

        self.status_changed.emit("正在同步NTP时间...")
        timer = NTPTimer(servers=self.ntp_servers, timeout=self.ntp_timeout)
        offset = timer.sync()
        if offset == 0.0 and self.ntp_servers:
            self._log("警告: NTP校时失败，使用本地时间")
        else:
            self._log(f"NTP校时完成，偏移量: {offset*1000:.1f}ms")

        self.status_changed.emit("正在连接手机...")
        self._log("正在连接手机...")
        mobile = MobileDevice()
        connect_retries = self.grab_config.get("connect_retries", 3)
        connect_retry_delay = self.grab_config.get("connect_retry_delay", 0.5)
        last_error = None
        for attempt in range(connect_retries):
            if self._stop_flag:
                self.grab_finished.emit(False, "用户手动停止")
                return
            try:
                mobile.connect(serial=self.device_serial)
                last_error = None
                break
            except Exception as e:
                last_error = e
                self._log(f"连接失败({attempt + 1}/{connect_retries}): {e}")
                if attempt + 1 < connect_retries:
                    time.sleep(connect_retry_delay)

        if last_error is not None:
            self._log("请检查:")
            self._log("  1. 手机已通过 USB 数据线连接电脑")
            self._log("  2. 手机已开启 USB 调试（开发者选项中）")
            self._log("  3. 手机弹窗已点击「允许 USB 调试」")
            self.grab_finished.emit(False, f"手机连接失败: {last_error}")
            return

        w, h = mobile.window_size()
        info_name = mobile.device.info.get("productName", "Unknown")
        self._log(f"已连接: {info_name} ({w}×{h})")

        if mobile.check_damai_foreground():
            self._log("大麦APP已在前台")
        else:
            self._log("警告: 当前前台不是大麦APP，请手动切换")

        grabber = MobileGrabber(
            max_retries=self.grab_config.get("max_retries", 20),
            click_interval_ms=self.grab_config.get("click_interval_ms", 50),
            confirm_clicks=self.grab_config.get("confirm_clicks", 10),
            max_run_seconds=self.grab_config.get("max_run_seconds", 180),
            normal_check_interval=self.grab_config.get("normal_check_interval", 1.0),
            fast_check_interval=self.grab_config.get("fast_check_interval", 0.2),
            popup_wait_seconds=self.grab_config.get("popup_wait_seconds", 0.2),
            post_submit_check_seconds=self.grab_config.get("post_submit_check_seconds", 1.0),
            fallback_popup_taps_enabled=self.grab_config.get("fallback_popup_taps_enabled", False),
            fallback_popup_taps=[
                tuple(point)
                for point in self.grab_config.get("fallback_popup_taps", [[0.50, 0.56], [0.50, 0.61]])
            ],
            fallback_popup_after_seconds=self.grab_config.get("fallback_popup_after_seconds", 0.45),
            manual_pause_enabled=self.grab_config.get("manual_pause_enabled", True),
            manual_pause_poll_seconds=self.grab_config.get("manual_pause_poll_seconds", 0.2),
            manual_pause_max_seconds=self.grab_config.get("manual_pause_max_seconds", 45.0),
            opencv_enabled=self.grab_config.get("opencv_enabled", True),
            opencv_threshold=self.grab_config.get("opencv_threshold", 0.75),
            opencv_match_scale=self.grab_config.get("opencv_match_scale", 0.6),
            opencv_scan_interval=self.grab_config.get("opencv_scan_interval", 0.2),
            opencv_refresh_wait_seconds=self.grab_config.get("opencv_refresh_wait_seconds", 0.35),
            opencv_try_wait_seconds=self.grab_config.get("opencv_try_wait_seconds", 0.15),
            opencv_cached_try_seconds=self.grab_config.get("opencv_cached_try_seconds", 6.0),
            opencv_cached_try_max_taps=self.grab_config.get("opencv_cached_try_max_taps", 12),
            opencv_cached_try_verify_every=self.grab_config.get("opencv_cached_try_verify_every", 3),
            opencv_start_delay_seconds=self.grab_config.get("opencv_start_delay_seconds", 0.3),
            opencv_roi=tuple(self.grab_config.get("opencv_roi", [0.0, 0.20, 1.0, 0.98])),
            opencv_templates=self.grab_config.get(
                "opencv_templates",
                {
                    "refresh": "btn_refresh.png",
                    "try": "btn_try.png",
                    "submit": "btn_submit.png",
                },
            ),
            video_stream_enabled=self.grab_config.get("video_stream_enabled", False),
            scrcpy_path=self.grab_config.get("scrcpy_path", ""),
            video_stream_window_title=self.grab_config.get("video_stream_window_title", "DamaiGrabberScrcpy"),
            video_stream_max_fps=self.grab_config.get("video_stream_max_fps", 30),
            video_stream_bit_rate=self.grab_config.get("video_stream_bit_rate", "4M"),
            video_stream_startup_timeout=self.grab_config.get("video_stream_startup_timeout", 10.0),
            video_stream_always_on_top=self.grab_config.get("video_stream_always_on_top", True),
            video_stream_fallback_screenshot=self.grab_config.get("video_stream_fallback_screenshot", True),
            video_stream_device_serial=self.device_serial,
            ticket_priority=self.grab_config.get("ticket_priority", []),
            ticket_positions={
                name: tuple(point)
                for name, point in self.grab_config.get("ticket_positions", {}).items()
            },
            ticket_confirm_pos=tuple(self.grab_config.get("ticket_confirm_pos", [0.78, 0.92])),
            ticket_select_wait_seconds=self.grab_config.get("ticket_select_wait_seconds", 0.35),
            run_recorder=recorder,
            should_stop=lambda: self._stop_flag,
        )
        grabber.prepare_video_stream(lambda msg: self._log(msg))

        advance = self.grab_config.get("advance_seconds", 0.5)

        self.status_changed.emit("等待开票时间...")
        while not self._stop_flag:
            remaining = self.target_timestamp - timer.now()
            if remaining <= advance:
                break
            self.countdown_tick.emit(remaining)
            if remaining > 1.0:
                time.sleep(0.1)
            else:
                time.sleep(0.01)

        if self._stop_flag:
            grabber.close_video_stream()
            if recorder:
                recorder.stop()
            self.grab_finished.emit(False, "用户手动停止")
            return

        if advance > 0:
            self._log(f"提前 {advance} 秒开始点击")

        self.status_changed.emit("抢票中...")
        try:
            result: GrabResult = grabber.run(
                mobile.device, on_log=lambda msg: self._log(msg)
            )
        finally:
            grabber.close_video_stream()
            if recorder:
                recorder.stop()

        self.grab_finished.emit(result.success, result.message)

    def stop(self):
        self._stop_flag = True
