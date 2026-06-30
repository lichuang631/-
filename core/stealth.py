"""自包含的反检测注入。

不依赖 playwright-stealth（各版本 API 不一致），用一段内联 JS 抹掉最常见的
自动化指纹。通过两条途径生效：

1. add_init_script — 注册到 context，覆盖「点击购买后跳转的订单新页面」等后续导航。
2. evaluate — 对当前已加载完成的页面立即打补丁（init script 对已有文档不生效）。
"""

from typing import Callable, Optional


# 注意：navigator.webdriver 主要靠启动参数 --disable-blink-features=AutomationControlled
# 处理；这里再做一层兜底，并补上 chrome/plugins/languages 等特征。
STEALTH_JS = r"""
(() => {
  try {
    // navigator.webdriver 兜底
    Object.defineProperty(navigator, 'webdriver', {
      get: () => undefined,
    });
  } catch (e) {}

  try {
    // 伪造 chrome 运行时对象（无头/自动化环境常缺失）
    if (!window.chrome) {
      window.chrome = {};
    }
    if (!window.chrome.runtime) {
      window.chrome.runtime = {};
    }
  } catch (e) {}

  try {
    // languages 不应为空
    if (!navigator.languages || navigator.languages.length === 0) {
      Object.defineProperty(navigator, 'languages', {
        get: () => ['zh-CN', 'zh'],
      });
    }
  } catch (e) {}

  try {
    // plugins 长度为 0 是典型的自动化特征
    if (navigator.plugins && navigator.plugins.length === 0) {
      Object.defineProperty(navigator, 'plugins', {
        get: () => [1, 2, 3, 4, 5],
      });
    }
  } catch (e) {}

  try {
    // permissions.query 在自动化环境下行为异常
    const originalQuery = window.navigator.permissions &&
      window.navigator.permissions.query;
    if (originalQuery) {
      window.navigator.permissions.query = (parameters) =>
        parameters && parameters.name === 'notifications'
          ? Promise.resolve({ state: Notification.permission })
          : originalQuery(parameters);
    }
  } catch (e) {}
})();
"""


async def apply_stealth(
    context,
    page,
    on_log: Optional[Callable[[str], None]] = None,
) -> None:
    """对 context 注册 init script，并对当前页面立即注入。

    任一步失败都只记日志、不抛异常 —— 反检测是增强项，不应拖垮抢票主流程。
    """
    log = on_log or (lambda _: None)

    # 1. 覆盖后续导航（如点击购买后跳转的订单页）
    try:
        await context.add_init_script(STEALTH_JS)
    except Exception as e:
        log(f"stealth init script 注册失败（已跳过）: {e}")

    # 2. 对当前已加载的页面立即打补丁
    try:
        await page.evaluate(STEALTH_JS)
        log("stealth 注入完成（当前页 + 后续导航）")
    except Exception as e:
        log(f"stealth 当前页注入失败（已跳过，不影响抢票）: {e}")
