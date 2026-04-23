#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CONFIG_PATH = DATA_DIR / "config.json"
HISTORY_PATH = DATA_DIR / "history.json"
LATEST_PATH = DATA_DIR / "latest.json"
PE_HISTORY_PATH = DATA_DIR / "pe_history.json"

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
PE_PAGE_URL = "https://worldperatio.com/index/nasdaq-100/"


@dataclass
class SeriesPoint:
    day: str
    value: float


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def save_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def parse_day(text: str) -> date:
    return datetime.strptime(text, "%Y-%m-%d").date()


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def get_grade(total: float, config: dict) -> dict:
    for grade in config["grades"]:
        if total >= grade["min"]:
            return grade
    return config["grades"][-1]


def fred_api_key() -> str:
    value = os.environ.get("FRED_API_KEY", "").strip()
    if not value:
        raise RuntimeError("缺少 FRED_API_KEY。请在 GitHub 仓库 Secrets 里配置它。")
    return value


def fetch_fred_series(series_id: str, start_day: str, end_day: Optional[str] = None) -> List[SeriesPoint]:
    params = {
        "series_id": series_id,
        "api_key": fred_api_key(),
        "file_type": "json",
        "observation_start": start_day,
    }
    if end_day:
        params["observation_end"] = end_day

    response = requests.get(FRED_BASE, params=params, timeout=30)
    response.raise_for_status()
    payload = response.json()

    points: List[SeriesPoint] = []
    for obs in payload.get("observations", []):
        value = obs.get("value")
        if value in (None, ".", ""):
            continue
        points.append(SeriesPoint(day=obs["date"], value=float(value)))
    return points


def rolling_ma(points: List[SeriesPoint], window: int) -> Dict[str, float]:
    result: Dict[str, float] = {}
    values: List[float] = []
    for point in points:
        values.append(point.value)
        if len(values) >= window:
            result[point.day] = sum(values[-window:]) / window
    return result


def build_value_lookup(points: List[SeriesPoint]) -> Dict[str, float]:
    return {point.day: point.value for point in points}


def latest_available_on_or_before(day: str, mapping: Dict[str, float]) -> Optional[float]:
    eligible = [d for d in mapping.keys() if d <= day]
    if not eligible:
        return None
    return mapping[max(eligible)]


def fetch_world_pe(timeout: int = 20) -> float:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }

    response = requests.get(PE_PAGE_URL, headers=headers, timeout=timeout)
    response.raise_for_status()
    html = response.text

    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()

    patterns = [
        r"P/E\s*Ratio\s*for\s*Nasdaq\s*100\s*Index\s*is\s*([0-9]+(?:\.[0-9]+)?)",
        r"Nasdaq\s*100\s*Index.*?P/E\s*Ratio.*?([0-9]+(?:\.[0-9]+)?)",
    ]

    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            pe = float(m.group(1))
            if 5 <= pe <= 100:
                return pe

    raise RuntimeError("未能从 worldperatio 页面解析出有效 PE。")


def normalize_pe_items(raw_payload) -> List[dict]:
    if isinstance(raw_payload, dict):
        raw_items = raw_payload.get("items", [])
    elif isinstance(raw_payload, list):
        raw_items = raw_payload
    else:
        raw_items = []

    clean: List[dict] = []
    for item in raw_items:
        if isinstance(item, dict) and "date" in item and "pe" in item:
            try:
                clean.append({
                    "date": str(item["date"]),
                    "pe": float(item["pe"]),
                })
            except (TypeError, ValueError):
                continue

    clean.sort(key=lambda x: x["date"])
    return clean


def load_pe_history() -> List[dict]:
    payload = load_json(PE_HISTORY_PATH, {"items": []})
    return normalize_pe_items(payload)


def upsert_pe_history(pe_items: List[dict], day: str, pe_value: float) -> List[dict]:
    updated = [item for item in pe_items if item["date"] != day]
    updated.append({"date": day, "pe": float(pe_value)})
    updated.sort(key=lambda x: x["date"])
    return updated


def maybe_update_pe_history_from_env_or_url(latest_market_day: str, pe_items: List[dict]) -> Tuple[List[dict], str]:
    # 1. 优先抓网页
    try:
        web_pe = fetch_world_pe()
        return upsert_pe_history(pe_items, latest_market_day, web_pe), "web:worldperatio"
    except Exception as exc:
        print(f"[PE] worldperatio fetch failed: {exc}")

    # 2. 回退到 CURRENT_PE
    current_pe = os.environ.get("CURRENT_PE", "").strip()
    if current_pe:
        try:
            return upsert_pe_history(pe_items, latest_market_day, float(current_pe)), "env:CURRENT_PE"
        except ValueError:
            raise RuntimeError(f"CURRENT_PE 格式错误：{current_pe}")

    # 3. 再回退到 PE_JSON_URL
    pe_json_url = os.environ.get("PE_JSON_URL", "").strip()
    if pe_json_url:
        response = requests.get(pe_json_url, timeout=30)
        response.raise_for_status()
        payload = response.json()

        pe_value = payload.get("pe")
        if pe_value is None:
            raise RuntimeError("PE_JSON_URL 返回 JSON 里缺少 pe 字段。")

        pe_day = payload.get("date", latest_market_day)
        return upsert_pe_history(pe_items, str(pe_day), float(pe_value)), f"url:{pe_json_url}"

    return pe_items, "file:data/pe_history.json"


def pe_lookup_fill(day: str, pe_items: List[dict]) -> Optional[float]:
    eligible = [item for item in pe_items if item["date"] <= day]
    if not eligible:
        return None
    return float(eligible[-1]["pe"])


