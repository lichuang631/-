import xml.etree.ElementTree as ET

import uiautomator2 as u2


def main():
    device = u2.connect()
    print("device:", device.info.get("productName", "?"), device.window_size())
    print("app:", device.app_current())

    root = ET.fromstring(device.dump_hierarchy())
    texts = []
    for node in root.iter("node"):
        text = (node.attrib.get("text") or "").strip()
        if text and text not in texts:
            texts.append(text)

    print("可读文字数量:", len(texts))
    for text in texts[:160]:
        print("-", text)

    print("--- 关键字测试 ---")
    keys = [
        "预约抢票",
        "立即购买",
        "提交订单",
        "立即提交",
        "继续尝试",
        "返回重新选购",
        "我知道了",
        "库存不足",
        "抢票人数太多",
        "缺货登记",
        "暂不可售",
    ]
    for key in keys:
        ok = device(text=key).exists(timeout=0.02) or device(textContains=key).exists(timeout=0.02)
        print(f"{key}: {ok}")


if __name__ == "__main__":
    main()
