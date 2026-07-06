import json
import queue
import threading
import time
from pathlib import Path
from typing import Any, Optional

try:
    import cv2
except ImportError:
    cv2 = None


class RunRecorder:
    """异步保存抢票复盘材料：日志、配置快照和识别画面视频。"""

    def __init__(
        self,
        run_dir: Path,
        enabled: bool = True,
        fps: int = 10,
        max_width: int = 720,
        queue_size: int = 60,
    ):
        self.run_dir = run_dir
        self.enabled = enabled and cv2 is not None
        self.fps = max(1, fps)
        self.max_width = max(120, max_width)
        self.queue: queue.Queue = queue.Queue(maxsize=max(1, queue_size))
        self.video_path = self.run_dir / "screen.mp4"
        self.config_path = self.run_dir / "config_snapshot.json"
        self._writer = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._last_frame_at = 0.0
        self._frame_interval = 1.0 / self.fps

    def start(self) -> bool:
        if not self.enabled:
            return False
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._thread = threading.Thread(target=self._write_loop, name="RunRecorder", daemon=True)
        self._thread.start()
        return True

    def save_config_snapshot(self, config: dict[str, Any]) -> None:
        try:
            self.run_dir.mkdir(parents=True, exist_ok=True)
            with self.config_path.open("w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def record_frame(self, frame_bgr) -> None:
        if not self.enabled or frame_bgr is None:
            return
        now = time.time()
        if now - self._last_frame_at < self._frame_interval:
            return
        self._last_frame_at = now

        try:
            frame = self._prepare_frame(frame_bgr)
            self.queue.put_nowait(frame)
        except queue.Full:
            # 复盘录像不能影响抢票速度，队列满了直接丢帧。
            pass
        except Exception:
            pass

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
        try:
            if self._writer:
                self._writer.release()
        except Exception:
            pass
        self._writer = None

    def _prepare_frame(self, frame_bgr):
        height, width = frame_bgr.shape[:2]
        if width > self.max_width:
            scale = self.max_width / width
            frame_bgr = cv2.resize(
                frame_bgr,
                (self.max_width, max(1, int(height * scale))),
                interpolation=cv2.INTER_AREA,
            )
        return frame_bgr.copy()

    def _ensure_writer(self, frame) -> bool:
        if self._writer is not None:
            return True
        height, width = frame.shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self._writer = cv2.VideoWriter(str(self.video_path), fourcc, self.fps, (width, height))
        return bool(self._writer and self._writer.isOpened())

    def _write_loop(self) -> None:
        while not self._stop_event.is_set() or not self.queue.empty():
            try:
                frame = self.queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                if self._ensure_writer(frame):
                    self._writer.write(frame)
            except Exception:
                pass
