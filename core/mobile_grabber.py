import random
import time
from pathlib import Path
from typing import Callable, Optional

import uiautomator2 as u2

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None

from core.grabber import GrabResult
from core.run_recorder import RunRecorder
from core.scrcpy_capture import ScrcpyWindowCapture

_BUY_BUTTON_TEXTS = ["立即抢购", "立即购买", "立即预订", "选座购买", "确定"]

_ORDER_DETECTED_TEXTS = ["提交订单", "立即提交", "确认订单", "确认购买"]

_CONFIRM_BUTTON_TEXTS = ["提交订单", "确认订单"]

_FALLBACK_BUY_POS = (0.63, 0.94)
_FALLBACK_CONFIRM_POS = (0.80, 0.92)
_BUY_BURST_CLICKS = 3
_BUY_DETECT_TIMEOUT = 0.03

_CONTINUE_TEXTS = ["继续尝试"]
_RESELECT_TEXTS = ["返回重新选购", "重新选购"]
_DISMISS_TEXTS = ["我知道了", "确定", "重试"]
_CROWDED_MARKERS = ["抢票人数太多", "继续尝试", "人数太多"]
_STOCK_MARKERS = ["库存不足", "请重新选购", "商品库存不足"]
_ERROR_MARKERS = ["活动太火爆", "网络异常", "系统繁忙", "稍后再试", "出错"]
_SOLD_OUT_MARKERS = ["已售罄", "售罄", "全部售罄"]
_TICKET_PAGE_MARKERS = ["场次", "票档"]
_PAYMENT_PACKAGES = ["alipay", "Alipay", "com.eg.android.AlipayGphone"]
_PAYMENT_MARKERS = ["支付宝", "确认付款", "立即付款", "收银台", "付款方式"]
_MANUAL_VERIFY_MARKERS = ["安全验证", "请完成验证", "拖动滑块", "滑块", "验证码", "点击按钮进行验证", "验证"]

_DEFAULT_TICKET_POSITIONS = {
    "看台380": (0.29, 0.44),
    "看台580": (0.29, 0.52),
    "看台880": (0.29, 0.59),
    "内场1080": (0.29, 0.67),
    "内场1380": (0.29, 0.74),
    "内场1680": (0.29, 0.81),
}


class MobileDevice:
    def __init__(self):
        self.device = None

    def connect(self, serial: str = "") -> None:
        if serial:
            self.device = u2.connect(serial)
        else:
            self.device = u2.connect()

    def check_damai_foreground(self) -> bool:
        current = self.device.app_current()
        return "damai" in current.get("package", "").lower()

    def window_size(self) -> tuple[int, int]:
        return self.device.window_size()


