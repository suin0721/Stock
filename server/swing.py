"""2~3일 보유 단타(스윙) 후보 스캐너.

유니버스(국내 시가총액 상위 / 미국 대형·인기주)의 1년 일봉을 yfinance로 한 번에 받아
세 가지 신호를 찾고, 같은 신호를 과거 1년에 적용했을 때의 3일 성과도 함께 계산합니다.

  돌파     : 20일 고가를 거래량 급증과 함께 넘고 고가 부근에서 마감
  눌림목   : 상승 추세(20일선 > 60일선) 속 고점 대비 3~12% 눌린 뒤 거래량 줄며 반등 양봉
  과매도   : 120일선 위 추세에서 RSI(2) 10 미만 단기 급락

진입은 신호가 난 날 종가, 손절은 진입 - ATR×1.2, 1차 목표는 진입 + ATR×1.5,
3거래일 안에 둘 다 닿지 않으면 3일째 종가에 정리하는 규칙으로 과거 성과를 셉니다.
"""
import json
import os
import re
import threading
import time
import urllib.request
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yfinance as yf

UA = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36"
CACHE_TTL = 15 * 60
HOLD_DAYS = 3
STOP_ATR, T1_ATR, T2_ATR = 1.2, 1.5, 2.5

SETUPS = {
    "breakout": "돌파",
    "pullback": "눌림목",
    "oversold": "과매도 반등",
}

MARKETS = {
    "KR": {"indexes": [("^KS11", "코스피"), ("^KQ11", "코스닥")], "cost": 0.0023,
           "min_value": 3e9, "min_price": 1000, "currency": "KRW"},
    "US": {"indexes": [("^GSPC", "S&P 500"), ("^IXIC", "나스닥")], "cost": 0.0005,
           "min_value": 3e7, "min_price": 5, "currency": "USD"},
}

