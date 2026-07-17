import pytest

import core.run_recorder as run_recorder_module
from core.run_recorder import RunRecorder

np = pytest.importorskip("numpy")


def require_cv2():
    if run_recorder_module.cv2 is None:
        pytest.skip("cv2 is not installed")


def test_record_frame_queues_real_capture_time(monkeypatch, tmp_path):
    require_cv2()
    monkeypatch.setattr(run_recorder_module.time, "time", lambda: 12.5)
    recorder = RunRecorder(tmp_path, enabled=True, fps=10)
    frame = np.zeros((20, 40, 3), dtype=np.uint8)

    recorder.record_frame(frame)

    captured_at, queued_frame = recorder.queue.get_nowait()
    assert captured_at == 12.5
    assert queued_frame is frame


def test_add_time_label_modifies_frame(tmp_path):
    require_cv2()
    recorder = RunRecorder(tmp_path, enabled=True)
    recorder._started_at = 10.0
    frame = np.zeros((80, 200, 3), dtype=np.uint8)

    labeled = recorder._add_time_label(frame.copy(), 12.3)

    assert labeled.shape == frame.shape
    assert np.any(labeled != frame)


def test_add_time_label_swallows_cv_errors(monkeypatch, tmp_path):
    class ExplodingCv2:
        FONT_HERSHEY_SIMPLEX = 0
        LINE_AA = 0

        @staticmethod
        def getTextSize(*args, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(run_recorder_module, "cv2", ExplodingCv2)
    recorder = RunRecorder(tmp_path, enabled=True)
    frame = np.zeros((20, 40, 3), dtype=np.uint8)

    assert recorder._add_time_label(frame, 1.0) is frame


def test_prepare_frame_resizes_to_max_width(tmp_path):
    require_cv2()
    recorder = RunRecorder(tmp_path, enabled=True, max_width=200)
    frame = np.zeros((100, 400, 3), dtype=np.uint8)

    prepared = recorder._prepare_frame(frame)

    assert prepared.shape == (50, 200, 3)
    assert prepared is not frame
