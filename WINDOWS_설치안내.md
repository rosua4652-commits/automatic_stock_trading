# AIDI — Windows 설치·실행

## 1. 준비 (한 번만)

1. **Python 3.12** (권장) 또는 **3.11**  
   https://www.python.org/downloads/  
   설치 시 **「Add python.exe to PATH」** 반드시 체크  

   > ⚠️ **Python 3.14는 안 됩니다.**  
   > `pydantic-core` 설치 실패 (PyO3가 3.14 미지원)  
   > `python --version` 이 3.14면 **3.12 새로 설치** 후 아래 venv 삭제

2. **Node.js 18+** (소스에서 빌드할 때만)  
   https://nodejs.org/  
   `aidi-samsung-tablet.zip` 처럼 **dist가 포함된 zip** 이면 Node 없어도 됨

3. 프로젝트 받기  
   - GitHub ZIP 다운로드 후 압축 해제  
   - 또는 `git clone` 후 폴더로 이동  

**dongil-3 PC 공식 폴더** (`pc-path.txt`):

```text
C:\Users\dongil-3\Downloads\automatic_stock_trading-main (3)\automatic_stock_trading-main
```

## 2. 실행 (가장 쉬움)

1. **`sync-pc-from-github.bat`** (최신 코드)  
2. 탐색기에서 **`SETUP_PC.bat`** 또는 **`run.bat`** 더블클릭

**`run.bat`에서 한글 깨지고 `'꼍'`, `'npmfail'` 같은 오류가 나면**  
→ **`run.ps1`** 사용 (아래 PowerShell 방법)

또는 **cmd**:

```cmd
cd C:\경로\automatic_stock_trading
run.bat
```

### PowerShell (run.bat 오류 시 권장)

```powershell
cd C:\경로\automatic_stock_trading
powershell -ExecutionPolicy Bypass -File run.ps1
```

브라우저: **http://127.0.0.1:8000**

## 3. 태블릿에서 같은 PC 서버 보기

1. PC에서 `run.bat` 실행 유지  
2. PC IP 확인 (cmd):

```cmd
ipconfig
```

`IPv4 주소` 예: `192.168.0.10`

3. 태블릿(같은 Wi‑Fi) 브라우저:

```
http://192.168.0.10:8000
```

Windows 방화벽 팝업이 뜨면 **허용**.

## 4. 로그 (파일 저장·실시간 보기)

| 파일 | 용도 |
|------|------|
| **`logs-aidi.bat`** | 메뉴 — 실시간 tail, 메모장, 폴더 열기, 로그 비우기 |
| **`run-log.bat`** | 서버 실행 + `logs\aidi-server.log` 에 저장 (화면에도 출력) |
| **`tail-log.bat`** | 실시간 로그만 바로 보기 |
| **`restart-log.bat`** | 기존 서버 종료 후 로그 모드로 재시작 |
| **`stop-aidi.bat`** | 포트 8000 사용 중인 서버만 종료 |

`run-log.bat` 이 바로 꺼지면 → **`run.bat` 창이 이미 켜져 있음** (포트 충돌). `stop-aidi.bat` 실행 후 `run-log.bat` 다시.

- 메인 로그: `logs\aidi-server.log`
- 날짜별: `logs\aidi-YYYY-MM-DD.log`
- 일반 실행(`run.bat`)은 콘솔만 — 파일 로그는 `run-log.bat` 사용

**세부 로그 (`run-log.bat` / `logs-aidi.bat` 1번)**  
`GET /api/chart` 같은 차트 폴링은 생략되고, 아래처럼 **버튼·처리·백테스트** 위주로 기록됩니다.

```text
2026-05-31 12:00:01 | AIDI | INFO | [분석 시작] 성공 · 처리 중… (120ms)
2026-05-31 12:00:02 | AIDI | INFO | [시장 스캔] 시작 — 종목·진입점수·투자 제안 갱신
2026-05-31 12:00:15 | AIDI | INFO | [시장 스캔] 완료 · [모의] 분석 80종 · 제안 5건 …
2026-05-31 12:04:00 | AIDI | INFO | [백테스트 주기] 시작 · 손익절 기준 6.0%/12.0%
2026-05-31 12:04:12 | AIDI | INFO | [백테스트 배치] BTC, ETH, XRP …
2026-05-31 12:04:20 | AIDI | INFO | [롱 분석 버튼] 성공 · HTTP 200 (3500ms)
```

## 5. Python만으로 실행 (run.bat 대신)

```cmd
cd C:\경로\automatic_stock_trading
python run.py
```

(`frontend\dist` 없으면 Node로 `cd frontend && npm install && npm run build` 필요)

## 5. 자주 나는 오류

| 증상 | 해결 |
|------|------|
| `python` 인식 안 됨 | Python 재설치 + PATH 체크, cmd 새로 열기 |
| `npm` 인식 안 됨 | Node 설치 또는 dist 포함 zip 사용 |
| `frontend\dist 없음` | `run.bat`이 npm 빌드 시도 / Node 설치 |
| `pydantic-core` / Python 3.14 오류 | **Python 3.12** 설치 → `rmdir /s /q backend\.venv` → `run.bat` 다시 |
| `'l'` / `'exist'` 명령 오류, 경로 없음 | **안쪽 프로젝트 폴더**에서 실행 / 최신 ZIP / **`SETUP_PC.bat`** 또는 **`run.ps1`** |
| `run.bat` 한글 깨짐·이상한 명령 오류 | **`run.ps1`** 사용 |
| 태블릿에서 접속 안 됨 | 같은 Wi‑Fi, 방화벽 허용, PC IP 확인 |

## 6. 개발 모드 (선택)

터미널 1:

```cmd
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

터미널 2:

```cmd
cd frontend
npm install
npm run dev
```

---

**Termux(삼성 탭)** 는 `TERMUX_권한해결.txt` 참고.