# 네이버 순위를 못 받을 때 쓰는 국내 대표 종목 (코드, 이름, 시장)
KR_FALLBACK = [
    ("005930", "삼성전자", "KS"), ("000660", "SK하이닉스", "KS"), ("373220", "LG에너지솔루션", "KS"),
    ("207940", "삼성바이오로직스", "KS"), ("005380", "현대차", "KS"), ("000270", "기아", "KS"),
    ("068270", "셀트리온", "KS"), ("005490", "POSCO홀딩스", "KS"), ("035420", "NAVER", "KS"),
    ("051910", "LG화학", "KS"), ("006400", "삼성SDI", "KS"), ("105560", "KB금융", "KS"),
    ("055550", "신한지주", "KS"), ("012330", "현대모비스", "KS"), ("035720", "카카오", "KS"),
    ("028260", "삼성물산", "KS"), ("066570", "LG전자", "KS"), ("003670", "포스코퓨처엠", "KS"),
    ("096770", "SK이노베이션", "KS"), ("034730", "SK", "KS"), ("015760", "한국전력", "KS"),
    ("032830", "삼성생명", "KS"), ("086790", "하나금융지주", "KS"), ("012450", "한화에어로스페이스", "KS"),
    ("329180", "HD현대중공업", "KS"), ("009540", "HD한국조선해양", "KS"), ("010130", "고려아연", "KS"),
    ("011200", "HMM", "KS"), ("017670", "SK텔레콤", "KS"), ("030200", "KT", "KS"),
    ("018260", "삼성에스디에스", "KS"), ("033780", "KT&G", "KS"), ("003550", "LG", "KS"),
    ("316140", "우리금융지주", "KS"), ("009150", "삼성전기", "KS"), ("010950", "S-Oil", "KS"),
    ("047050", "포스코인터내셔널", "KS"), ("042660", "한화오션", "KS"), ("034020", "두산에너빌리티", "KS"),
    ("064350", "현대로템", "KS"), ("272210", "한화시스템", "KS"), ("079550", "LIG넥스원", "KS"),
    ("267260", "HD현대일렉트릭", "KS"), ("010140", "삼성중공업", "KS"), ("000810", "삼성화재", "KS"),
    ("024110", "기업은행", "KS"), ("138040", "메리츠금융지주", "KS"), ("259960", "크래프톤", "KS"),
    ("036570", "엔씨소프트", "KS"), ("352820", "하이브", "KS"), ("090430", "아모레퍼시픽", "KS"),
    ("097950", "CJ제일제당", "KS"), ("011170", "롯데케미칼", "KS"), ("004020", "현대제철", "KS"),
    ("000100", "유한양행", "KS"), ("128940", "한미약품", "KS"), ("326030", "SK바이오팜", "KS"),
    ("006800", "미래에셋증권", "KS"), ("071050", "한국금융지주", "KS"), ("016360", "삼성증권", "KS"),
    ("039490", "키움증권", "KS"), ("323410", "카카오뱅크", "KS"), ("377300", "카카오페이", "KS"),
    ("251270", "넷마블", "KS"), ("011070", "LG이노텍", "KS"), ("000880", "한화", "KS"),
    ("009830", "한화솔루션", "KS"), ("042700", "한미반도체", "KS"), ("298040", "효성중공업", "KS"),
    ("010120", "LS ELECTRIC", "KS"), ("006260", "LS", "KS"), ("001440", "대한전선", "KS"),
    ("103140", "풍산", "KS"), ("047810", "한국항공우주", "KS"), ("003490", "대한항공", "KS"),
    ("271560", "오리온", "KS"), ("004370", "농심", "KS"), ("021240", "코웨이", "KS"),
    ("161390", "한국타이어앤테크놀로지", "KS"), ("000720", "현대건설", "KS"), ("028050", "삼성E&A", "KS"),
    ("241560", "두산밥캣", "KS"), ("454910", "두산로보틱스", "KS"), ("450080", "에코프로머티", "KS"),
    ("005830", "DB손해보험", "KS"), ("066970", "엘앤에프", "KS"), ("036460", "한국가스공사", "KS"),
    ("247540", "에코프로비엠", "KQ"), ("086520", "에코프로", "KQ"), ("196170", "알테오젠", "KQ"),
    ("028300", "HLB", "KQ"), ("263750", "펄어비스", "KQ"), ("293490", "카카오게임즈", "KQ"),
    ("041510", "에스엠", "KQ"), ("035900", "JYP Ent.", "KQ"), ("122870", "와이지엔터테인먼트", "KQ"),
    ("357780", "솔브레인", "KQ"), ("240810", "원익IPS", "KQ"), ("039030", "이오테크닉스", "KQ"),
    ("058470", "리노공업", "KQ"), ("145020", "휴젤", "KQ"), ("214150", "클래시스", "KQ"),
    ("141080", "리가켐바이오", "KQ"), ("087010", "펩트론", "KQ"), ("277810", "레인보우로보틱스", "KQ"),
    ("112040", "위메이드", "KQ"), ("078600", "대주전자재료", "KQ"), ("095340", "ISC", "KQ"),
    ("403870", "HPSP", "KQ"), ("036930", "주성엔지니어링", "KQ"), ("214450", "파마리서치", "KQ"),
    ("000250", "삼천당제약", "KQ"), ("348370", "엔켐", "KQ"), ("298380", "에이비엘바이오", "KQ"),
    ("237690", "에스티팜", "KQ"), ("222800", "심텍", "KQ"), ("005290", "동진쎄미켐", "KQ"),
    ("084370", "유진테크", "KQ"), ("108490", "로보티즈", "KQ"), ("067310", "하나마이크론", "KQ"),
    ("310210", "보로노이", "KQ"), ("064760", "티씨케이", "KQ"), ("950160", "코오롱티슈진", "KQ"),
]

