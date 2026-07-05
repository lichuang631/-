# Damai Ticket Grabbing Script

大麦移动端半自动抢票辅助工具。项目主要面向 Android 手机 APP 场景，通过 `uiautomator2` 控制手机点击，并用 OpenCV 模板匹配辅助处理回流按钮。

这个工具的定位不是“保证抢到”，而是把开抢瞬间和回流阶段里重复、机械、容易手慢的操作交给脚本完成；用户仍然需要提前登录、预约、盯着手机，并在支付阶段手动完成付款。

## 当前能力

- NTP 校时，到点启动。
- Android APP 固定坐标高速点击底部购票按钮。
- OpenCV 识别并点击：
  - `努力刷新`
  - `继续尝试`
  - `立即提交`
- `继续尝试` 坐标短时间缓存，减少反复截图识别带来的延迟。
- 检测到验证码/安全验证/滑块等需要人工处理的页面时，暂停自动点击，等待用户手动处理。
- 检测到支付宝/支付界面后停止脚本，避免误触。
- 支持 GUI 启动、手机连接检测、日志复盘。

## 使用前说明

请合理使用。本项目仅用于个人学习、自动化测试和个人辅助操作，不承诺成功率，不绕过平台服务端排队、库存分配、验证码、风控等限制。

不要用于商业倒票或其他违法违规用途。

## 环境要求

- Windows/macOS
- Python 3.9+
- Android 手机
- USB 数据线
- 已开启 USB 调试
- 手机已安装并登录大麦 APP

## 安装

克隆仓库：

```bash
git clone https://gitee.com/lichuang-c/damai-ticket-grabbing-script.git
cd damai-ticket-grabbing-script
```

Windows 推荐直接运行：

```bat
setup.bat
```

也可以手动安装：

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

如果系统没有 ADB，需要安装 Android Platform Tools，并确保 `adb devices` 能看到手机。

## 快速开始

如果你是第一次使用，可以按下面顺序来：

1. 克隆项目并安装依赖。
2. 复制 `config.example.json` 为 `config.json`。
3. 准备三张模板图：`btn_refresh.png`、`btn_try.png`、`btn_submit.png`。
4. 手机打开 USB 调试，用数据线连接电脑。
5. 运行 `python inspect_ui.py`，确认手机能被识别。
6. 运行 `python main.py` 或双击 `start.bat`。
7. 在 GUI 里选择“移动端(APP)”。
8. 点击“连接手机”。
9. 手机打开大麦 APP，提前登录并停在目标演出页面。
10. 设置开票时间，点击“开始抢票”。
11. 全程盯着手机，进入支付界面后手动支付。

建议第一次不要直接实战，可以先设置一个当前时间 +60 秒的测试时间，观察日志和手机点击位置是否正常。

## 配置

首次运行前复制示例配置：

```powershell
Copy-Item config.example.json config.json
```

然后编辑本地 `config.json`。`config.json` 是个人运行配置，默认不会提交到仓库。

重点参数：

| 参数 | 说明 |
| --- | --- |
| `mobile.device_serial` | Android 设备序列号，留空时自动连接默认设备 |
| `mobile.advance_seconds` | 提前点击秒数，当前建议 `0`，避免提前点到“已预约” |
| `mobile.max_retries` | 单轮购票点击循环次数 |
| `mobile.max_run_seconds` | 最大运行时长 |
| `mobile.opencv_match_scale` | OpenCV 降采样匹配比例，默认 `0.6` |
| `mobile.opencv_start_delay_seconds` | 开始后延迟多少秒再启动识别，默认 `0.3` |
| `mobile.opencv_cached_try_seconds` | “继续尝试”坐标缓存有效期 |
| `mobile.opencv_cached_try_max_taps` | 缓存坐标最多连点次数 |
| `mobile.opencv_cached_try_verify_every` | 缓存坐标每点几次后强制截图校验 |
| `mobile.manual_pause_enabled` | 检测到验证页面时是否暂停自动点击，默认开启 |

