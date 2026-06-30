import random
import time
from typing import Callable, Optional

import uiautomator2 as u2

from core.grabber import GrabResult

_BUY_BUTTON_TEXTS = ["立即抢购", "立即购买", "立即预订", "选座购买", "确定"]

_ORDER_DETECTED_TEXTS = ["提交订单"]

_CONFIRM_BUTTON_TEXTS = ["提交订单", "确认订单"]

_FALLBACK_BUY_POS = (0.75, 0.92)
_FALLBACK_CONFIRM_POS = (0.80, 0.92)


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
    ):
        self.max_retries = max_retries
        self.click_interval_ms = click_interval_ms
        self.confirm_clicks = confirm_clicks

    def _jittered_interval(self) -> float:
        # 给连点间隔加 ±30% 抖动，避免完美的机械节奏被风控标记
        return self.click_interval_ms / 1000 * random.uniform(0.7, 1.3)

    def _jittered_pos(self, w: int, h: int, fx: float, fy: float) -> tuple[int, int]:
        # 坐标兜底点击时落点加几像素随机偏移，避免每次点同一个像素
        jx = int(w * fx) + random.randint(-6, 6)
        jy = int(h * fy) + random.randint(-6, 6)
        return jx, jy

    def click_buy(self, device, on_log: Callable[[str], None]) -> bool:
        w, h = device.window_size()
        for attempt in range(self.max_retries):
            clicked = False
            for text in _BUY_BUTTON_TEXTS:
                btn = device(text=text)
                if btn.exists(timeout=0.3):
                    btn.click()
                    on_log(f"第 {attempt + 1} 次尝试 — 点击了「{text}」")
                    clicked = True
                    break

            if not clicked:
                fx, fy = _FALLBACK_BUY_POS
                bx, by = self._jittered_pos(w, h, fx, fy)
                device.click(bx, by)
                on_log(f"第 {attempt + 1} 次尝试 — 坐标兜底点击 ({fx:.0%}, {fy:.0%})")

            for det_text in _ORDER_DETECTED_TEXTS:
                if device(text=det_text).exists(timeout=0.1):
                    on_log(f"第 {attempt + 1} 次尝试 — 检测到订单页面")
                    return True
            try:
                if device(textContains="¥").exists(timeout=0.1):
                    on_log(f"第 {attempt + 1} 次尝试 — 检测到订单页面")
                    return True
            except TypeError:
                pass

            time.sleep(self._jittered_interval())

        on_log(f"购买按钮点击失败，已尝试 {self.max_retries} 次")
        return False

    def confirm_order(self, device, on_log: Callable[[str], None]) -> bool:
        w, h = device.window_size()

        for text in _CONFIRM_BUTTON_TEXTS:
            btn = device(text=text)
            if btn.exists(timeout=0.3):
                btn.click()
                on_log(f"点击了「{text}」")
                break

        fx, fy = _FALLBACK_CONFIRM_POS
        on_log(f"坐标兜底连点 ({fx:.0%}, {fy:.0%}) × {self.confirm_clicks}")
        for _ in range(self.confirm_clicks):
            cx, cy = self._jittered_pos(w, h, fx, fy)
            device.click(cx, cy)
            time.sleep(self._jittered_interval())

        return True

    def run(
        self,
        device,
        on_log: Optional[Callable[[str], None]] = None,
    ) -> GrabResult:
        log = on_log or (lambda _: None)
        start = time.time()

        log("Step 1: 疯狂点击购买按钮")
        buy_ok = self.click_buy(device, log)
        if not buy_ok:
            elapsed = (time.time() - start) * 1000
            return GrabResult(success=False, message="购买按钮点击失败", elapsed_ms=elapsed)

        buy_elapsed = (time.time() - start) * 1000
        log(f"购买按钮点击成功 (耗时 {buy_elapsed:.0f}ms) — Step 2: 确认订单")

        self.confirm_order(device, log)
        elapsed = (time.time() - start) * 1000
        log(f"抢票完成！总耗时 {elapsed:.0f}ms，请在手机上完成支付")
        return GrabResult(success=True, message="抢票成功，请在手机上完成支付", elapsed_ms=elapsed)