US_UNIVERSE = [
    ("AAPL", "애플"), ("MSFT", "마이크로소프트"), ("NVDA", "엔비디아"), ("AMZN", "아마존"), ("GOOGL", "알파벳"),
    ("META", "메타"), ("TSLA", "테슬라"), ("AVGO", "브로드컴"), ("AMD", "AMD"), ("NFLX", "넷플릭스"),
    ("COST", "코스트코"), ("JPM", "JP모건"), ("V", "비자"), ("MA", "마스터카드"), ("UNH", "유나이티드헬스"),
    ("LLY", "일라이릴리"), ("XOM", "엑슨모빌"), ("ORCL", "오라클"), ("CRM", "세일즈포스"), ("ADBE", "어도비"),
    ("INTC", "인텔"), ("QCOM", "퀄컴"), ("MU", "마이크론"), ("AMAT", "어플라이드머티리얼즈"), ("LRCX", "램리서치"),
    ("KLAC", "KLA"), ("TXN", "텍사스인스트루먼트"), ("ASML", "ASML"), ("TSM", "TSMC"), ("PLTR", "팔란티어"),
    ("COIN", "코인베이스"), ("MSTR", "마이크로스트래티지"), ("SMCI", "슈퍼마이크로"), ("ARM", "ARM"), ("UBER", "우버"),
    ("ABNB", "에어비앤비"), ("SHOP", "쇼피파이"), ("SNOW", "스노우플레이크"), ("CRWD", "크라우드스트라이크"),
    ("PANW", "팔로알토"), ("NET", "클라우드플레어"), ("DDOG", "데이터독"), ("ZS", "지스케일러"), ("MDB", "몽고DB"),
    ("PYPL", "페이팔"), ("SOFI", "소파이"), ("HOOD", "로빈후드"), ("RIVN", "리비안"), ("NIO", "니오"),
    ("BABA", "알리바바"), ("PDD", "PDD"), ("BA", "보잉"), ("CAT", "캐터필러"), ("GE", "GE에어로스페이스"),
    ("GS", "골드만삭스"), ("MS", "모건스탠리"), ("BAC", "뱅크오브아메리카"), ("WFC", "웰스파고"), ("KO", "코카콜라"),
    ("PEP", "펩시코"), ("MCD", "맥도날드"), ("WMT", "월마트"), ("HD", "홈디포"), ("NKE", "나이키"),
    ("SBUX", "스타벅스"), ("DIS", "디즈니"), ("PFE", "화이자"), ("MRK", "머크"), ("ABBV", "애브비"),
    ("JNJ", "존슨앤존슨"), ("AMGN", "암젠"), ("MRNA", "모더나"), ("CVX", "셰브론"), ("OXY", "옥시덴탈"),
    ("F", "포드"), ("GM", "GM"), ("DAL", "델타항공"), ("UAL", "유나이티드항공"), ("CCL", "카니발"),
    ("MARA", "마라홀딩스"), ("RIOT", "라이엇플랫폼"), ("IONQ", "아이온큐"), ("RKLB", "로켓랩"), ("RBLX", "로블록스"),
    ("DKNG", "드래프트킹스"), ("CVNA", "카바나"), ("APP", "앱러빈"), ("AFRM", "어펌"), ("VRT", "버티브"),
    ("ANET", "아리스타"), ("DELL", "델"), ("ON", "온세미"), ("MRVL", "마벨"), ("WDC", "웨스턴디지털"),
    ("CEG", "컨스텔레이션에너지"), ("VST", "비스트라"), ("OKLO", "오클로"), ("SNAP", "스냅"), ("LULU", "룰루레몬"),
]


