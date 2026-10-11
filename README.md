# 차트 시그널

일봉·주봉 차트를 기술적 지표로 분석해 **매수 / 매도 방향**을 제안하는 웹앱(PWA)입니다.
종목 코드를 입력하면 yfinance로 최근 180일 실제 시세를 가져와 차트를 그리고 분석합니다.

## 바로 쓰기

- 웹: https://chart-signal.onrender.com
- 안드로이드 APK: [ChartSignal.apk](https://github.com/suin0721/Stock/releases/download/latest/ChartSignal.apk)
- 윈도우: [설치형 ChartSignal-Setup.exe](https://github.com/suin0721/Stock/releases/download/desktop/ChartSignal-Setup.exe) · [설치 없이 실행 ChartSignal-Portable.exe](https://github.com/suin0721/Stock/releases/download/desktop/ChartSignal-Portable.exe)
- 맥: [M1~M4 맥](https://github.com/suin0721/Stock/releases/download/desktop/ChartSignal-mac-arm64.dmg) · [인텔 맥](https://github.com/suin0721/Stock/releases/download/desktop/ChartSignal-mac-x64.dmg)

### 휴대폰에 앱으로 설치
- **아이폰(Safari)**: 서버 주소 열기 → 공유 버튼 → "홈 화면에 추가"
- **안드로이드(Chrome)**: 서버 주소 열기 → 메뉴(⋮) → "앱 설치" 또는 "홈 화면에 추가"

## 사용법
1. 앱 상단 검색창에 **종목명이나 코드**를 입력합니다. 입력하는 동안 후보가 뜨고, 고르면 바로 열립니다.
   - 종목명: `삼성전자`, `코카콜라`, `에코프로`, `apple`
   - 미국 주식 티커: `KO`, `AAPL`, `NVDA` / 한국 주식 6자리 코드: `005930`
2. 데이터 서버가 **yfinance**로 최근 180일 일봉을 가져오고, 주봉은 앱에서 자동으로 만듭니다.
3. **단타 추천 · 차트 분석 · 뉴스 · 관심종목** 탭으로 나뉩니다. **뉴스** 탭에는 해당 종목의 최근 30일 기사가 최신순으로 모입니다 (한국 종목은 Google 뉴스 한국어, 해외 종목은 Yahoo Finance와 Google 뉴스).
4. 오른쪽 위 **☆ 관심종목 추가**를 누르면 관심종목 목록에 담깁니다. 목록에서 종목별 현재가·등락률·최근 30일 흐름·매수/매도 판정을 한눈에 보고, 누르면 해당 종목 차트로 이동합니다. 판정 점수순·등락률순 정렬과 5분 자동 갱신을 지원하며, 목록은 기기에 저장됩니다.
5. 화면이 켜져 있는 동안 1분마다 자동 갱신됩니다. 시세는 Yahoo Finance 기준이며 수 분~20분 지연될 수 있습니다.

## 단타 추천 (2~3일 보유)

**단타 추천** 탭은 장 마감 뒤 시장 전체를 훑어 2~3일 보유에 맞는 후보를 점수순으로 보여줍니다.

- **대상**: 한국은 코스피 시총 상위 150 + 코스닥 상위 100 (보통주, 하루 평균 거래대금 30억 원 이상), 미국은 대형·인기주 100종목
- **신호**
  - **돌파**: 20일 고가를 거래량 1.8배 이상과 함께 넘고 당일 고가 부근에서 마감 (20일선 이격 15% 미만)
  - **눌림목**: 20일선 > 60일선 상승 추세에서 10일 고점 대비 3~12% 눌린 뒤, 거래량이 줄며 반등 양봉
  - **과매도 반등**: 120일선 위 추세에서 RSI(2) 10 미만 단기 급락
- **가격**: 진입 = 신호일 종가, 손절 = 진입 − ATR×1.2, 1차 목표 = 진입 + ATR×1.5, 2차 목표 = 진입 + ATR×2.5, 최대 3거래일 보유
- **과거 성과**: 같은 신호를 최근 1년에 적용해 위 규칙으로 매매했을 때의 평균 수익·수익 마감 비율·손절 비율 (한국 0.23%, 미국 0.05% 비용 차감). 같은 날 손절과 목표가 모두 닿으면 손절로 계산합니다.
- **점수**: 신호 종류, 거래량, 최근 20일 지수 대비 강도, 시장 상태(지수 20일선 위/아래), 과열·이격, 그 종목의 과거 같은 신호 성과를 더해 0~100점
- 스캔 결과는 서버에 15분 동안 저장되고, **다시 스캔**으로 새로 받을 수 있습니다.

## 데이터 서버 (yfinance)

yfinance는 Python 라이브러리라서 휴대폰·브라우저 안에서 직접 실행할 수 없습니다.
그래서 `server/app.py`(Flask + yfinance)가 시세를 받아 JSON으로 넘겨주고, 앱 화면도 함께 제공합니다.

### Render에 무료 배포 (권장)
1. [render.com](https://render.com) 가입 → GitHub 계정 연결
2. **New → Blueprint** → `suin0721/Stock` 선택 → **Apply** (`render.yaml` 설정이 자동 적용됨)
3. 배포가 끝나면 나오는 주소(예: `https://chart-signal.onrender.com`)를 휴대폰에서 열면 바로 앱이 동작합니다.
4. APK나 GitHub Pages에서 쓸 때는 앱 하단 **데이터 서버 설정**에 위 주소를 넣고 저장하세요.

무료 서버는 15분간 요청이 없으면 잠들어서, 처음 열 때 30초~1분 정도 걸릴 수 있습니다.

### 내 PC에서 실행
```bash
pip install -r server/requirements.txt
python server/app.py      # http://localhost:8000
```

### API
- `GET /api/search?q=삼성전자` — 종목명(한글·영어)·코드로 종목 찾기 (네이버 증권 자동완성 + Yahoo 검색)
- `GET /api/news?symbol=005930&name=삼성전자` — 최근 30일 뉴스
- `GET /api/swing?market=KR` — 단타 후보 스캔 (`US`도 가능, `refresh=1`로 새로 스캔). 스캔 중이면 `status: running`과 진행률을 돌려줍니다.
- `GET /api/history?symbol=KO&days=180`
```json
{ "symbol": "KO", "name": "Coca-Cola Company (The)", "currency": "USD",
  "source": "Yahoo Finance (yfinance)", "fetchedAt": "2026-10-10T00:00:00+00:00",
  "bars": [{ "t": "2026-04-13", "o": 70.1, "h": 70.9, "l": 69.8, "c": 70.5, "v": 12345678 }] }
```

## 분석 방식

| 구분 | 비중 | 보는 지표 |
|---|---|---|
| 주봉 (추세) | 60% | 5·10·20주선 배열과 기울기, MACD, RSI(14), 볼린저밴드, 26주 고점·저점 돌파, 거래량 |
| 일봉 (타이밍) | 40% | 5·20·60일선 배열, 골든/데드크로스, RSI 과매수·과매도, MACD, 볼린저밴드, 60일 고점·저점, 거래량 급증 |

두 점수를 합쳐 **강력 매수 · 매수 · 관망 · 매도 · 강력 매도**로 판정하고,
주봉과 일봉 조합에 따른 대응(예: 상승 추세 속 눌림목)과 저항·지지·손절·목표 참고가를 보여줍니다.
손절 참고가는 가까운 지지선에서 ATR(14) 1배를 뺀 값입니다.

## 파일 구성
- `index.html` — 앱 화면 (차트는 Canvas로 직접 그림)
- `server/` — yfinance 데이터 서버 (Flask), `render.yaml` — Render 배포 설정
- `manifest.webmanifest`, `sw.js`, `icons/` — 설치형 앱(PWA) 설정
- `android/` — 안드로이드 APK (WebView), `desktop/` — 윈도우·맥 앱 (Electron). 둘 다 GitHub Actions가 자동 빌드

## 주의
기술적 지표만을 규칙에 따라 점수화한 참고 도구입니다. 실적·뉴스·수급은 반영하지 않으며 투자 권유가 아닙니다.
