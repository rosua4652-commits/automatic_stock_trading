# AIDI — AI 자동투자 (업비트 KRW)

모의투자는 업비트 시세 기준 시뮬레이션, 실거래는 **업비트만** 지원합니다.

---

## Windows 셋팅 (처음 한 번)

### 1. 필수 프로그램

| 프로그램 | 버전 | 용도 |
|----------|------|------|
| **Python** | **3.12** ([다운로드](https://www.python.org/downloads/)) | 백엔드·서버 (설치 시 **Add to PATH** 체크) |
| **Node.js** | LTS ([다운로드](https://nodejs.org/)) | 첫 실행·빌드 불일치 시 프론트 빌드 (`npm`) |
| **Git** (선택) | ([다운로드](https://git-scm.com/)) | `run.bat`이 GitHub와 자동 `git pull` 하려면 필요 |

- **Python 3.14는 사용하지 마세요.** (`py -3.12 --version` 이 되면 OK)
- Git 없이 ZIP만 써도 됩니다. 이 경우 **코드 업데이트는 ZIP으로 직접** 받아야 합니다.

### 2. 프로젝트 폴더 받기

**방법 A — Git (권장, 자동 업데이트)**

```bat
cd C:\Users\본인계정\Downloads\trading
git clone https://github.com/rosua4652-commits/automatic_stock_trading.git automatic_stock_trading-main
cd automatic_stock_trading-main
```

**방법 B — ZIP**

1. GitHub → **Code** → **Download ZIP**
2. 압축 해제 (예: `C:\Users\...\automatic_stock_trading-main`)
3. **안쪽** 폴더까지 들어가 `backend\app\main.py` 가 보이는 위치가 프로젝트 루트입니다.

### 3. 첫 실행

1. 프로젝트 루트에서 **`run.bat`** 더블클릭  
2. 처음이면 1~5분 걸릴 수 있습니다 (venv, pip, `npm run build`)  
3. 브라우저: **http://127.0.0.1:8000**  
4. 빌드 확인: **http://127.0.0.1:8000/api/version** → `build` 값 (예: `2026-05-31-fast-run-prep`)

콘솔에 `Build … — OK, starting server...` 가 나오면 **셋팅 완료**입니다.

### 4. 상세 로그 모드 (선택)

업비트 버튼·스캔·백테스트 등 **동작 로그**를 파일로 남기려면:

1. **`run-log.bat`** 실행 (일반 `run.bat` 과 **동시에 켜지 마세요**)
2. 로그 보기: **`logs-aidi.bat`** → `1` 실시간 보기  
   또는 **`tail-log.bat`**

로그 파일: `logs\aidi-server.log`

---

## 매일 쓰는 방법

| 하고 싶은 일 | 실행 |
|--------------|------|
| 그냥 서버 켜기 | `run.bat` |
| 로그 남기며 서버 | `run-log.bat` |
| 서버 끄기 | `stop-aidi.bat` 또는 콘솔 `Ctrl+C` |
| 로그만 보기 | `logs-aidi.bat` |

### `run.bat` / `run-log.bat` 이 자동으로 하는 일 (`scripts/aidi-prep`)

시작 전에 아래를 검사합니다.

1. **로컬** `backend/app/main.py` 의 `AIDI_BUILD`
2. **로컬** `frontend/src/uiBuild.ts` 의 `UI_BUILD`
3. **빌드된 UI** `frontend/dist/.aidi-ui-build` 스탬프
4. **GitHub** 최신 `main` 의 빌드 번호 (인터넷 있을 때)

| 결과 | 동작 |
|------|------|
| 전부 일치 + venv·dist 있음 | **pip/npm 생략 → 바로 서버** |
| GitHub가 더 새름 + `.git` 있음 | `git pull` → 필요 시 pip·프론트만 다시 |
| GitHub가 더 새름 + git 없음 | ZIP 덮어쓰라고 안내 후 종료 |
| venv/dist 없음·UI 불일치 | venv·pip·`npm run build` 후 시작 |

**둘 중 하나만** 실행하세요 (`run.bat` 와 `run-log.bat` 은 같은 포트 8000).

---

## 코드 업데이트 (GitHub 맞추기)

### Git 쓰는 경우

```bat
cd 프로젝트폴더
git pull
run.bat
```

`run.bat` 이 pull 을 대신 할 수도 있습니다 (로컬 빌드가 GitHub보다 낮을 때).

### ZIP만 쓰는 경우

1. GitHub에서 **새 ZIP** 받기  
2. **같은 폴더**에 압축 해제해 덮어쓰기 (`backend\data` 설정·모의 잔고는 보통 유지)  
3. **`run.bat`** 실행 → 빌드가 바뀌었으면 프론트 자동 재빌드

---

## 문제 해결

| 증상 | 해결 |
|------|------|
| Python 3.12 없음 | `py -3.12 --version` 확인, 3.12 재설치 |
| `npm not found` | Node.js 설치 후 `run.bat` 다시 |
| 포트 8000 사용 중 | `stop-aidi.bat` 후 재실행 |
| GitHub와 빌드 다름 (git 없음) | ZIP으로 폴더 덮어쓰기 |
| UI가 예전 화면 | `run.bat` 한 번 (prep 이 `npm run build` 함) |
| venv 꼬임 | `backend\.venv` 폴더 삭제 후 `run.bat` |

PowerShell 실행 정책 오류가 나면 **관리자 CMD**에서 한 번:

```bat
powershell -Command "Set-ExecutionPolicy -Scope CurrentUser RemoteSigned"
```

---

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
scripts/         aidi-prep (빌드 검사·빠른 시작)
```