def _get(url, timeout=8):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://m.stock.naver.com/"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _naver_rank(market, count):
    """네이버 증권 시가총액 순위 (보통주만)."""
    out, page = [], 1
    while len(out) < count and page <= 4:
        url = f"https://m.stock.naver.com/api/stocks/marketValue/{market}?page={page}&pageSize=100"
        data = json.loads(_get(url).decode("utf-8"))
        found = []

        def walk(x):
            if isinstance(x, dict):
                if "itemCode" in x:
                    found.append(x)
                else:
                    for v in x.values():
                        walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)

        walk(data)
        if not found:
            break
        for it in found:
            code = str(it.get("itemCode") or "")
            name = it.get("stockName") or it.get("itemName") or code
            end = (it.get("stockEndType") or "stock").lower()
            if not re.fullmatch(r"\d{5}0", code) or end not in ("stock",):
                continue  # 우선주·ETF·스팩 등 제외
            if re.search(r"스팩|ETN|ETF|리츠", name):
                continue
            out.append((code, name, "KS" if market == "KOSPI" else "KQ"))
        page += 1
    return out[:count]


def universe(market):
    if market == "US":
        return [(s, n, s) for s, n in US_UNIVERSE], "미국 대형·인기주 %d종목" % len(US_UNIVERSE)
    try:
        kr = _naver_rank("KOSPI", 150) + _naver_rank("KOSDAQ", 100)
        if len(kr) >= 80:
            seen, uniq = set(), []
            for c, n, m in kr:
                if c not in seen:
                    seen.add(c)
                    uniq.append((c, n, f"{c}.{m}"))
            return uniq, f"코스피 시총 상위 150 + 코스닥 상위 100 (보통주 {len(uniq)}종목)"
    except Exception:
        pass
    return [(c, n, f"{c}.{m}") for c, n, m in KR_FALLBACK], f"국내 대표 {len(KR_FALLBACK)}종목"


def _download(tickers, progress=None):
    frames = {}
    chunks = [tickers[i:i + 50] for i in range(0, len(tickers), 50)]
    for k, chunk in enumerate(chunks):
        df = None
        for attempt in range(2):
            try:
                df = yf.download(chunk, period="1y", interval="1d", group_by="ticker", auto_adjust=False,
                                 threads=True, progress=False)
                break
            except Exception:
                time.sleep(2)
        if df is not None and not df.empty:
            multi = isinstance(df.columns, pd.MultiIndex)
            level0 = set(df.columns.get_level_values(0)) if multi else set()
            for t in chunk:
                if multi and t in level0:
                    sub = df[t]
                elif not multi and len(chunk) == 1:
                    sub = df
                else:
                    continue
                sub = sub.dropna(subset=["Open", "High", "Low", "Close"])
                if len(sub) >= 130:
                    frames[t] = sub
        if progress:
            progress(min(len(tickers), (k + 1) * 50), len(tickers))
    return frames


# ---------------- 지표 ----------------
def _sma(x, n):
    return pd.Series(x).rolling(n).mean().values


def _shift(x, k):
    out = np.full_like(x, np.nan, dtype=float)
    out[k:] = x[:-k]
    return out


def _rsi(c, n):
    d = np.diff(c, prepend=c[0])
    au = pd.Series(np.clip(d, 0, None)).ewm(alpha=1 / n, adjust=False).mean().values
    ad = pd.Series(np.clip(-d, 0, None)).ewm(alpha=1 / n, adjust=False).mean().values
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = np.where(ad > 0, au / ad, np.inf)
    return 100 - 100 / (1 + rs)


def _atr(h, l, c, n=14):
    pc = _shift(c, 1)
    tr = np.nanmax(np.vstack([h - l, np.abs(h - pc), np.abs(l - pc)]), axis=0)
    return pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().values


def _features(df):
    o, h, l, c, v = (df[k].to_numpy(dtype=float) for k in ("Open", "High", "Low", "Close", "Volume"))
    v = np.nan_to_num(v)
    f = dict(o=o, h=h, l=l, c=c, v=v)
    f["ma5"], f["ma10"], f["ma20"], f["ma60"], f["ma120"] = (_sma(c, n) for n in (5, 10, 20, 60, 120))
    f["atr"] = _atr(h, l, c)
    f["rsi14"], f["rsi2"] = _rsi(c, 14), _rsi(c, 2)
    f["vol20p"] = _shift(_sma(v, 20), 1)
    f["vol3"] = _sma(v, 3)
    f["hi20p"] = _shift(pd.Series(h).rolling(20).max().values, 1)
    f["hi10"] = pd.Series(h).rolling(10).max().values
    f["low3"] = pd.Series(l).rolling(3).min().values
    f["tv20"] = _sma(c * v, 20)
    rng = h - l
    f["pos"] = np.where(rng > 0, (c - l) / np.where(rng > 0, rng, 1), 0.5)
    f["chg"] = c / _shift(c, 1) - 1
    f["dates"] = [d.strftime("%Y-%m-%d") for d in df.index]
    return f


