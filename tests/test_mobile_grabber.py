import time

import pytest

import core.mobile_grabber as mobile_grabber_module
from core.mobile_grabber import MobileGrabber


DAMAI_PACKAGE = "cn.damai"
OTHER_PACKAGE = "com.tencent.mm"
PAYMENT_PACKAGE = "com.eg.android.AlipayGphone"


class FakeClock:
    def __init__(self, now=1000.0):
        self.now = now

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FakeDevice:
    def __init__(self, package=DAMAI_PACKAGE, app_responses=None, window=(1000, 2000)):
        self.package = package
        self.app_responses = list(app_responses or [])
        self.window = window
        self.app_current_calls = 0
        self.shell_calls = []
        self.click_calls = []

    def app_current(self):
        self.app_current_calls += 1
        if self.app_responses:
            response = self.app_responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return {"package": response}
        if isinstance(self.package, Exception):
            raise self.package
        return {"package": self.package}

    def window_size(self):
        return self.window

    def shell(self, command, timeout=None):
        self.shell_calls.append((command, timeout))

    def click(self, x, y):
        self.click_calls.append((x, y))


class TemplateGrabber(MobileGrabber):
    def __init__(self, matches=None, **kwargs):
        templates = {
            "refresh": "refresh",
            "try": "try",
            "submit": "submit",
            "verify_title": "verify_title",
            "verify_slider": "verify_slider",
        }
        super().__init__(opencv_templates=templates, **kwargs)
        self.matches = matches or {}

    def _screenshot_bgr(self, device, on_log=None):
        return object()

    def _opencv_scan_gray(self, screen_bgr):
        return object(), 0, 0

    def _match_template_gray(self, screen_gray, template_path, offset_x=0, offset_y=0):
        return self.matches.get(template_path, (False, 0, 0, 0.0))


@pytest.fixture
def opencv_available(monkeypatch):
    monkeypatch.setattr(mobile_grabber_module, "cv2", object())
    monkeypatch.setattr(mobile_grabber_module, "np", object())


