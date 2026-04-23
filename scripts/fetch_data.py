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
   