def _signals(f):
    c, o = f["c"], f["o"]
    with np.errstate(invalid="ignore", divide="ignore"):
        trend = (f["ma20"] > f["ma60"]) & (f["ma20"] > _shift(f["ma20"], 5))
        breakout = ((c > f["hi20p"]) & (f["v"] >= 1.8 * f["vol20p"]) & (f["pos"] >= 0.6) & (c > f["ma20"])
                    & (f["ma20"] > f["ma60"]) & (c / f["ma20"] - 1 < 0.15) & (f["chg"] > 0.02) & (f["chg"] < 0.15))
        off = c / f["hi10"]
        pullback = (trend & (f["low3"] <= f["ma10"] * 1.01) & (c > f["ma20"]) & (off >= 0.88) & (off <= 0.97)
                    & (f["vol3"] < f["vol20p"] * 0.9) & (c > o) & (c > _shift(c, 1))
                    & (f["rsi14"] >= 40) & (f["rsi14"] <= 62))
        oversold = (f["rsi2"] < 10) & (c > f["ma120"]) & (f["ma60"] > f["ma120"])
    return {"breakout": np.nan_to_num(breakout).astype(bool),
            "pullback": np.nan_to_num(pullback).astype(bool),
            "oversold": np.nan_to_num(oversold).astype(bool)}


def _simulate(f, i, cost):
    """i일 종가 진입 → 3거래일 동안 손절/1차 목표/시간 정리."""
    c, h, l = f["c"], f["h"], f["l"]
    entry, a = c[i], f["atr"][i]
    stop, t1 = entry - STOP_ATR * a, entry + T1_ATR * a
    for j in range(1, HOLD_DAYS + 1):
        if l[i + j] <= stop:          # 같은 날 둘 다 닿으면 손절로 (보수적으로)
            return stop / entry - 1 - cost, "stop"
        if h[i + j] >= t1:
            return t1 / entry - 1 - cost, "target"
    return c[i + HOLD_DAYS] / entry - 1 - cost, "time"


def _index_state(f, name):
    c, ma20, ma60 = f["c"], f["ma20"], f["ma60"]
    n = len(c) - 1
    above = c[n] > ma20[n]
    rising = ma20[n] > ma20[n - 5]
    if above and rising:
        mood, label = 1, "양호"
    elif above or rising:
        mood, label = 0, "보통"
    else:
        mood, label = -1, "주의"
    return {"name": name, "close": round(float(c[n]), 2), "chg": round(float(f["chg"][n] * 100), 2),
            "ma20": round(float(ma20[n]), 2), "aboveMa20": bool(above), "ma20Rising": bool(rising),
            "ret20": round(float((c[n] / c[n - 20] - 1) * 100), 2), "mood": mood, "label": label}


def _fmt(x):
    return f"{x:,.0f}" if x >= 1000 else f"{x:,.2f}"