def pe_percentile(day: str, pe_value: float, pe_items: List[dict], config: dict) -> float:
    current = parse_day(day)
    window_days = int(config["pe"]["window_trading_days"])
    min_samples = int(config["pe"]["min_samples_for_true_percentile"])
    start_day = current - timedelta(days=window_days * 2)

    subset = [
        float(item["pe"])
        for item in pe_items
        if start_day <= parse_day(item["date"]) <= current
    ]

    if len(subset) >= min_samples:
        subset_sorted = sorted(subset)
        count_le = sum(1 for value in subset_sorted if value <= pe_value)
        return count_le / len(subset_sorted)

    lower = float(config["pe"]["fallback_min"])
    upper = float(config["pe"]["fallback_max"])
    return clamp((pe_value - lower) / (upper - lower), 0.0, 1.0)


def score_record(raw: dict, config: dict) -> dict:
    weights = config["weights"]

    pe_pct = float(raw["pePercentile"])
    bias = float(raw["bias"])

    pe_score = (1 - pe_pct) * float(weights["pe"])
    ma_score = clamp(
        float(weights["ma"]) * (
            1 - abs(bias - float(config["ma"]["target_bias"])) / float(config["ma"]["bias_range"])
        ),
        0.0,
        float(weights["ma"]),
    )
    vix_score = clamp(
        (
            (float(raw["vix"]) - float(config["vol"]["floor"])) /
            (float(config["vol"]["cap"]) - float(config["vol"]["floor"]))
        ) * float(weights["vol"]),
        0.0,
        float(weights["vol"]),
    )
    total = pe_score + ma_score + vix_score
    grade = get_grade(total, config)

    scored = dict(raw)
    scored.update(
        {
            "peScore": round(pe_score, 6),
            "maScore": round(ma_score, 6),
            "vixScore": round(vix_score, 6),
            "total": round(total, 6),
            "gradeLetter": grade["letter"],
            "gradeNote": grade["note"],
        }
    )
    return scored


def build_records(config: dict, price_points: List[SeriesPoint], vol_points: List[SeriesPoint], pe_items: List[dict]) -> List[dict]:
    ma_map = rolling_ma(price_points, int(config["ma"]["window_days"]))
    vol_map = build_value_lookup(vol_points)

    records: List[dict] = []
    for point in price_points:
        ma200 = ma_map.get(point.day)
        if ma200 is None:
            continue

        vol_value = latest_available_on_or_before(point.day, vol_map)
        pe_value = pe_lookup_fill(point.day, pe_items)

        if vol_value is None or pe_value is None:
            continue

        bias = ((point.value - ma200) / ma200) * 100
        pct = pe_percentile(point.day, pe_value, pe_items, config)

        raw = {
            "date": point.day,
            "price": round(point.value, 6),
            "pe": round(float(pe_value), 6),
            "ma200": round(ma200, 6),
            "vix": round(float(vol_value), 6),
            "bias": round(bias, 6),
            "pePercentile": round(float(pct), 6),
        }
        records.append(score_record(raw, config))

    records.sort(key=lambda x: x["date"], reverse=True)
    limit = int(config.get("history_limit", 252))
    return records[:limit]


def main() -> int:
    config = load_json(CONFIG_PATH, None)
    if not config:
        raise RuntimeError("缺少 data/config.json。")

    start_day = os.environ.get("OBS_START", (date.today() - timedelta(days=4200)).isoformat())
    end_day = os.environ.get("OBS_END", date.today().isoformat())

    index_series_id = os.environ.get("NDX_SERIES_ID", config["series"]["index_series_id"])
    vol_series_id = os.environ.get("VOL_SERIES_ID", config["series"]["vol_series_id"])

    print(f"Fetching {index_series_id} and {vol_series_id} ...")
    price_points = fetch_fred_series(index_series_id, start_day, end_day)
    vol_points = fetch_fred_series(vol_series_id, start_day, end_day)

    if not price_points:
        raise RuntimeError("没有拿到指数价格数据。")
    if not vol_points:
        raise RuntimeError("没有拿到波动率数据。")

    latest_market_day = price_points[-1].day
    pe_items = load_pe_history()
    pe_items, pe_source = maybe_update_pe_history_from_env_or_url(latest_market_day, pe_items)

    if not pe_items:
        raise RuntimeError(
            "没有可用的 PE 数据。请至少提供 data/pe_history.json，或者配置 CURRENT_PE / PE_JSON_URL。"
        )

    records = build_records(config, price_points, vol_points, pe_items)
    if not records:
        raise RuntimeError("没有生成任何记录。请检查 PE 历史、价格序列和波动率序列。")

    latest = records[0]
    generated_at = now_iso()

    history_payload = {
        "generated_at": generated_at,
        "mode": "auto",
        "items": records,
    }

    latest_payload = {
        "generated_at": generated_at,
        "as_of": latest["date"],
        "mode": "auto",
        "meta": {
            "index_source": f"FRED:{index_series_id}",
            "vol_source": f"FRED:{vol_series_id}",
            "pe_source": pe_source,
        },
        "record": latest,
    }

    pe_payload = {
        "updated_at": generated_at,
        "items": pe_items,
    }

    save_json(HISTORY_PATH, history_payload)
    save_json(LATEST_PATH, latest_payload)
    save_json(PE_HISTORY_PATH, pe_payload)

    print(f"Generated {len(records)} records. Latest day: {latest['date']}, total score: {latest['total']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise
