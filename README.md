# Data Verification Tool (데이터 검증 도구)

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.68%2B-green)
![Pandas](https://img.shields.io/badge/Pandas-Data%20Analysis-orange)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

## 📖 개요 (Overview)

**Data Verification Tool**은 원본 데이터와 대조본 데이터(Excel, CSV, TXT)를 비교하여 정합성을 검증하는 기업용(Enterprise) 웹 애플리케이션입니다.

두 개의 데이터 파일을 업로드하여 자동으로 비교 분석하고, 불일치 내역을 시각적으로 제공하며, 결과 보고서를 엑셀 파일로 생성해줍니다.

## ✨ 주요 기능 (Key Features)

### 1. 📊 대시보드 (Dashboard)
- **파일 비교:** 원본(Source)과 대조본(Target) 엑셀파일 시
- **실시간 분석:** 전체 건수, 일치, 불일치, 누락 건수 요약 카드 제공.
- **데이터 미리보기:** 불일치(Mismatch) 항목을 우선적으로 웹에서 바로 확인.
- **결과 내보내기:** 검증 결과가 하이라이팅(Yellow/Red)된 엑셀 파일 다운로드.

### 2. 🕒 검증 이력 (History)
- 과거 수행한 모든 검증 작업의 이력 자동 저장.
- 언제든 과거 결과 리포트 재다운로드 가능.
- 날짜, 파일명, 결과 요약 정보 조회.

### 3. ⚙️ 설정 (Settings)
- **칼럼 매핑:** 비교할 데이터 칼럼(Source/Target)을 유동적으로 설정 가능.
- **사용자 관리 (Admin):** 관리자 권한으로 사용자 계정 생성 및 관리.

### 4. 🔒 보안 (Security)
- **인증:** JWT 기반 로그인 시스템.
- **권한:** 일반 사용자(User)와 관리자(Admin) 권한 분리.
- **암호화:** 비밀번호 Bcrypt 해싱 저장.

---

## 🛠 기술 스택 (Tech Stack)

- **Backend:** Python, FastAPI
- **Database:** SQLite (SQLAlchemy ORM)
- **Data Processing:** Pandas, Openpyxl
- **Frontend:** Jinja2 Templates, TailwindCSS (CDN), Axios

---

## 🚀 설치 및 실행 (Installation & Run)

### 1. 저장소 클론 (Clone)
```bash
git clone https://github.com/davidleearchives-dotcom/DataIntegrityChecker.git
cd DataIntegrityChecker
```

### 2. 가상환경 설정 (Optional)
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Mac/Linux
source venv/bin/activate
```

### 3. 의존성 패키지 설치
```bash
pip install -r requirements.txt
```

### 4. 애플리케이션 실행
```bash
python run.py
```
서버가 시작되면 브라우저에서 `http://localhost:8000` 으로 접속합니다.

---

## 🔑 초기 계정 정보 (Default Credentials)

최초 실행 시 자동으로 생성되는 관리자 계정입니다.

- **ID:** `admin`
- **Password:** `!admin12345`

> ⚠️ 로그인 후 설정 페이지에서 비밀번호를 변경하는 것을 권장합니다.

---

## 📂 프로젝트 구조 (Project Structure)

```text
DataIntegrityChecker/
├── app/
│   ├── main.py            # 애플리케이션 진입점
│   ├── models.py          # DB 모델 정의
│   ├── auth.py            # 인증 로직
│   ├── routers/           # API 라우터 (Dashboard, History, Settings)
│   ├── services/          # 비즈니스 로직 (비교 알고리즘, 데이터 처리)
│   └── templates/         # HTML 템플릿
├── uploads/               # 업로드 파일 임시 저장소
├── results/               # 결과 파일 저장소
├── bms.db                 # SQLite 데이터베이스
├── requirements.txt       # 라이브러리 목록
└── run.py                 # 실행 스크립트
```

## � 업데이트 로그 (Update Log)

### 2026-01-13
- **데이터 비교 로직 개선:**
  - 기존: 중복된 키(Key)가 있는 행을 삭제하여 일부 데이터(약 40건)만 비교되는 현상 수정.
  - 변경: `groupby.cumcount()`를 사용하여 중복 키를 가진 행들도 순차적으로 매칭되도록 개선 (전체 9470개 행 비교 가능).
- **데이터 전처리 강화:**
  - 모든 데이터를 문자열(String)로 변환하여 타입 불일치로 인한 오류 방지.
  - 데이터 앞뒤의 공백(Whitespace) 제거 로직 추가 (`strip()`).
  - `NaN` (결측치) 값을 빈 문자열(`""`)로 치환하여 비교 정확도 향상.
- **헤더 제외 로직 확인:**
  - 첫 번째 행(Header)은 비교에서 제외하고, 두 번째 행부터 데이터 비교가 수행되도록 로직 유지 및 검증.

---

## �� 라이선스 (License)

This project is licensed under the MIT License.
