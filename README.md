# AIDI — AI 자동투자

설정은 **목표 수익 금액**만. **자동투자 시작** 한 번이면 시장 전체를 스캔해 우량 코인을 고르고, 익절·손절·트레일링 스탑까지 AI가 처리합니다.

> ⚠️ **모의투자**는 업비트 KRW 시세 기준 시뮬레이션입니다. **실거래**는 **업비트만** 지원합니다 (바이낸스 미사용).

## 실행

### Windows

**PC 최종본 폴더** (dongil-3): `pc-path.txt` · **`PC_최종본_설치.txt`** 참고

1. [Python 3.12](https://www.python.org/downloads/) 설치 (PATH 추가) — **3.14 사용 금지**
2. **`sync-pc-from-github.bat`** 로 최신 코드 받기 (또는 GitHub ZIP)
3. **`SETUP_PC.bat`** 또는 **`run.bat`** 더블클릭  
   - 한글 깨짐/명령 오류 나면 **`run.ps1`** (PowerShell) 사용  
   자세한 내용: **`WINDOWS_설치안내.md`**

브라우저: http://localhost:8000  
빌드 확인: `check-build.bat` → `2026-03-30-pc-dongil3-final`

### Mac / Linux

```bash
chmod +x run.sh
./run.sh
```

브라우저: http://localhost:8000

## 개발 (핫리로드)

터미널 1:
```bash
cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

터미널 2:
```bash
cd frontend && npm install && npm run dev
```

## 기능

- 전 시장 USDT 현물 스캔 (거래량·변동성·레버리지 토큰·스테이블 제외)
- EMA / RSI / 모멘텀 기반 점수화 후 상위 코인 자동 매수
- 자동 익절·손절·트레일링 스탑
- 실시간 포트폴리오 · 캔들 차트 · AI 선정 목록
- 설정: 목표 수익(원)만

## 구조

```
backend/app/     FastAPI + 트레이딩 엔진
frontend/src/    React UI + Lightweight Charts
```
