"""차트 시그널 데이터 서버.

- /api/history : yfinance로 최근 N일(기본 180일) 일봉
- /api/search  : 종목명(한글·영어) 또는 코드로 종목 찾기 (네이버 자동완성 + Yahoo 검색)
- /api/news    : 종목 최근 뉴스 (Yahoo Finance 뉴스 + Google 뉴스)
- /api/quotes  : 여러 종목 현재가 한 번에 (보유종목 탭)
- /api/swing   : 2~3일 단타 후보 스캔 (돌파·눌림목·과매도 반등 + 과거 1년 신호 성과)
같은 주소에서 앱 화면(index.html)도 함께 제공합니다.

    pip install -r server/requirements.txt
    python server/app.py            # http://localhost:8000
"""
import json
import os
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf
from flask import Flask, jsonify, request, send_from_directory

import swing

ROOT = Path(__file__).resolve().parent.parent
app = Flask(__name__, static_folder=None)

CACHE_SECONDS = 60          # 같은 종목은 1분 동안 캐시 (Yahoo 요청 제한 대비)
_cache: dict = {}
UA = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36"
HANGUL = re.compile(r"[\uac00-\ud7a3]")


def _cached(key, seconds, fn):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < seconds:
        return hit[1]
    val = fn()
    _cache[key] = (time.time(), val)
    return val