## 模板图片

移动端 OpenCV 识别需要在项目根目录放置三张按钮模板图：

```text
btn_refresh.png  努力刷新
btn_try.png      继续尝试
btn_submit.png   立即提交
btn_verify_title.png   验证页标题/提示
btn_verify_slider.png  滑块验证区域
```

模板建议：

- 只裁剪按钮主体。
- 不要带太多背景。
- 尽量使用和实战手机同分辨率、同主题下的截图。
- 如果大麦页面样式变化，模板可能需要重新截。

## 启动

Windows：

```bat
start.bat
```

或手动运行：

```bash
python main.py
```

## 推荐实战流程

1. 手机开启 USB 调试。
2. 用数据线连接电脑。
3. 手机弹窗点击“允许 USB 调试”。
4. 打开大麦 APP，登录账号。
5. 进入目标演出详情页。
6. 提前完成预约或选好目标票档。
7. 电脑启动本工具，选择“移动端(APP)”。
8. 点击“连接手机”，确认连接成功。
9. 设置真实开票时间。
10. 点击“开始抢票”。
11. 到点后脚本自动点击底部购票按钮。
12. 遇到“继续尝试/努力刷新”时脚本自动处理。
13. 识别到“立即提交”时脚本自动点击。
14. 进入支付宝/支付界面后脚本停止，用户手动支付。

## 当前移动端逻辑

```text
到点启动
前 0.3 秒只点底部购票坐标
0.3 秒后启动页面识别
识别到继续尝试 -> 点击并缓存坐标
短时间内优先点缓存坐标
每点几次后截图校验
识别到努力刷新 -> 点击并短等待
识别到立即提交 -> 点击并结束
检测到验证码/安全验证 -> 暂停自动点击，等待人工处理后继续
检测到支付界面 -> 停止脚本，交给用户付款
```

## 测试手机连接

可以先运行：

```bash
python inspect_ui.py
```

用于检查手机连接、前台 APP、当前可读取的控件文字。

## 项目结构

```text
├── main.py
├── start.bat
├── setup.bat
├── config.example.json
├── core/
│   ├── timer.py
│   ├── grabber.py
│   └── mobile_grabber.py
├── gui/
│   ├── main_window.py
│   ├── mobile_worker.py
│   └── worker.py
├── utils/
│   └── config.py
└── inspect_ui.py
```

## 注意事项

- 这个工具不能绕过验证码、排队、库存分配和平台风控。
- OpenCV 模板识别依赖页面样式，页面变化后需要重截模板。
- 不建议完全无人值守，最好全程盯着手机，必要时手动介入。
- 支付阶段必须手动完成。

## 问题反馈与协作开发

这个项目目前还在个人实战测试和迭代阶段，很多逻辑会受到手机型号、屏幕分辨率、大麦 APP 版本、页面样式、网络环境的影响。

如果你在使用中发现问题，欢迎反馈：

- 运行日志
- 手机型号和分辨率
- 大麦 APP 版本
- 问题发生时的页面截图
- 你的 `config.json` 中和移动端相关的配置项

如果你有 Python、OpenCV、uiautomator2、Android 自动化方面的经验，也欢迎一起改进。比较需要优化的方向包括：

- 更快的截图/识别链路
- 更稳的模板匹配策略
- 不同分辨率下的坐标适配
- 票档选择逻辑
- 回流弹窗处理
- 日志复盘和测试工具

欢迎提交 Issue 或 Pull Request。请不要提交个人账号信息、真实订单截图、支付截图、设备隐私信息或本地 `config.json`。

也可以添加微信交流：`Aaaa000531`。如果你有更好的思路，或者愿意一起完善这个脚本，欢迎联系交流。

## 免责声明

本项目仅供学习、研究和个人自动化辅助使用。使用者应自行承担使用风险，并遵守相关平台规则和法律法规。请勿用于商业倒票、批量抢票或其他违规用途。