def scan(market="KR", progress=None):
    cfg = MARKETS[market]
    uni, uni_label = universe(market)
    idx_tickers = [t for t, _ in cfg["indexes"]]
    frames = _download(idx_tickers + [t for _, _, t in uni], progress)

    indexes = []
    idx_feat = {}
    for t, name in cfg["indexes"]:
        if t in frames:
            f = _features(frames[t])
            idx_feat[t] = f
            indexes.append(_index_state(f, name))
    mood = min([i["mood"] for i in indexes], default=0)

    stats = {k: {"signals": 0, "wins": 0, "targets": 0, "stops": 0, "sum": 0.0} for k in SETUPS}
    items = []
    scanned = 0
    asof = None
    for code, name, t in uni:
        if t not in frames:
            continue
        f = _features(frames[t])
        n = len(f["c"]) - 1
        scanned += 1
        asof = max(asof or f["dates"][n], f["dates"][n])
        sig = _signals(f)
        liquid = (f["tv20"] >= cfg["min_value"]) & (f["c"] >= cfg["min_price"])

        # 과거 성과 (최근 1년, 120일선이 생긴 뒤부터)
        own = {}
        for k, s in sig.items():
            idxs = np.where(s[120:n - HOLD_DAYS + 1] & liquid[120:n - HOLD_DAYS + 1])[0] + 120
            last = -99
            for i in idxs:
                if i - last < HOLD_DAYS:   # 보유 중 중복 신호 제외
                    continue
                last = i
                r, how = _simulate(f, i, cfg["cost"])
                r = float(r)
                st = stats[k]
                st["signals"] += 1
                st["sum"] += r
                st["wins"] += int(r > 0)
                st["targets"] += int(how == "target")
                st["stops"] += int(how == "stop")
                o = own.setdefault(k, [0, 0])
                o[0] += 1
                o[1] += int(r > 0)

        # 오늘 신호
        today = [k for k, s in sig.items() if s[n]]
        if not today or not liquid[n]:
            continue
        c, a = f["c"][n], f["atr"][n]
        ref = idx_feat.get("^KQ11" if t.endswith(".KQ") else idx_tickers[0])
        rs = None
        if ref is not None and len(ref["c"]) > 20:
            rs = ((c / f["c"][n - 20]) / (ref["c"][-1] / ref["c"][-21]) - 1) * 100

        score = max({"breakout": 58, "pullback": 56, "oversold": 50}[k] for k in today) + 5 * (len(today) - 1)
        reasons, cautions = [], []
        if "breakout" in today:
            vr = f["v"][n] / f["vol20p"][n]
            score += min(12, (vr - 1.8) * 6)
            reasons.append(f"20일 고가 {_fmt(f['hi20p'][n])} 돌파, 거래량 평소의 {vr:.1f}배")
            reasons.append(f"당일 고가 부근에서 마감 (일중 위치 {f['pos'][n] * 100:.0f}%)")
        if "pullback" in today:
            off = (1 - c / f["hi10"][n]) * 100
            reasons.append(f"상승 추세(20일선>60일선) 속 고점 대비 {off:.1f}% 눌린 뒤 반등 양봉")
            reasons.append(f"눌림 구간 거래량 감소 (평소의 {f['vol3'][n] / f['vol20p'][n]:.1f}배)")
        if "oversold" in today:
            reasons.append(f"RSI(2) {f['rsi2'][n]:.0f}: 단기 급락, 120일선 위 추세는 유지")
            score += 6 if f["rsi2"][n] < 5 else 0
        if rs is not None:
            score += max(-10, min(10, rs / 2))
            if rs >= 3:
                reasons.append(f"최근 20일 지수보다 {rs:.1f}%p 강함")
            elif rs <= -5:
                cautions.append(f"최근 20일 지수보다 {abs(rs):.1f}%p 약함")
        ext = (c / f["ma20"][n] - 1) * 100
        if ext > 10:
            score -= 8
            cautions.append(f"20일선과 {ext:.0f}% 벌어져 추격 부담")
        if f["rsi14"][n] > 75:
            score -= 5
            cautions.append(f"RSI(14) {f['rsi14'][n]:.0f} 과열")
        score += {1: 8, 0: 0, -1: -12}[mood]
        hist = [own[k] for k in today if k in own]
        hn = sum(h[0] for h in hist)
        hw = sum(h[1] for h in hist)
        if hn >= 3:
            score += 5 if hw / hn >= 0.6 else (-5 if hw / hn < 0.4 else 0)
        score = int(round(max(0, min(100, score))))

        stop, t1, t2 = c - STOP_ATR * a, c + T1_ATR * a, c + T2_ATR * a
        items.append({
            "code": code, "symbol": t, "name": name, "setups": today,
            "setupNames": [SETUPS[k] for k in today], "score": score,
            "close": round(float(c), 4), "chg": round(float(f["chg"][n] * 100), 2),
            "entry": round(float(c), 4), "stop": round(float(stop), 4),
            "target1": round(float(t1), 4), "target2": round(float(t2), 4),
            "stopPct": round(float((stop / c - 1) * 100), 2), "t1Pct": round(float((t1 / c - 1) * 100), 2),
            "t2Pct": round(float((t2 / c - 1) * 100), 2), "atrPct": round(float(a / c * 100), 2),
            "rsi14": round(float(f["rsi14"][n]), 1), "volRatio": round(float(f["v"][n] / f["vol20p"][n]), 2),
            "valueAvg": float(f["tv20"][n]), "date": f["dates"][n],
            "reasons": reasons, "cautions": cautions,
            "history": {"signals": int(hn), "wins": int(hw)},
            "spark": [round(float(x), 4) for x in f["c"][-30:]],
        })

    items.sort(key=lambda x: (-x["score"], -x["valueAvg"]))
    setup_stats = []
    for k, st in stats.items():
        n_ = st["signals"]
        setup_stats.append({
            "key": k, "name": SETUPS[k], "signals": n_,
            "winRate": round(st["wins"] / n_ * 100, 1) if n_ else None,
            "targetRate": round(st["targets"] / n_ * 100, 1) if n_ else None,
            "stopRate": round(st["stops"] / n_ * 100, 1) if n_ else None,
            "avgRet": round(st["sum"] / n_ * 100, 2) if n_ else None,
        })
    return {
        "market": market, "currency": cfg["currency"], "asof": asof,
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "universe": uni_label, "scanned": scanned, "indexes": indexes, "mood": mood,
        "rules": {"holdDays": HOLD_DAYS, "stopAtr": STOP_ATR, "t1Atr": T1_ATR, "t2Atr": T2_ATR,
                  "costPct": round(cfg["cost"] * 100, 2)},
        "setupStats": setup_stats, "items": items[:20], "total": len(items),
    }


