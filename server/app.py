"""차트 시그널 데이터 서버.

yfinance로 종목의 최근 N일(기본 180일) 일봉을 가져와 JSON으로 돌려주고,
같은 주소에서 앱 화면(index.html)도 함께 제공합니다.

    pip install -r server/requirements.txt
    python server/app.py            # http://localhost:8000
"""
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yfinance as yf
from flask import Flask, jsonify, request, send_from_directory

ROOT = Path(__file__).resolve().parent.parent
app = Flask(__name__, static_folder=None)

CACHE_SECONDS = 60          # 같은 종목은 1분 동안 캐시 (Yahoo 요청 제한 대비)
_cache: dict = {}


@app.after_request
def cors(resp):
    # APK(파일로 열린 화면)나 GitHub Pages에서도 호출할 수 있도록 허용
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _candidates(symbol: str):
    """6자리 한국 종목코드는 코스피(.KS) → 코스닥(.KQ) 순서로 시도."""
    if re.fullmatch(r"\d{6}", symbol):
        return [symbol + ".KS", symbol + ".KQ"]
    return [symbol]


def _history(ticker: str, days: int):
    start = (datetime.now(timezone.utc) - timedelta(days=days)).date()
    t = yf.Ticker(ticker)
    df = t.history(start=start.isoformat(), interval="1d", auto_adjust=False)
    if df is None or df.empty:
        return None
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    bars = [
        {
            "t": idx.strftime("%Y-%m-%d"),
            "o": round(float(r["Open"]), 4),
            "h": round(float(r["High"]), 4),
            "l": round(float(r["Low"]), 4),
            "c": round(float(r["Close"]), 4),
            "v": int(r["Volume"]) if r["Volume"] == r["Volume"] else 0,
        }
        for idx, r in df.iterrows()
    ]
    name, currency = ticker, None
    try:
        fi = t.fast_info
        currency = fi.get("currency")
    except Exception:
        pass
    try:
        info = t.get_info()
        name = info.get("shortName") or info.get("longName") or ticker
        currency = currency or info.get("currency")
    except Exception:
        pass
    return {"name": name, "currency": currency, "bars": bars}


@app.get("/api/history")
def history():
    symbol = (request.args.get("symbol") or "").strip().upper()
    days = max(30, min(int(request.args.get("days", 180)), 3650))
    if not re.fullmatch(r"[A-Z0-9.\-=^]{1,15}", symbol):
        return jsonify(error="종목 코드를 확인해주세요. 예: KO, AAPL, 005930"), 400

    key = (symbol, days)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return jsonify(hit[1])

    last_err = None
    for ticker in _candidates(symbol):
        try:
            data = _history(ticker, days)
        except Exception as e:  # 네트워크 오류, Yahoo 요청 제한 등
            last_err = str(e)
            continue
        if data and data["bars"]:
            payload = {
                "symbol": ticker,
                "name": data["name"],
                "currency": data["currency"],
                "days": days,
                "source": "Yahoo Finance (yfinance)",
                "fetchedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "bars": data["bars"],
            }
            _cache[key] = (time.time(), payload)
            return jsonify(payload)

    msg = f"'{symbol}' 시세를 찾지 못했습니다. 종목 코드를 확인해주세요."
    if last_err:
        msg = f"Yahoo Finance에서 데이터를 가져오지 못했습니다: {last_err}"
    return jsonify(error=msg), 502


@app.get("/api/health")
def health():
    return jsonify(ok=True)


# 앱 화면과 아이콘 등 정적 파일
@app.get("/")
def index():
    return send_from_directory(ROOT, "index.html")


@app.get("/<path:path>")
def static_files(path):
    if path.split("/")[0] in {"icons"} or path in {"manifest.webmanifest", "sw.js"}:
        return send_from_directory(ROOT, path)
    return ("Not found", 404)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