def test_foreground_state_is_throttled(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(mobile_grabber_module.time, "time", clock.time)
    grabber = MobileGrabber(foreground_check_interval=0.2)
    device = FakeDevice(package=DAMAI_PACKAGE)

    assert grabber._read_foreground_state(device) == "damai"
    device.package = OTHER_PACKAGE
    clock.now += 0.1

    assert grabber._read_foreground_state(device) == "damai"
    assert device.app_current_calls == 1

    clock.now += 0.11
    assert grabber._read_foreground_state(device) == "other"
    assert device.app_current_calls == 2


def test_damai_foreground_batches_burst_taps_into_one_shell_command():
    grabber = MobileGrabber()
    device = FakeDevice(package=DAMAI_PACKAGE)

    assert grabber._tap_points(device, [(1, 2), (3, 4), (5, 6)])

    assert device.shell_calls == [("input tap 1 2; input tap 3 4; input tap 5 6", 2.0)]
    assert device.click_calls == []


def test_other_foreground_blocks_taps_and_clears_cached_retry():
    grabber = MobileGrabber()
    grabber._cached_try_point = (10, 20)
    grabber._cached_try_until = time.time() + 10
    device = FakeDevice(package=OTHER_PACKAGE)

    assert not grabber._tap_points(device, [(1, 2)])

    assert device.shell_calls == []
    assert grabber._cached_try_point is None
    assert grabber._cached_try_until == 0.0


def test_wait_for_safe_foreground_auto_resumes(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(mobile_grabber_module.time, "time", clock.time)
    monkeypatch.setattr(mobile_grabber_module.time, "sleep", clock.sleep)
    grabber = MobileGrabber(foreground_check_interval=0.2)
    device = FakeDevice(app_responses=[OTHER_PACKAGE, DAMAI_PACKAGE])
    logs = []

    state = grabber._wait_for_safe_foreground(device, logs.append, deadline=clock.time() + 1)

    assert state == "damai"
    assert any("前台不是大麦" in message for message in logs)
    assert any("恢复自动点击" in message for message in logs)


def test_wait_for_safe_foreground_returns_payment():
    grabber = MobileGrabber()
    device = FakeDevice(package=PAYMENT_PACKAGE)

    assert grabber._wait_for_safe_foreground(device, lambda _: None, deadline=time.time() + 1) == "payment"


def test_foreground_query_exception_pauses_and_resumes(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(mobile_grabber_module.time, "time", clock.time)
    monkeypatch.setattr(mobile_grabber_module.time, "sleep", clock.sleep)
    grabber = MobileGrabber(foreground_check_interval=0.2)
    device = FakeDevice(app_responses=[RuntimeError("adb unavailable"), DAMAI_PACKAGE])
    logs = []

    state = grabber._wait_for_safe_foreground(device, logs.append, deadline=clock.time() + 1)

    assert state == "damai"
    assert any("无法确认前台应用" in message for message in logs)


def test_retry_templates_choose_highest_score_candidate(opencv_available):
    grabber = TemplateGrabber(
        matches={
            "refresh": (True, 100, 900, 0.80),
            "try": (True, 200, 800, 0.95),
        },
    )
    device = FakeDevice(package=DAMAI_PACKAGE)
    logs = []

    state = grabber._handle_opencv_buttons(device, logs.append)

    assert state == "retry"
    assert device.shell_calls == [("input tap 200 800", 2.0)]
    assert any("继续尝试" in message for message in logs)


def test_visual_fast_retry_path_does_not_read_ui_context(opencv_available):
    class NoUiContextGrabber(TemplateGrabber):
        def _is_continue_try_context(self, device):
            raise AssertionError("visual fast path must not read UI text")

    grabber = NoUiContextGrabber(matches={"try": (True, 200, 800, 0.95)})
    grabber._video_enabled_runtime = True
    grabber._flow_phase = "post_submit"
    grabber._submit_armed = False
    device = FakeDevice(package=DAMAI_PACKAGE)

    assert grabber._handle_opencv_buttons(device, lambda _: None) == "retry"
    assert grabber._submit_armed


def test_submit_match_disarms_until_retry_button_rearms(opencv_available):
    grabber = TemplateGrabber(matches={"submit": (True, 300, 1500, 0.96)})
    device = FakeDevice(package=DAMAI_PACKAGE)

    assert grabber._handle_opencv_buttons(device, lambda _: None) == "success"
    assert not grabber._submit_armed
    assert len(device.shell_calls) == 1

    assert grabber._handle_opencv_buttons(device, lambda _: None) == "normal"
    assert len(device.shell_calls) == 1

    grabber.matches = {"try": (True, 200, 800, 0.95)}
    grabber._flow_phase = "post_submit"
    assert grabber._handle_opencv_buttons(device, lambda _: None) == "retry"
    assert grabber._submit_armed


def test_post_submit_visual_fast_mode_does_not_blind_tap_buy_button(monkeypatch):
    monkeypatch.setattr(mobile_grabber_module.time, "sleep", lambda _: None)
    grabber = MobileGrabber(max_retries=3, opencv_start_delay_seconds=10.0)
    grabber._video_enabled_runtime = True
    grabber._flow_phase = "post_submit"
    device = FakeDevice(package=DAMAI_PACKAGE)

    assert grabber.click_buy(device, lambda _: None, deadline=time.time() + 1) == "retry"
    assert device.shell_calls == []


def test_run_initial_foreground_timeout_reports_elapsed(monkeypatch):
    clock = FakeClock(now=0.0)
    monkeypatch.setattr(mobile_grabber_module.time, "time", clock.time)
    monkeypatch.setattr(mobile_grabber_module.time, "sleep", clock.sleep)
    grabber = MobileGrabber(max_run_seconds=0.5, foreground_check_interval=0.2)
    device = FakeDevice(package=OTHER_PACKAGE)

    result = grabber.run(device, lambda _: None)

    assert not result.success
    assert result.message == "达到最大运行时长，已停止"
    assert result.elapsed_ms >= 500