# ---------------- 백그라운드 스캔 + 캐시 ----------------
_state = {}
_lock = threading.Lock()
CACHE_DIR = os.environ.get("SWING_CACHE_DIR", "/tmp")


def _cache_path(market):
    return os.path.join(CACHE_DIR, f"swing_{market}.json")


def _run(market):
    st = _state[market]

    def prog(done, total):
        st["progress"] = [done, total]

    try:
        res = scan(market, prog)
        st.update(result=res, at=time.time(), status="done", error=None)
        try:
            with open(_cache_path(market), "w", encoding="utf-8") as fp:
                json.dump({"at": st["at"], "result": res}, fp, ensure_ascii=False)
        except Exception:
            pass
    except Exception as e:
        st.update(status="error", error=str(e))


def get(market, refresh=False):
    with _lock:
        st = _state.setdefault(market, {"status": "idle", "result": None, "at": 0, "progress": [0, 0], "error": None})
        if st["result"] is None:
            try:
                with open(_cache_path(market), encoding="utf-8") as fp:
                    saved = json.load(fp)
                st.update(result=saved["result"], at=saved["at"], status="done")
            except Exception:
                pass
        age = time.time() - st["at"] if st["result"] else None
        stale = st["result"] is None or age > CACHE_TTL or (refresh and age > 120)
        if stale and st["status"] != "running":
            st.update(status="running", progress=[0, 0], error=None)
            threading.Thread(target=_run, args=(market,), daemon=True).start()
        return {"status": st["status"], "progress": st["progress"], "error": st["error"],
                "ageSeconds": int(age) if age is not None else None, "result": st["result"]}
