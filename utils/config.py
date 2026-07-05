import json
import copy
from pathlib import Path
from typing import Any

DEFAULT_CONFIG: dict[str, Any] = {
    "mode": "desktop",
    "chrome_path": "",
    "debug_port": 9222,
    "grab": {
        "max_retries": 40,
        "retry_interval_ms": 50,
        "poll_interval_ms": 50,
        "confirm_timeout_ms": 5000,
    },
    "mobile": {
        "device_serial": "",
        "max_retries": 20,
        "click_interval_ms": 50,
        "confirm_clicks": 10,
        "advance_seconds": 0,
        "max_run_seconds": 180,
        "normal_check_interval": 1.0,
        "fast_check_interval": 0.2,
        "popup_wait_seconds": 0.2,
        "post_submit_check_seconds": 1.0,
        "fallback_popup_taps_enabled": False,
        "fallback_popup_taps": [[0.50, 0.56], [0.50, 0.61]],
        "fallback_popup_after_seconds": 0.45,
        "manual_pause_enabled": True,
        "manual_pause_poll_seconds": 0.2,
        "manual_pause_max_seconds": 45.0,
        "opencv_enabled": True,
        "opencv_threshold": 0.75,
        "opencv_match_scale": 0.6,
        "opencv_scan_interval": 0.2,
        "opencv_refresh_wait_seconds": 0.35,
        "opencv_try_wait_seconds": 0.15,
        "opencv_cached_try_seconds": 6.0,
        "opencv_cached_try_max_taps": 12,
        "opencv_cached_try_verify_every": 3,
        "opencv_start_delay_seconds": 0.3,
        "opencv_roi": [0.0, 0.30, 1.0, 0.98],
        "opencv_templates": {
            "refresh": "btn_refresh.png",
            "try": "btn_try.png",
            "submit": "btn_submit.png",
        },
        "ticket_priority": ["看台880", "内场1080", "内场1380", "内场1680", "看台580", "看台380"],
        "ticket_positions": {
            "看台380": [0.29, 0.44],
            "看台580": [0.29, 0.52],
            "看台880": [0.29, 0.59],
            "内场1080": [0.29, 0.67],
            "内场1380": [0.29, 0.74],
            "内场1680": [0.29, 0.81],
        },
        "ticket_confirm_pos": [0.78, 0.92],
        "ticket_select_wait_seconds": 0.35,
        "connect_retries": 3,
        "connect_retry_delay": 0.5,
    },
    "ntp": {
        "servers": ["ntp.aliyun.com", "ntp.tencent.com", "cn.pool.ntp.org"],
        "timeout_s": 3,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_config(path: Path) -> dict:
    if not path.exists():
        return copy.deepcopy(DEFAULT_CONFIG)
    with open(path, "r", encoding="utf-8") as f:
        user_config = json.load(f)
    return _deep_merge(DEFAULT_CONFIG, user_config)


def save_config(path: Path, config: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