class MobileGrabber:
    def __init__(
        self,
        max_retries: int = 20,
        click_interval_ms: int = 50,
        confirm_clicks: int = 10,
        max_run_seconds: float = 180,
        buy_button_pos: tuple[float, float] = _FALLBACK_BUY_POS,
        confirm_button_pos: tuple[float, float] = _FALLBACK_CONFIRM_POS,
        normal_check_interval: float = 1.0,
        fast_check_interval: float = 0.2,
        popup_wait_seconds: float = 0.2,
        post_submit_check_seconds: float = 1.0,
        fallback_popup_taps_enabled: bool = False,
        fallback_popup_taps: Optional[list[tuple[float, float]]] = None,
        fallback_popup_after_seconds: float = 0.45,
        manual_pause_enabled: bool = True,
        manual_pause_poll_seconds: float = 0.2,
        manual_pause_max_seconds: float = 45.0,
        foreground_check_interval: float = 0.2,
        opencv_enabled: bool = True,
        opencv_threshold: float = 0.75,
        opencv_match_scale: float = 0.6,
        opencv_scan_interval: float = 0.2,
        opencv_refresh_wait_seconds: float = 0.35,
        opencv_try_wait_seconds: float = 0.15,
        opencv_cached_try_seconds: float = 6.0,
        opencv_cached_try_max_taps: int = 12,
        opencv_cached_try_verify_every: int = 3,
        opencv_start_delay_seconds: float = 0.3,
        opencv_visual_retry_cooldown_seconds: float = 0.06,
        opencv_roi: tuple[float, float, float, float] = (0.0, 0.20, 1.0, 0.98),
        opencv_templates: Optional[dict[str, str]] = None,
        video_stream_enabled: bool = False,
        scrcpy_path: str = "",
        video_stream_window_title: str = "DamaiGrabberScrcpy",
        video_stream_max_fps: int = 30,
        video_stream_bit_rate: str = "4M",
        video_stream_startup_timeout: float = 10.0,
        video_stream_always_on_top: bool = True,
        video_stream_fallback_screenshot: bool = True,
        video_stream_device_serial: str = "",
        ticket_priority: Optional[list[str]] = None,
        ticket_positions: Optional[dict[str, tuple[float, float]]] = None,
        ticket_confirm_pos: tuple[float, float] = (0.78, 0.92),
        ticket_select_wait_seconds: float = 0.35,
        run_recorder: Optional[RunRecorder] = None,
        should_stop: Optional[Callable[[], bool]] = None,
    ):
        self.max_retries = max_retries
        self.click_interval_ms = click_interval_ms
        self.confirm_clicks = confirm_clicks
        self.max_run_seconds = max_run_seconds
        self.buy_button_pos = buy_button_pos
        self.confirm_button_pos = confirm_button_pos
        self.normal_check_interval = normal_check_interval
        self.fast_check_interval = fast_check_interval
        self.popup_wait_seconds = popup_wait_seconds
        self.post_submit_check_seconds = post_submit_check_seconds
        self.fallback_popup_taps_enabled = fallback_popup_taps_enabled
        self.fallback_popup_taps = fallback_popup_taps or [(0.50, 0.56), (0.50, 0.61)]
        self.fallback_popup_after_seconds = fallback_popup_after_seconds
        self.manual_pause_enabled = manual_pause_enabled
        self.manual_pause_poll_seconds = manual_pause_poll_seconds
        self.manual_pause_max_seconds = manual_pause_max_seconds
        self.foreground_check_interval = max(0.01, foreground_check_interval)
        self.opencv_enabled = opencv_enabled
        self.opencv_threshold = opencv_threshold
        self.opencv_match_scale = opencv_match_scale
        self.opencv_scan_interval = opencv_scan_interval
        self.opencv_refresh_wait_seconds = opencv_refresh_wait_seconds
        self.opencv_try_wait_seconds = opencv_try_wait_seconds
        self.opencv_cached_try_seconds = opencv_cached_try_seconds
        self.opencv_cached_try_max_taps = opencv_cached_try_max_taps
        self.opencv_cached_try_verify_every = max(1, opencv_cached_try_verify_every)
        self.opencv_start_delay_seconds = opencv_start_delay_seconds
        self.opencv_visual_retry_cooldown_seconds = max(0.0, opencv_visual_retry_cooldown_seconds)
        self.opencv_roi = opencv_roi
        self.opencv_templates = opencv_templates or {
            "refresh": "btn_refresh.png",
            "try": "btn_try.png",
            "submit": "btn_submit.png",
            "verify_title": "btn_verify_title.png",
            "verify_slider": "btn_verify_slider.png",
        }
        self.video_stream_enabled = video_stream_enabled
        self.scrcpy_path = scrcpy_path
        self.video_stream_window_title = video_stream_window_title
        self.video_stream_max_fps = video_stream_max_fps
        self.video_stream_bit_rate = video_stream_bit_rate
        self.video_stream_startup_timeout = video_stream_startup_timeout
        self.video_stream_always_on_top = video_stream_always_on_top
        self.video_stream_fallback_screenshot = video_stream_fallback_screenshot
        self.video_stream_device_serial = video_stream_device_serial
        self._video_capture: Optional[ScrcpyWindowCapture] = None
        self._video_enabled_runtime = False
        self._video_source_logged = False
        self._screenshot_fallback_logged = False
        self._screen_to_device_scale = (1.0, 1.0)
        self._device_window_size: Optional[tuple[int, int]] = None
        self._opencv_ready_logged = False
        self._template_cache = {}
        self._scaled_template_cache = {}
        self._cached_try_point: Optional[tuple[int, int]] = None
        self._cached_try_until = 0.0
        self._cached_try_taps = 0
        self._cached_try_need_verify = False
        self._foreground_state_cache = "unknown"
        self._foreground_checked_at = 0.0
        self._foreground_paused = False
        self._flow_phase = "buying"
        self._submit_armed = True
        self._last_visual_retry_signature: Optional[tuple[str, int, int]] = None
        self._last_visual_retry_at = 0.0
        self.ticket_priority = ticket_priority or []
        self.ticket_positions = ticket_positions or _DEFAULT_TICKET_POSITIONS
        self.ticket_confirm_pos = ticket_confirm_pos
        self.ticket_select_wait_seconds = ticket_select_wait_seconds
        self.run_recorder = run_recorder
        self.should_stop = should_stop or (lambda: False)

    def prepare_video_stream(self, on_log: Callable[[str], None]) -> None:
        """提前启动 scrcpy 画面源；失败时保留原截图模式。"""
        if not self.video_stream_enabled:
            return
        if not self.scrcpy_path:
            on_log("已开启视频流识别，但未配置scrcpy_path，已回退普通截图模式")
            return

        capture = ScrcpyWindowCapture(
            scrcpy_path=self.scrcpy_path,
            window_title=self.video_stream_window_title,
            device_serial=self.video_stream_device_serial,
            max_fps=self.video_stream_max_fps,
            video_bit_rate=self.video_stream_bit_rate,
            startup_timeout=self.video_stream_startup_timeout,
            always_on_top=self.video_stream_always_on_top,
            fallback_screenshot=self.video_stream_fallback_screenshot,
        )
        self._video_enabled_runtime = capture.start(on_log)
        if self._video_enabled_runtime:
            self._video_capture = capture
        else:
            capture.stop()

    def close_video_stream(self) -> None:
        if self._video_capture:
            self._video_capture.stop()
        self._video_capture = None
        self._video_enabled_runtime = False

    def _jittered_interval(self) -> float:
        # 给连点间隔加 ±30% 抖动，避免完美的机械节奏被风控标记
        return self.click_interval_ms / 1000 * random.uniform(0.7, 1.3)

    def _get_device_window_size(self, device) -> tuple[int, int]:
        if self._device_window_size is None:
            self._device_window_size = device.window_size()
        return self._device_window_size

    def _jittered_pos(self, w: int, h: int, fx: float, fy: float) -> tuple[int, int]:
        # 坐标兜底点击时落点加几像素随机偏移，避免每次点同一个像素
        jx = int(w * fx) + random.randint(-8, 8)
        jy = int(h * fy) + random.randint(-8, 8)
        return jx, jy

    def _clear_cached_try(self) -> None:
        self._cached_try_point = None
        self._cached_try_until = 0.0
        self._cached_try_taps = 0
        self._cached_try_need_verify = False

    def _clear_visual_retry_cooldown(self) -> None:
        self._last_visual_retry_signature = None
        self._last_visual_retry_at = 0.0

    def _restore_buying_phase(self) -> None:
        self._flow_phase = "buying"
        self._submit_armed = True
        self._clear_cached_try()
        self._clear_visual_retry_cooldown()

    def _mark_post_submit_phase(self) -> None:
        self._flow_phase = "post_submit"
        self._submit_armed = False
        self._clear_cached_try()
        self._clear_visual_retry_cooldown()

    def _visual_retry_signature(self, template_key: str, x: int, y: int) -> tuple[str, int, int]:
        return template_key, int(round(x / 8)), int(round(y / 8))

    def _is_visual_retry_on_cooldown(self, template_key: str, x: int, y: int) -> bool:
        if not self._is_visual_fast_mode() or self.opencv_visual_retry_cooldown_seconds <= 0:
            return False
        signature = self._visual_retry_signature(template_key, x, y)
        now = time.time()
        return (
            self._last_visual_retry_signature == signature
            and now - self._last_visual_retry_at < self.opencv_visual_retry_cooldown_seconds
        )

    def _record_visual_retry_tap(self, template_key: str, x: int, y: int) -> None:
        if not self._is_visual_fast_mode() or self.opencv_visual_retry_cooldown_seconds <= 0:
            return
        self._last_visual_retry_signature = self._visual_retry_signature(template_key, x, y)
        self._last_visual_retry_at = time.time()

    def _read_foreground_state(self, device, force: bool = False) -> str:
        now = time.time()
        if (
            not force
            and self._foreground_checked_at > 0
            and now - self._foreground_checked_at < self.foreground_check_interval
        ):
            return self._foreground_state_cache

        try:
            package_name = device.app_current().get("package", "").lower()
            if any(marker.lower() in package_name for marker in _PAYMENT_PACKAGES):
                state = "payment"
            elif "damai" in package_name:
                state = "damai"
            else:
                state = "other"
        except Exception:
            state = "unknown"

        self._foreground_state_cache = state
        self._foreground_checked_at = now
        return state

    def _wait_for_safe_foreground(
        self,
        device,
        on_log: Callable[[str], None],
        deadline: float,
        force: bool = False,
    ) -> str:
        while True:
            if self.should_stop():
                return "stopped"
            if time.time() >= deadline:
                return "timeout"

            state = self._read_foreground_state(
                device,
                force=force or self._foreground_paused,
            )
            force = False
            if state == "damai":
                if self._foreground_paused:
                    on_log("检测到大麦APP已回到前台，恢复自动点击")
                self._foreground_paused = False
                return "damai"
            if state == "payment":
                self._foreground_paused = False
                return "payment"

            self._clear_cached_try()
            self._clear_visual_retry_cooldown()
            if not self._foreground_paused:
                if state == "unknown":
                    on_log("暂时无法确认前台应用，已暂停自动点击")
                else:
                    on_log("检测到前台不是大麦APP，已暂停自动点击；切回大麦后自动恢复")
            self._foreground_paused = True
            time.sleep(self.foreground_check_interval)

    def _tap_points(self, device, points: list[tuple[int, int]]) -> bool:
        if self._read_foreground_state(device) != "damai":
            self._clear_cached_try()
            return False
        commands = [f"input tap {x} {y}" for x, y in points]
        try:
            timeout = max(2.0, len(points) * 0.3)
            device.shell("; ".join(commands), timeout=timeout)
        except Exception:
            for x, y in points:
                device.click(x, y)
        return True

    def _tap_relative_points(
        self,
        device,
        rel_points: list[tuple[float, float]],
        jitter: int = 4,
    ) -> bool:
        w, h = self._get_device_window_size(device)
        points = [
            (int(w * fx) + random.randint(-jitter, jitter), int(h * fy) + random.randint(-jitter, jitter))
            for fx, fy in rel_points
        ]
        return self._tap_points(device, points)

    def _exists_any_text(self, device, texts: list[str], timeout: float = 0.01) -> bool:
        for text in texts:
            try:
                if device(text=text).exists(timeout=timeout):
                    return True
            except Exception:
                pass
        return False

    def _exists_any_contains(self, device, texts: list[str], timeout: float = 0.01) -> bool:
        for text in texts:
            try:
                if device(textContains=text).exists(timeout=timeout):
                    return True
            except Exception:
                pass
        return False

    def _click_first_text(self, device, texts: list[str], timeout: float = 0.02) -> Optional[str]:
        if self._read_foreground_state(device) != "damai":
            return None
        for text in texts:
            try:
                target = device(text=text)
                if target.exists(timeout=timeout):
                    target.click()
                    return text
            except Exception:
                pass
        return None

    def _is_order_page(self, device) -> bool:
        return self._exists_any_text(device, _ORDER_DETECTED_TEXTS, _BUY_DETECT_TIMEOUT)

    def _screenshot_bgr(self, device, on_log: Optional[Callable[[str], None]] = None):
        if cv2 is None or np is None:
            return None
        if self._video_enabled_runtime and self._video_capture:
            try:
                frame = self._video_capture.grab_bgr()
                if frame is not None:
                    device_w, device_h = self._get_device_window_size(device)
                    frame_h, frame_w = frame.shape[:2]
                    if frame_w > 0 and frame_h > 0:
                        self._screen_to_device_scale = (
                            device_w / frame_w,
                            device_h / frame_h,
                        )
                    if on_log and not self._video_source_logged:
                        on_log("OpenCV识别使用 scrcpy 视频窗口帧")
                        self._video_source_logged = True
                    if self.run_recorder:
                        self.run_recorder.record_frame(frame)
                    return frame
                if (
                    on_log
                    and self.video_stream_fallback_screenshot
                    and not self._screenshot_fallback_logged
                ):
                    reason = getattr(self._video_capture, "last_error_reason", "") or "未知原因"
                    on_log(f"scrcpy视频帧暂不可用（原因：{reason}），OpenCV已回退普通手机截图")
                    self._screenshot_fallback_logged = True
            except Exception as e:
                if (
                    on_log
                    and self.video_stream_fallback_screenshot
                    and not self._screenshot_fallback_logged
                ):
                    on_log(f"scrcpy视频帧读取异常（原因：{e}），OpenCV已回退普通手机截图")
                    self._screenshot_fallback_logged = True
                if not self.video_stream_fallback_screenshot:
                    return None
        if self._video_enabled_runtime and not self.video_stream_fallback_screenshot:
            return None
        try:
            image = device.screenshot()
            rgb = np.array(image.convert("RGB"))
            self._screen_to_device_scale = (1.0, 1.0)
            frame = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            if self.run_recorder:
                self.run_recorder.record_frame(frame)
            return frame
        except Exception:
            return None

    def _load_template_gray(self, template_path: str):
        if cv2 is None:
            return None
        path = Path(template_path)
        if not path.exists():
            return None
        cache_key = str(path.resolve())
        if cache_key not in self._template_cache:
            self._template_cache[cache_key] = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        return self._template_cache[cache_key]

    def _match_template(self, screen_bgr, template_path: str) -> tuple[bool, int, int, float]:
        template = self._load_template_gray(template_path)
        if screen_bgr is None or template is None:
            return False, 0, 0, 0.0
        screen_gray = cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2GRAY)
        return self._match_template_gray(screen_gray, template_path)

    def _match_template_gray(
        self,
        screen_gray,
        template_path: str,
        offset_x: int = 0,
        offset_y: int = 0,
    ) -> tuple[bool, int, int, float]:
        template = self._load_template_gray(template_path)
        if screen_gray is None or template is None:
            return False, 0, 0, 0.0
        scale = self.opencv_match_scale
        device_scale_x, device_scale_y = self._screen_to_device_scale
        template_scale_x = 1.0 / device_scale_x
        template_scale_y = 1.0 / device_scale_y
        if 0 < scale < 1.0 or abs(template_scale_x - 1.0) > 0.001 or abs(template_scale_y - 1.0) > 0.001:
            screen_gray = cv2.resize(screen_gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
            cache_key = (
                str(Path(template_path).resolve()),
                round(scale, 3),
                round(template_scale_x, 3),
                round(template_scale_y, 3),
            )
            if cache_key not in self._scaled_template_cache:
                fx = max(0.05, scale * template_scale_x)
                fy = max(0.05, scale * template_scale_y)
                self._scaled_template_cache[cache_key] = cv2.resize(
                    template,
                    None,
                    fx=fx,
                    fy=fy,
                    interpolation=cv2.INTER_AREA,
                )
            template = self._scaled_template_cache[cache_key]
        if screen_gray.shape[0] < template.shape[0] or screen_gray.shape[1] < template.shape[1]:
            return False, 0, 0, 0.0
        result = cv2.matchTemplate(screen_gray, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val < self.opencv_threshold:
            return False, 0, 0, float(max_val)
        h, w = template.shape[:2]
        screen_x = offset_x + int((max_loc[0] + w // 2) / scale)
        screen_y = offset_y + int((max_loc[1] + h // 2) / scale)
        return (
            True,
            int(screen_x * device_scale_x),
            int(screen_y * device_scale_y),
            float(max_val),
        )

    def _opencv_scan_gray(self, screen_bgr):
        screen_gray = cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2GRAY)
        height, width = screen_gray.shape[:2]
        x1f, y1f, x2f, y2f = self.opencv_roi
        x1 = max(0, min(width, int(width * x1f)))
        y1 = max(0, min(height, int(height * y1f)))
        x2 = max(x1, min(width, int(width * x2f)))
        y2 = max(y1, min(height, int(height * y2f)))
        if x2 <= x1 or y2 <= y1:
            return screen_gray, 0, 0
        return screen_gray[y1:y2, x1:x2], x1, y1

    def _handle_opencv_buttons(
        self,
        device,
        on_log: Callable[[str], None],
        allow_submit: bool = True,
    ) -> str:
        if not self.opencv_enabled:
            return "normal"
        if cv2 is None or np is None:
            if not self._opencv_ready_logged:
                on_log("OpenCV未安装，已跳过图片按钮识别")
                self._opencv_ready_logged = True
            return "normal"

        screen = self._screenshot_bgr(device, on_log)
        if screen is None:
            return "normal"
        screen_gray, offset_x, offset_y = self._opencv_scan_gray(screen)

        verify_title_path = self.opencv_templates.get("verify_title", "")
        verify_slider_path = self.opencv_templates.get("verify_slider", "")
        title_matched, _, _, title_score = self._match_template_gray(
            screen_gray, verify_title_path, offset_x, offset_y
        )
        slider_matched, _, _, slider_score = self._match_template_gray(
            screen_gray, verify_slider_path, offset_x, offset_y
        )
        if title_matched:
            if slider_matched:
                on_log(
                    f"OpenCV识别到「验证提示+滑块验证」"
                    f"(title={title_score:.2f}, slider={slider_score:.2f})，暂停自动点击"
                )
            else:
                on_log(f"OpenCV识别到「验证提示」(score={title_score:.2f})，暂停自动点击")
            return "manual_pause"

        retry_candidates = []
        for label, template_key, wait_seconds in [
            ("努力刷新", "refresh", self.opencv_refresh_wait_seconds),
            ("继续尝试", "try", self.opencv_try_wait_seconds),
        ]:
            template_path = self.opencv_templates.get(template_key, "")
            matched, x, y, score = self._match_template_gray(screen_gray, template_path, offset_x, offset_y)
            if matched and self._is_retry_action_area(device, y):
                retry_candidates.append((score, label, template_key, x, y, wait_seconds))

        if retry_candidates:
            score, label, template_key, x, y, wait_seconds = max(
                retry_candidates,
                key=lambda candidate: candidate[0],
            )
            if self._is_visual_retry_on_cooldown(template_key, x, y):
                return "retry"
            if not self._tap_points(device, [(x, y)]):
                return "normal"
            on_log(f"OpenCV识别到「{label}」(score={score:.2f})，已点击")

            if template_key == "refresh":
                self._restore_buying_phase()
            elif self._flow_phase == "post_submit":
                self._submit_armed = True
                if self._is_visual_fast_mode():
                    self._clear_cached_try()
                elif self._is_continue_try_context(device):
                    self._cached_try_point = (x, y)
                    self._cached_try_until = time.time() + self.opencv_cached_try_seconds
                    self._cached_try_taps = 0
                    self._cached_try_need_verify = False
            else:
                self._clear_cached_try()
            self._record_visual_retry_tap(template_key, x, y)

            if not self._is_visual_fast_mode():
                time.sleep(wait_seconds)
            return "retry"

        if allow_submit and self._submit_armed:
            template_path = self.opencv_templates.get("submit", "")
            matched, x, y, score = self._match_template_gray(screen_gray, template_path, offset_x, offset_y)
            if matched:
                if not self._tap_points(device, [(x, y)]):
                    return "normal"
                on_log(f"OpenCV识别到「立即提交」(score={score:.2f})，已点击")
                self._mark_post_submit_phase()
                return "success"

        return "normal"

    def _is_retry_action_area(self, device, y: int) -> bool:
        try:
            _, h = self._get_device_window_size(device)
            return int(h * 0.35) <= y < int(h * 0.82)
        except Exception:
            return False

    def _is_continue_try_context(self, device) -> bool:
        """只有在订单页或拥挤弹窗附近，才允许「继续尝试」启用缓存连点。"""
        try:
            if self._is_order_page(device):
                return True
            return self._exists_any_contains(device, _CROWDED_MARKERS, timeout=0.001)
        except Exception:
            return False

    def _tap_cached_try_if_available(self, device, on_log: Callable[[str], None]) -> bool:
        if self._is_visual_fast_mode():
            self._clear_cached_try()
            return False
        if not self._cached_try_point:
            return False
        if time.time() >= self._cached_try_until:
            self._clear_cached_try()
            return False
        if self._cached_try_taps >= self.opencv_cached_try_max_taps:
            self._clear_cached_try()
            return False

        if not self._tap_points(device, [self._cached_try_point]):
            self._clear_cached_try()
            return False
        self._cached_try_taps += 1
        self._cached_try_need_verify = self._cached_try_taps % self.opencv_cached_try_verify_every == 0
        on_log(f"快速点击缓存「继续尝试」坐标（第 {self._cached_try_taps} 次）")
        time.sleep(self.opencv_try_wait_seconds)
        return True

    def _is_ticket_page(self, device) -> bool:
        return all(self._exists_any_contains(device, [marker]) for marker in _TICKET_PAGE_MARKERS)

    def _is_visual_fast_mode(self) -> bool:
        return self.opencv_enabled and self._video_enabled_runtime

    def _is_payment_page(self, device, include_text: bool = True) -> bool:
        try:
            package_name = device.app_current().get("package", "")
            if any(marker.lower() in package_name.lower() for marker in _PAYMENT_PACKAGES):
                return True
        except Exception:
            pass
        if not include_text:
            return False
        return self._exists_any_contains(device, _PAYMENT_MARKERS)

    def _is_manual_verify_page(self, device, include_opencv: bool = True) -> bool:
        if not self.manual_pause_enabled:
            return False
        if self._exists_any_contains(device, _MANUAL_VERIFY_MARKERS):
            return True
        if not include_opencv:
            return False
        return self._is_opencv_verify_page(device)

    def _is_opencv_verify_page(self, device) -> bool:
        if not self.opencv_enabled or cv2 is None or np is None:
            return False
        screen = self._screenshot_bgr(device)
        if screen is None:
            return False
        screen_gray, offset_x, offset_y = self._opencv_scan_gray(screen)
        template_path = self.opencv_templates.get("verify_title", "")
        matched, _, _, _ = self._match_template_gray(screen_gray, template_path, offset_x, offset_y)
        return matched

    def _wait_manual_intervention(self, device, on_log: Callable[[str], None], deadline: float) -> str:
        self._clear_cached_try()

        end_at = min(deadline, time.time() + self.manual_pause_max_seconds)
        on_log("检测到验证/需要人工处理页面，已暂停自动点击，请手动处理")
        while time.time() < end_at:
            if self.should_stop():
                return "stopped"
            if self._is_payment_page(device):
                return "payment"
            if self._is_order_page(device):
                return "order"
            if not self._is_manual_verify_page(device):
                on_log("人工处理页面已消失，继续自动尝试")
                return "retry_fast"
            time.sleep(self.manual_pause_poll_seconds)

        on_log("人工处理等待超时，继续自动尝试")
        return "retry_fast"

    def _handle_page_state(
        self,
        device,
        on_log: Callable[[str], None],
        include_opencv_verify: bool = True,
    ) -> str:
        """低频检查页面状态，只在弹窗/订单/售罄等特殊页面介入。"""
        if self._is_payment_page(device):
            on_log("检测到支付宝/支付界面，停止脚本，请手动完成支付")
            return "payment"

        if self._is_manual_verify_page(device, include_opencv=include_opencv_verify):
            return "manual_pause"

        if self._exists_any_contains(device, _SOLD_OUT_MARKERS):
            on_log("检测到售罄/暂不可售状态，停止抢票")
            return "soldout"

        if self._exists_any_contains(device, _CROWDED_MARKERS):
            clicked = self._click_first_text(device, _CONTINUE_TEXTS)
            if clicked:
                on_log(f"检测到抢票人数过多弹窗，已点击「{clicked}」")
                time.sleep(self.popup_wait_seconds)
                return "retry_fast"
            clicked = self._click_first_text(device, _RESELECT_TEXTS)
            if clicked:
                on_log(f"检测到抢票人数过多弹窗，已点击「{clicked}」")
                time.sleep(self.popup_wait_seconds)
                return "retry_fast"
            on_log("检测到抢票人数过多弹窗，但未找到「继续尝试」按钮")
            return "retry_fast"

        if self._exists_any_contains(device, _STOCK_MARKERS):
            clicked = self._click_first_text(device, _DISMISS_TEXTS + _RESELECT_TEXTS)
            if clicked:
                on_log(f"检测到库存不足提示，已点击「{clicked}」并继续尝试")
                time.sleep(self.popup_wait_seconds)
                return "retry_fast"
            on_log("检测到库存不足提示，但未找到可点击的关闭按钮")
            return "retry_fast"

        if self._exists_any_contains(device, _ERROR_MARKERS):
            clicked = self._click_first_text(device, _DISMISS_TEXTS + _CONTINUE_TEXTS + _RESELECT_TEXTS)
            if clicked:
                on_log(f"检测到异常/重试提示，已点击「{clicked}」")
                time.sleep(self.popup_wait_seconds)
                return "retry_fast"
            on_log("检测到异常/重试提示，但未找到可点击按钮")
            return "retry_fast"

        if self._is_order_page(device):
            return "order"

        if self._is_ticket_page(device):
            return "ticket"

        return "normal"

    def _select_ticket_by_priority(self, device, on_log: Callable[[str], None], deadline: float) -> str:
        """在票档页按配置优先级尝试选票档并点击确定。"""
        if not self.ticket_priority:
            return "normal"

        for ticket_name in self.ticket_priority:
            foreground_state = self._wait_for_safe_foreground(device, on_log, deadline)
            if foreground_state != "damai":
                return foreground_state

            pos = self.ticket_positions.get(ticket_name)
            if not pos:
                on_log(f"票档「{ticket_name}」没有配置坐标，已跳过")
                continue

            on_log(f"票档页：尝试选择「{ticket_name}」")
            self._tap_relative_points(device, [pos])
            time.sleep(0.08)
            self._tap_relative_points(device, [self.ticket_confirm_pos])
            time.sleep(self.ticket_select_wait_seconds)

            state = self._handle_page_state(device, on_log)
            if state == "manual_pause":
                state = self._wait_manual_intervention(device, on_log, deadline)
            if state in ("order", "soldout", "retry_fast", "payment"):
                return state

            if not self._is_ticket_page(device):
                state = self._handle_page_state(device, on_log)
                if state == "manual_pause":
                    state = self._wait_manual_intervention(device, on_log, deadline)
                if state in ("order", "soldout", "retry_fast", "payment"):
                    return state

        on_log("票档页：所有配置票档都尝试过，继续回流")
        return "retry_fast"

    def click_buy(self, device, on_log: Callable[[str], None], deadline: float) -> str:
        w, h = self._get_device_window_size(device)
        fx, fy = self.buy_button_pos
        check_gap = self.normal_check_interval
        last_check = 0.0
        detect_delay = (
            0.0
            if self._is_visual_fast_mode() and self._flow_phase == "post_submit" and self._submit_armed
            else self.opencv_start_delay_seconds
        )
        detect_enabled_at = time.time() + detect_delay

        for _ in range(self.max_retries):
            foreground_state = self._wait_for_safe_foreground(device, on_log, deadline)
            if foreground_state != "damai":
                return foreground_state

            if time.time() >= detect_enabled_at and self._tap_cached_try_if_available(device, on_log):
                check_gap = self.fast_check_interval
                if not self._cached_try_need_verify:
                    continue

            now = time.time()
            if time.time() >= detect_enabled_at and now - last_check >= check_gap:
                if not self._is_visual_fast_mode() and self._is_payment_page(device):
                    on_log("检测到支付宝/支付界面，停止脚本，请手动完成支付")
                    return "payment"

                opencv_state = self._handle_opencv_buttons(device, on_log)
                if opencv_state == "manual_pause":
                    state = self._wait_manual_intervention(device, on_log, deadline)
                    if state in ("order", "soldout", "payment", "stopped", "timeout"):
                        return state
                    if state == "retry_fast":
                        check_gap = self.fast_check_interval
                        last_check = time.time()
                        continue
                if opencv_state == "success":
                    return "submitted"
                if opencv_state == "retry":
                    check_gap = self.fast_check_interval
                    last_check = time.time()
                    continue

                if self._is_visual_fast_mode():
                    last_check = time.time()
                else:
                    state = self._handle_page_state(device, on_log, include_opencv_verify=False)
                    if state == "manual_pause":
                        state = self._wait_manual_intervention(device, on_log, deadline)
                    if state in ("order", "soldout", "payment"):
                        return state
                    if state in ("stopped", "timeout"):
                        return state
                    if state == "ticket":
                        state = self._select_ticket_by_priority(device, on_log, deadline)
                        if state in ("order", "soldout", "payment", "stopped", "timeout"):
                            return state
                    last_check = time.time()
                    check_gap = self.fast_check_interval if state == "retry_fast" else self.normal_check_interval

            if self._is_visual_fast_mode() and self._flow_phase == "post_submit":
                time.sleep(0.01)
                continue

            points = [
                self._jittered_pos(w, h, fx, fy)
                for _ in range(_BUY_BURST_CLICKS)
            ]
            self._tap_points(device, points)

            if time.time() < detect_enabled_at:
                continue

            if not self._is_visual_fast_mode() and self._is_order_page(device):
                state = self._handle_page_state(device, on_log, include_opencv_verify=False)
                if state == "manual_pause":
                    state = self._wait_manual_intervention(device, on_log, deadline)
                if state in ("order", "soldout", "payment"):
                    return state
                if state in ("stopped", "timeout"):
                    return state
                if state == "ticket":
                    state = self._select_ticket_by_priority(device, on_log, deadline)
                    if state in ("order", "soldout", "payment", "stopped", "timeout"):
                        return state
                check_gap = self.fast_check_interval if state == "retry_fast" else self.normal_check_interval
                last_check = time.time()
                continue

            now = time.time()
            if now - last_check >= check_gap:
                if not self._is_visual_fast_mode() and self._is_payment_page(device):
                    on_log("检测到支付宝/支付界面，停止脚本，请手动完成支付")
                    return "payment"

                opencv_state = self._handle_opencv_buttons(device, on_log)
                if opencv_state == "manual_pause":
                    state = self._wait_manual_intervention(device, on_log, deadline)
                    if state in ("order", "soldout", "payment", "stopped", "timeout"):
                        return state
                    if state == "retry_fast":
                        check_gap = self.fast_check_interval
                        last_check = time.time()
                        continue
                if opencv_state == "success":
                    return "submitted"
                if opencv_state == "retry":
                    check_gap = self.fast_check_interval
                    last_check = time.time()
                    continue

                if self._is_visual_fast_mode():
                    last_check = time.time()
                    check_gap = self.normal_check_interval
                    continue

                state = self._handle_page_state(device, on_log, include_opencv_verify=False)
                if state == "manual_pause":
                    state = self._wait_manual_intervention(device, on_log, deadline)
                if state in ("order", "soldout", "payment"):
                    return state
                if state in ("stopped", "timeout"):
                    return state
                if state == "ticket":
                    state = self._select_ticket_by_priority(device, on_log, deadline)
                    if state in ("order", "soldout", "payment", "stopped", "timeout"):
                        return state

                last_check = time.time()
                check_gap = self.fast_check_interval if state == "retry_fast" else self.normal_check_interval

        return "retry"

    def confirm_order(self, device, on_log: Callable[[str], None]) -> bool:
        w, h = self._get_device_window_size(device)
        fx, fy = self.confirm_button_pos
        points = [
            self._jittered_pos(w, h, fx, fy)
            for _ in range(self.confirm_clicks)
        ]
        if not self._tap_points(device, points):
            return False
        self._mark_post_submit_phase()
        return True

    def _recover_after_submit_timeout(self, device, on_log: Callable[[str], None], deadline: float) -> str:
        foreground_state = self._wait_for_safe_foreground(device, on_log, deadline, force=True)
        if foreground_state == "payment":
            return "success"
        if foreground_state in ("stopped", "timeout"):
            return foreground_state

        state = self._handle_page_state(device, on_log, include_opencv_verify=False)
        if state == "manual_pause":
            state = self._wait_manual_intervention(device, on_log, deadline)
        if state == "payment":
            return "success"
        if state in ("stopped", "timeout"):
            return state
        if state == "soldout":
            return "soldout"
        if state == "order":
            self._flow_phase = "post_submit"
            self._submit_armed = True
            self._clear_cached_try()
            on_log("提交后仍停留在订单页，已重新允许提交")
            return "order"

        if state == "ticket":
            on_log("提交后回到票档页，已恢复购买阶段继续回流")
        elif state == "retry_fast":
            on_log("提交后已处理回流提示，恢复购买阶段继续尝试")
        else:
            on_log("提交后暂未确认进入支付，已恢复购买阶段继续回流")
        self._restore_buying_phase()
        return "retry"

    def _wait_after_submit(self, device, on_log: Callable[[str], None], deadline: float) -> str:
        end_at = min(time.time() + self.post_submit_check_seconds, deadline)
        wait_start = time.time()
        fallback_tapped = False
        last_opencv_scan = 0.0
        while time.time() < end_at:
            foreground_state = self._wait_for_safe_foreground(device, on_log, deadline)
            if foreground_state == "payment":
                return "success"
            if foreground_state != "damai":
                return foreground_state
            if not self._is_visual_fast_mode():
                if self._is_payment_page(device):
                    return "success"

            if self._tap_cached_try_if_available(device, on_log):
                if not self._cached_try_need_verify:
                    continue

            now = time.time()
            if now - last_opencv_scan >= self.opencv_scan_interval:
                opencv_state = self._handle_opencv_buttons(
                    device,
                    on_log,
                    allow_submit=self._submit_armed,
                )
                last_opencv_scan = time.time()
                if opencv_state == "manual_pause":
                    state = self._wait_manual_intervention(device, on_log, deadline)
                    if state == "payment":
                        return "success"
                    if state == "order":
                        continue
                    if state in ("stopped", "timeout"):
                        return state
                    if state == "soldout":
                        return "soldout"
                    if state == "retry_fast":
                        continue
                if opencv_state == "retry":
                    continue
                if opencv_state == "success":
                    continue

            if self._is_visual_fast_mode():
                time.sleep(0.02)
                continue

            state = self._handle_page_state(device, on_log, include_opencv_verify=False)
            if state == "manual_pause":
                state = self._wait_manual_intervention(device, on_log, deadline)
            if state == "payment":
                return "success"
            if state == "order":
                continue
            if state in ("stopped", "timeout"):
                return state
            if state == "soldout":
                return "soldout"
            if state == "retry_fast":
                continue

            if (
                self.fallback_popup_taps_enabled
                and not fallback_tapped
                and now - wait_start >= self.fallback_popup_after_seconds
            ):
                self._tap_relative_points(device, self.fallback_popup_taps)
                on_log("未读到弹窗文字，已尝试点击常见弹窗按钮位置兜底")
                fallback_tapped = True
                time.sleep(self.popup_wait_seconds)
                continue
            time.sleep(0.05)
        return self._recover_after_submit_timeout(device, on_log, deadline)

    def run(
        self,
        device,
        on_log: Optional[Callable[[str], None]] = None,
    ) -> GrabResult:
        log = on_log or (lambda _: None)
        start = time.time()
        deadline = start + self.max_run_seconds

        self._restore_buying_phase()
        self._foreground_state_cache = "unknown"
        self._foreground_checked_at = 0.0
        self._foreground_paused = False

        foreground_state = self._wait_for_safe_foreground(device, log, deadline, force=True)
        if foreground_state == "payment":
            elapsed = (time.time() - start) * 1000
            return GrabResult(success=True, message="检测到支付界面，脚本已停止防误触，请手动完成支付", elapsed_ms=elapsed)
        if foreground_state == "stopped":
            elapsed = (time.time() - start) * 1000
            return GrabResult(success=False, message="用户手动停止", elapsed_ms=elapsed)
        if foreground_state == "timeout":
            elapsed = (time.time() - start) * 1000
            return GrabResult(success=False, message="达到最大运行时长，已停止", elapsed_ms=elapsed)

        round_no = 1
        while not self.should_stop() and time.time() < deadline:
            log(f"Step 1: 疯狂点击购买按钮（第 {round_no} 轮）")
            buy_state = self.click_buy(device, log, deadline)
            if buy_state == "stopped":
                elapsed = (time.time() - start) * 1000
                return GrabResult(success=False, message="用户手动停止", elapsed_ms=elapsed)
            if buy_state == "timeout":
                elapsed = (time.time() - start) * 1000
                return GrabResult(success=False, message="达到最大运行时长，已停止", elapsed_ms=elapsed)
            if buy_state == "soldout":
                elapsed = (time.time() - start) * 1000
                return GrabResult(success=False, message="检测到售罄/暂不可售，已停止", elapsed_ms=elapsed)
            if buy_state == "payment":
                elapsed = (time.time() - start) * 1000
                log(f"检测到支付界面，总耗时 {elapsed:.0f}ms，脚本已停止防误触")
                return GrabResult(success=True, message="检测到支付界面，脚本已停止防误触，请手动完成支付", elapsed_ms=elapsed)
            if buy_state == "submitted":
                log("OpenCV已点击立即提交，继续观察是否进入支付或回流")
                submit_state = self._wait_after_submit(device, log, deadline)
                if submit_state == "success":
                    elapsed = (time.time() - start) * 1000
                    log(f"提交后未检测到回流，总耗时 {elapsed:.0f}ms，请在手机上确认支付状态")
                    return GrabResult(success=True, message="已点击提交，请在手机上确认支付状态", elapsed_ms=elapsed)
                if submit_state == "soldout":
                    elapsed = (time.time() - start) * 1000
                    return GrabResult(success=False, message="检测到售罄/暂不可售，已停止", elapsed_ms=elapsed)
                if submit_state == "stopped":
                    elapsed = (time.time() - start) * 1000
                    return GrabResult(success=False, message="用户手动停止", elapsed_ms=elapsed)
                if submit_state == "timeout":
                    elapsed = (time.time() - start) * 1000
                    return GrabResult(success=False, message="达到最大运行时长，已停止", elapsed_ms=elapsed)
                if submit_state == "order":
                    log("提交后仍在订单页，准备重新提交")
                    buy_state = "order"
                else:
                    log("提交后未确认支付或遇到回流提示，继续回流尝试")
                    round_no += 1
                    continue

            if buy_state != "order":
                round_no += 1
                continue

            buy_elapsed = (time.time() - start) * 1000
            log(f"已进入/仍在订单页 (耗时 {buy_elapsed:.0f}ms) — Step 2: 确认订单")

            if not self.confirm_order(device, log):
                foreground_state = self._wait_for_safe_foreground(device, log, deadline, force=True)
                if foreground_state == "payment":
                    elapsed = (time.time() - start) * 1000
                    log(f"检测到支付界面，总耗时 {elapsed:.0f}ms，脚本已停止防误触")
                    return GrabResult(success=True, message="检测到支付界面，脚本已停止防误触，请手动完成支付", elapsed_ms=elapsed)
                if foreground_state == "stopped":
                    elapsed = (time.time() - start) * 1000
                    return GrabResult(success=False, message="用户手动停止", elapsed_ms=elapsed)
                if foreground_state == "timeout":
                    elapsed = (time.time() - start) * 1000
                    return GrabResult(success=False, message="达到最大运行时长，已停止", elapsed_ms=elapsed)
                log("提交点击被安全门拦截，已回到大麦，重新进入抢票流程")
                round_no += 1
                continue

            submit_state = self._wait_after_submit(device, log, deadline)
            if submit_state == "success":
                elapsed = (time.time() - start) * 1000
                log(f"抢票完成！总耗时 {elapsed:.0f}ms，请在手机上完成支付")
                return GrabResult(success=True, message="抢票成功，请在手机上完成支付", elapsed_ms=elapsed)
            if submit_state == "soldout":
                elapsed = (time.time() - start) * 1000
                return GrabResult(success=False, message="检测到售罄/暂不可售，已停止", elapsed_ms=elapsed)
            if submit_state == "stopped":
                elapsed = (time.time() - start) * 1000
                return GrabResult(success=False, message="用户手动停止", elapsed_ms=elapsed)
            if submit_state == "timeout":
                elapsed = (time.time() - start) * 1000
                return GrabResult(success=False, message="达到最大运行时长，已停止", elapsed_ms=elapsed)
            if submit_state == "order":
                log("提交后仍在订单页，继续回流重新提交")
                round_no += 1
                continue

            log("提交后未确认支付或遇到弹窗/库存提示，继续回流尝试")
            round_no += 1

        elapsed = (time.time() - start) * 1000
        return GrabResult(success=False, message="达到最大运行时长，已停止", elapsed_ms=elapsed)
