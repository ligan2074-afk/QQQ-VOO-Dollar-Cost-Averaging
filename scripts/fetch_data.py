import os
import re
import json
from datetime import datetime, timezone
from pathlib import Path

import requests


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

PE_PAGE_URL = "https://worldperatio.com/index/nasdaq-100/"


def load_json(path: Path, default):
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path: Path, data):
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_world_pe(timeout: int = 20):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }

    resp = requests.get(PE_PAGE_URL, headers=headers, timeout=timeout)
    resp.raise_for_status()
    html = resp.text

    # 优先匹配正文里的描述句：
    # The estimated Price-to-Earnings (P/E) Ratio for Nasdaq 100 Index is 31.36, calculated on ...
    m = re.search(
        r"Price-to-Earnings\s*\(P/E\)\s*Ratio\s*for\s*Nasdaq\s*100\s*Index\s*is\s*([0-9]+(?:\.[0-9]+)?)",
        html,
        re.IGNORECASE,
    )
    if m:
        return float(m.group(1))

    # 退一步：匹配标题区块 “P/E Ratio” 后面的第一个数字
    m = re.search(
        r"P/E\s*Ratio\s*</[^>]+>\s*<[^>]+>\s*([0-9]+(?:\.[0-9]+)?)",
        html,
        re.IGNORECASE,
    )
    if m:
        return float(m.group(1))

    # 再退一步：纯文本粗匹配
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()

    m = re.search(
        r"Nasdaq\s*100\s*Index.*?P/E\s*Ratio.*?([0-9]+(?:\.[0-9]+)?)",
        text,
        re.IGNORECASE,
    )
    if m:
        return float(m.group(1))

    raise ValueError("未能从 worldperatio 页面解析出 PE 数值")


def get_current_pe():
    # 1. 优先抓网页
    try:
        pe = fetch_world_pe()
        print(f"[PE] fetched from worldperatio: {pe}")
        return pe, "worldperatio"
    except Exception as e:
        print(f"[PE] worldperatio failed: {e}")

    # 2. 回退到环境变量 CURRENT_PE
    current_pe = os.getenv("CURRENT_PE", "").strip()
    if current_pe:
        try:
            pe = float(current_pe)
            print(f"[PE] fallback to CURRENT_PE: {pe}")
            return pe, "env"
        except ValueError:
            print(f"[PE] invalid CURRENT_PE: {current_pe}")

    raise RuntimeError("无法获取 PE：网页抓取失败，且 CURRENT_PE 未设置或格式错误")


def update_pe_history():
    pe_history_path = DATA_DIR / "pe_history.json"
    pe_history = load_json(pe_history_path, [])

    pe_value, pe_source = get_current_pe()
    today = datetime.now(timezone.utc).date().isoformat()

    # 如果今天已有记录就覆盖
    found = False
    for item in pe_history:
        if item.get("date") == today:
            item["pe"] = pe_value
            item["source"] = pe_source
            found = True
            break

    if not found:
        pe_history.append(
            {
                "date": today,
                "pe": pe_value,
                "source": pe_source,
            }
        )

    pe_history.sort(key=lambda x: x["date"])
    save_json(pe_history_path, pe_history)
    return pe_value, pe_history


def calc_pe_percentile(current_pe, pe_history):
    values = [float(x["pe"]) for x in pe_history if "pe" in x]
    if not values:
        return 0.5

    less_equal = sum(1 for v in values if v <= current_pe)
    return less_equal / len(values)


if __name__ == "__main__":
    pe_value, pe_history = update_pe_history()
    pe_percentile = calc_pe_percentile(pe_value, pe_history)

    print("current_pe =", pe_value)
    print("pe_percentile =", round(pe_percentile, 4))
