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

## 2. 실행 (가장 쉬움)

탐색기에서 프로젝트 폴더 → **`run.bat`** 더블클릭

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

## 4. Python만으로 실행 (run.bat 대신)

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
