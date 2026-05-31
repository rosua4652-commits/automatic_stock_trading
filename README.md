# AIDI — AI 자동투자 (업비트 KRW)

모의투자는 업비트 시세 기준 시뮬레이션, 실거래는 **업비트만** 지원합니다.

## Windows에서 실행

1. [Python 3.12](https://www.python.org/downloads/) 설치 (PATH 추가, **3.14 사용 금지**)
2. 프로젝트 폴더에서 **`run.bat`** 더블클릭 (첫 실행 시 venv·패키지·프론트 빌드)
3. 브라우저: http://127.0.0.1:8000

### 자주 쓰는 배치

| 파일 | 용도 |
|------|------|
| `run.bat` | 일반 서버 시작 |
| `run-log.bat` | 상세 로그 파일로 서버 시작 |
| `logs-aidi.bat` | 로그 보기·서버 시작 메뉴 |
| `stop-aidi.bat` | 8000 포트 서버 종료 |
| `restart-log.bat` | 로그 모드 서버 재시작 |
| `tail-log.bat` | `logs\aidi-server.log` 실시간 보기 |

`run.bat`와 `run-log.bat`는 **동시에 하나만** 실행하세요 (같은 포트).

## 개발 (핫리로드)

```bash
cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend && npm install && npm run dev
```

## 구조

```
backend/app/     FastAPI + 트레이딩 엔진
frontend/src/    React UI
```

빌드 확인: 서버 실행 후 http://127.0.0.1:8000/api/version 의 `build` 필드