def _get(url, timeout=8):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


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
            name_ko = None
            if ticker.endswith((".KS", ".KQ")):
                try:
                    name_ko = _naver_name(ticker[:6])
                except Exception:
                    pass
            payload = {
                "symbol": ticker,
                "name": name_ko or data["name"],
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


# ---------------- 종목 검색 ----------------
_NAVER_US = {"NYSE", "NASDAQ", "AMEX", "NYSEARCA", "NYSE ARCA", "NYSEAMERICAN", "BATS"}


def _naver_search(q):
    """네이버 증권 자동완성: 한글 종목명(삼성전자, 코카콜라)으로 국내·미국 종목 검색."""
    url = "https://ac.stock.naver.com/ac?" + urllib.parse.urlencode({"q": q, "target": "stock,index,etf"})
    data = json.loads(_get(url, timeout=5).decode("utf-8"))
    out = []
    for it in data.get("items", []):
        if isinstance(it, list):          # 예전 형식 방어
            continue
        code = str(it.get("code") or "").strip()
        nation = (it.get("nationCode") or "").upper()
        typ = (it.get("typeCode") or "").upper()
        name = it.get("name") or code
        if nation == "KOR" and re.fullmatch(r"\d{6}|[0-9A-Z]{6}", code):
            sym = code + (".KQ" if "KOSDAQ" in typ else ".KS")
            market = it.get("typeName") or ("코스닥" if "KOSDAQ" in typ else "코스피")
        elif nation == "USA" and code:
            sym = code.split(".")[0].replace("/", "-")
            market = it.get("typeName") or typ or "미국"
        else:
            continue
        out.append({"symbol": sym, "code": sym.replace(".KS", "").replace(".KQ", ""), "name": name,
                    "market": market, "nation": nation})
    return out


def _naver_name(code):
    def fn():
        for it in _naver_search(code):
            if it["code"] == code:
                return it["name"]
        return None
    return _cached(("naver_name", code), 86400, fn)


def _yahoo_search(q):
    out = []
    try:
        quotes = yf.Search(q, max_results=8, news_count=0).quotes
    except Exception:
        url = "https://query2.finance.yahoo.com/v1/finance/search?" + urllib.parse.urlencode(
            {"q": q, "quotesCount": 8, "newsCount": 0})
        quotes = json.loads(_get(url, timeout=6)).get("quotes", [])
    for it in quotes:
        sym = it.get("symbol")
        if not sym or it.get("quoteType") not in (None, "EQUITY", "ETF", "INDEX", "MUTUALFUND"):
            continue
        out.append({"symbol": sym, "code": re.sub(r"\.(KS|KQ)$", "", sym),
                    "name": it.get("shortname") or it.get("longname") or sym,
                    "market": it.get("exchDisp") or it.get("exchange") or "",
                    "nation": "KOR" if sym.endswith((".KS", ".KQ")) else ""})
    return out


@app.get("/api/search")
def search():
    q = (request.args.get("q") or "").strip()[:40]
    if not q:
        return jsonify(items=[])

    def fn():
        items, seen, errors = [], set(), []
        sources = [_naver_search, _yahoo_search] if HANGUL.search(q) or q.isdigit() else [_yahoo_search, _naver_search]
        for src in sources:
            try:
                for it in src(q):
                    if it["symbol"] not in seen:
                        seen.add(it["symbol"])
                        items.append(it)
            except Exception as e:
                errors.append(f"{src.__name__}: {e}")
        return {"query": q, "items": items[:12], "errors": errors}

    return jsonify(_cached(("search", q.lower()), 600, fn))


# ---------------- 뉴스 ----------------
def _yahoo_news(ticker):
    out = []
    for it in (yf.Ticker(ticker).news or [])[:20]:
        c = it.get("content") if isinstance(it.get("content"), dict) else None
        if c:   # yfinance 0.2.48 이후 형식
            url = ((c.get("clickThroughUrl") or {}).get("url") or (c.get("canonicalUrl") or {}).get("url"))
            t = c.get("pubDate") or c.get("displayTime")
            out.append({"title": c.get("title"), "summary": c.get("summary") or "",
                        "source": (c.get("provider") or {}).get("displayName") or "Yahoo Finance",
                        "url": url, "time": t})
        else:   # 예전 형식
            ts = it.get("providerPublishTime")
            out.append({"title": it.get("title"), "summary": "", "source": it.get("publisher") or "Yahoo Finance",
                        "url": it.get("link"),
                        "time": datetime.fromtimestamp(ts, timezone.utc).isoformat() if ts else None})
    return [n for n in out if n["title"] and n["url"]]


def _google_news(query, lang="ko"):
    loc = {"ko": ("ko", "KR", "KR:ko"), "en": ("en-US", "US", "US:en")}[lang]
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": query + " when:30d", "hl": loc[0], "gl": loc[1], "ceid": loc[2]})
    root = ET.fromstring(_get(url))
    out = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        src = (item.findtext("source") or "").strip()
        if src and title.endswith(" - " + src):
            title = title[: -len(src) - 3]
        try:
            t = parsedate_to_datetime(item.findtext("pubDate")).astimezone(timezone.utc).isoformat()
        except Exception:
            t = None
        out.append({"title": title, "summary": "", "source": src or "Google 뉴스",
                    "url": item.findtext("link"), "time": t})
        if len(out) >= 20:
            break
    return out


def _clean_en(name):
    n = re.sub(r"\s*\(The\)", "", name).strip()
    for _ in range(3):
        n = re.sub(r",?\s+(Inc|Corp|Corporation|Co|Ltd|plc|PLC|Company|Holdings|Group|Incorporated|N\.V|S\.A|AG|SE)\.?$", "", n).strip()
    return n or name


def _norm_time(t):
    try:
        return datetime.fromisoformat(str(t).replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)


@app.get("/api/news")
def news():
    symbol = (request.args.get("symbol") or "").strip().upper()
    name = (request.args.get("name") or "").strip()[:60]
    if not re.fullmatch(r"[A-Z0-9.\-=^]{1,15}", symbol):
        return jsonify(error="종목 코드를 확인해주세요."), 400

    def fn():
        is_kr = bool(re.fullmatch(r"\d{6}(\.(KS|KQ))?", symbol))
        code = symbol[:6] if is_kr else symbol
        ko_name = name if HANGUL.search(name) else None
        if not ko_name:
            try:
                ko_name = _naver_name(code)
            except Exception:
                pass
        items, errors = [], []
        jobs = []
        if ko_name:
            jobs.append(("google-ko", lambda: _google_news(f'"{ko_name}"', "ko")))
        if not is_kr:
            jobs.append(("yahoo", lambda: _yahoo_news(symbol)))
            en = _clean_en(name) if name and not HANGUL.search(name) else None
            jobs.append(("google-en", lambda: _google_news(f'"{en}"' if en else f"{symbol} stock", "en")))
        elif not ko_name:
            jobs.append(("yahoo", lambda: _yahoo_news(_candidates(code)[0])))
        for label, job in jobs:
            try:
                items += job()
            except Exception as e:
                errors.append(f"{label}: {e}")
        seen, uniq = set(), []
        for n in sorted(items, key=lambda n: _norm_time(n["time"]), reverse=True):
            k = re.sub(r"\W+", "", n["title"].lower())[:60]
            if k in seen:
                continue
            seen.add(k)
            uniq.append(n)
        return {"symbol": symbol, "query": ko_name or name or symbol, "items": uniq[:25], "errors": errors,
                "fetchedAt": datetime.now(timezone.utc).isoformat(timespec="seconds")}

    return jsonify(_cached(("news", symbol, name), 300, fn))


# ---------------- 현재가 여러 개 ----------------
EXTRA_NAMES = {"VOO": "뱅가드 S&P500", "SPY": "SPDR S&P500", "IVV": "아이셰어즈 S&P500", "VTI": "뱅가드 미국 전체",
               "QQQ": "인베스코 나스닥100", "QQQM": "인베스코 나스닥100", "SCHD": "슈왑 배당", "DIA": "다우존스",
               "SOXL": "반도체 3배 레버리지", "TQQQ": "나스닥 3배 레버리지", "UPRO": "S&P500 3배 레버리지",
               "SOXX": "반도체 ETF", "SMH": "반도체 ETF", "MAGS": "매그니피센트7 ETF", "SQQQ": "나스닥 3배 인버스"}


def _name_for(sym, ticker):
    if ticker.endswith((".KS", ".KQ")):
        try:
            return _naver_name(ticker[:6])
        except Exception:
            return None
    if sym in EXTRA_NAMES:
        return EXTRA_NAMES[sym]
    for s_, n_ in swing.US_UNIVERSE + swing.M7:
        if s_ == sym:
            return n_
    return None


@app.get("/api/quotes")
def quotes():
    syms = []
    for s_ in (request.args.get("symbols") or "").split(","):
        s_ = s_.strip().upper()
        if re.fullmatch(r"[A-Z0-9.\-]{1,12}", s_) and s_ not in syms:
            syms.append(s_)
    syms = syms[:40]
    if not syms:
        return jsonify(quotes={})

    def fn():
        mapping, tickers = {}, []
        for s_ in syms:
            mapping[s_] = _candidates(s_)
            tickers += mapping[s_]
        df = yf.download(tickers, period="5d", interval="1d", group_by="ticker", auto_adjust=False,
                         threads=True, progress=False)
        multi = isinstance(df.columns, pd.MultiIndex)
        level0 = set(df.columns.get_level_values(0)) if multi else set()
        out = {}
        for s_, ts in mapping.items():
            for t in ts:
                if multi and t in level0:
                    sub = df[t]
                elif not multi and len(tickers) == 1:
                    sub = df
                else:
                    continue
                sub = sub.dropna(subset=["Close"])
                if sub.empty:
                    continue
                c = float(sub["Close"].iloc[-1])
                p = float(sub["Close"].iloc[-2]) if len(sub) > 1 else c
                out[s_] = {"symbol": t, "name": _name_for(s_, t), "price": round(c, 4), "prev": round(p, 4),
                           "chg": round((c / p - 1) * 100, 2), "date": sub.index[-1].strftime("%Y-%m-%d"),
                           "currency": "KRW" if t.endswith((".KS", ".KQ")) else "USD"}
                break
        return {"quotes": out, "fetchedAt": datetime.now(timezone.utc).isoformat(timespec="seconds")}

    return jsonify(_cached(("quotes", tuple(sorted(syms))), 60, fn))


@app.get("/api/swing")
def swing_scan():
    market = (request.args.get("market") or "KR").upper()
    if market not in swing.MARKETS:
        return jsonify(error="market은 KR 또는 US만 됩니다."), 400
    return jsonify(swing.get(market, refresh=request.args.get("refresh") == "1"))


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
