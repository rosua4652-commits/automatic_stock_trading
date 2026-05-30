# automatic_stock_trading

업비트 KRW 마켓을 대상으로 한 **AI 보조 단타 분석, 시뮬레이션, 자금/로그 관리, 웹 UI, 안전장치 포함 자동매매 MVP**입니다.

> 주의: 이 프로젝트는 수익을 보장하지 않습니다. 기본 실행 모드는 실거래가 아닌 `paper`입니다. 실거래는 명시적으로 환경변수를 켜고 CLI 확인 플래그를 넣어야만 동작합니다.

## 주요 기능

- 업비트 API 인증/잔고 조회
- KRW 마켓 거래대금 상위 코인 스캔
- RSI, EMA, MACD, Bollinger Band, VWAP, ATR, 거래량 비율 계산
- 거래량 돌파 / 눌림목 반등 중심 단타 신호 점수화
- BTC 급락장 신규 진입 차단
- 수수료/슬리피지를 반영한 기대 순수익 계산
- paper trading 기반 지속 실행 루프
- guarded live trading 구조
- Cursor AI/OpenAI 호환 API를 통한 신호 해석
- 포트폴리오 평가, 자산 비중, 미실현 손익, 스냅샷 저장
- HTML 자금 리포트/그래프 생성
- 웹 UI에서 시작/중단/분석/포트폴리오/로그 확인
- JSONL 로그 기록

## 설치

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

개발/테스트만 할 경우 별도 외부 패키지는 필요 없습니다.

## 빠른 실행

Windows:

```bat
start_dashboard.bat
```

Linux/macOS:

```bash
chmod +x start_dashboard.sh
./start_dashboard.sh
```

스크립트는 `.env`가 없으면 `.env.example`에서 자동 생성하고, 가상환경을 만든 뒤 웹 UI를 실행합니다.

## 환경변수

```bash
cp .env.example .env
```

`.env`에 실제 키를 넣습니다. 실제 키는 절대 커밋하지 마세요.

```env
UPBIT_ACCESS_KEY=...
UPBIT_SECRET_KEY=...
CURSOR_API_KEY=...
AI_ENABLED=true
```

기본 안전 설정:

```env
TRADING_MODE=paper
LIVE_TRADING_ENABLED=false
TOTAL_BUDGET_KRW=50000
MAX_POSITION_KRW=10000
MAX_OPEN_POSITIONS=1
DAILY_LOSS_LIMIT_KRW=1500
TAKE_PROFIT_PCT=1.2
STOP_LOSS_PCT=0.7
TRAILING_STOP_PCT=0.5
TAKER_FEE_PCT=0.05
SLIPPAGE_PCT=0.08
```

## CLI 사용법

API 인증/잔고 조회:

```bash
upbit-scalper accounts
```

단타 후보 분석:

```bash
upbit-scalper scan --limit 10
```

AI 분석 포함:

```bash
upbit-scalper scan --limit 5 --ai
```

특정 코인 간이 백테스트:

```bash
upbit-scalper backtest --market KRW-BTC --unit 5 --count 200
```

포트폴리오 평가 및 스냅샷 저장:

```bash
upbit-scalper portfolio --save
```

자금 현황 HTML 리포트 생성:

```bash
upbit-scalper report
```

중단 전까지 paper mode 지속 실행:

```bash
upbit-scalper run --mode paper --interval 60
```

중단 방법:

- 터미널에서 `Ctrl+C`
- 또는 `data/STOP_BOT` 파일 생성

## 웹 UI

```bash
upbit-scalper web --host 0.0.0.0 --port 8080
```

브라우저에서:

```text
http://localhost:8080
```

UI에서 가능한 작업:

- Paper 지속 실행 시작
- 중단
- 1회 분석/실행
- 후보 분석
- AI 분석
- 자금 현황 저장/조회
- HTML 리포트 생성
- 최근 봇 로그 조회

## 실거래 안전장치

실거래는 기본 비활성화입니다. 활성화하려면 둘 다 필요합니다.

```env
TRADING_MODE=live
LIVE_TRADING_ENABLED=true
```

그리고 단발 실주문은 확인 플래그가 필요합니다.

```bash
upbit-scalper live-once --i-understand-live-risk
```

지속 실행 실거래:

```bash
upbit-scalper run --mode live --interval 60
```

실거래 전에 반드시 다음 순서를 권장합니다.

1. `accounts`로 API 인증 확인
2. `scan`으로 신호 품질 확인
3. `backtest`로 전략 동작 확인
4. `run --mode paper`로 paper trading 로그 축적
5. 소액 실거래

## 로그 파일

```text
logs/scans.jsonl        후보 분석 기록
logs/backtests.jsonl    백테스트 기록
logs/bot_events.jsonl   지속 실행 판단/포지션 기록
logs/live_orders.jsonl  실주문 요청/응답 기록
logs/portfolio.jsonl    자금 현황 스냅샷
logs/errors.jsonl       오류 기록
```

## 전략 개요

현재 MVP는 다음 조건을 점수화합니다.

- 거래량 20봉 평균 대비 증가율
- EMA 5/20/60 정배열
- VWAP 위 가격
- MACD 신호선 상향
- RSI 모멘텀 구간
- 20봉 고점 돌파
- 눌림목 반등
- 과열/추격매수 위험 감점
- BTC 5분봉 급락 시 진입 차단

진입 점수는 기본 80점 이상이며, 손절/익절/트레일링 스탑과 수수료/슬리피지 기준을 통과해야 합니다.
