# PDF to Spreadsheet - 웹 GUI 구현 계획

## 1. 프로젝트 개요

### 1.1 목표
PDF 문서(명단, 영수증, 이수증)를 파싱하여 Excel 또는 Google 스프레드시트로 자동 변환하는 **웹 기반 GUI 도구**

### 1.2 기술 스택
| 구분 | 기술 | 버전 |
|------|------|------|
| **백엔드** | FastAPI | 0.115+ |
| **템플릿** | Jinja2 | 3.1+ |
| **데이터베이스** | SQLite + SQLAlchemy | 2.0+ |
| **인증** | Session 기반 (passlib + bcrypt) | - |
| **PDF 파싱** | pdfplumber | 0.11+ |
| **데이터 처리** | pandas | 2.2+ |
| **Excel 출력** | openpyxl | 3.1+ |
| **컨테이너** | Docker | - |

---

## 2. 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                        사용자 (브라우저)                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Docker Container                             │
│                                                                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │  FastAPI    │───▶│  Parsers    │───▶│  Exporters  │         │
│  │  (웹 서버)  │    │  (PDF 파싱) │    │  (Excel)    │         │
│  └─────────────┘    └─────────────┘    └─────────────┘         │
│         │                                                   │
│         ▼                                                   │
│  ┌─────────────┐    ┌─────────────┐                         │
│  │  SQLite DB  │    │  uploads/   │                         │
│  │  (사용자)   │    │  (임시파일) │                         │
│  └─────────────┘    └─────────────┘                         │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. 페이지 구성

### 3.1 페이지 목록
| 페이지 | 경로 | 설명 | 인증 |
|--------|------|------|------|
| 로그인 | `/login` | 사용자 인증 | 불필요 |
| 회원가입 | `/register` | 신규 사용자 등록 | 불필요 |
| 메인 업로드 | `/` | PDF 파일 업로드 | 필요 |
| 변환 설정 | `/convert/{id}` | 출력 형식 선택, 파서 설정 | 필요 |
| 결과 다운로드 | `/download/{id}` | 변환된 파일 다운로드 | 필요 |
| 변환 이력 | `/history` | 이전 변환 기록 조회 | 필요 |

### 3.2 사용자 흐름

```
로그인 → 메인 업로드 → PDF 업로드 → 변환 설정 → 변환 실행 → 결과 다운로드
  ↑                                                              │
  └────────────────────── 이력에서 재다운로드 ←──────────────────┘
```

---

## 4. 데이터베이스 설계

### 4.1 테이블 구조

#### users 테이블
```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    hashed_password VARCHAR(200) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    is_admin BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### conversions 테이블
```sql
CREATE TABLE conversions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    stored_filename VARCHAR(255) NOT NULL,
    file_size INTEGER,
    pdf_type VARCHAR(50),           -- roster, receipt, certificate
    output_format VARCHAR(20),      -- excel, sheets
    status VARCHAR(20) DEFAULT 'pending',  -- pending, processing, completed, failed
    output_filename VARCHAR(255),
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

---

## 5. API 엔드포인트 설계

### 5.1 페이지 라우트
```python
# 인증 불필요
GET  /login              # 로그인 페이지
POST /login              # 로그인 처리
GET  /register           # 회원가입 페이지
POST /register           # 회원가입 처리
POST /logout             # 로그아웃

# 인증 필요
GET  /                   # 메인 업로드 페이지
POST /upload             # 파일 업로드 처리
GET  /convert/{id}       # 변환 설정 페이지
POST /convert/{id}       # 변환 실행
GET  /download/{id}      # 결과 다운로드
GET  /history            # 변환 이력
```

### 5.2 API 라우트 (JSON)
```python
GET  /api/status/{id}    # 변환 상태 조회 (AJAX)
DELETE /api/file/{id}    # 업로드 파일 삭제
```

---

## 6. 파일 구조

```
pdf-to-spreadsheet/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
│
├── main.py                    # 앱 엔트리포인트 + 라우트
├── config.py                  # 설정 관리
├── database.py                # SQLAlchemy 엔진/세션
├── models.py                  # ORM 모델
├── schemas.py                 # Pydantic 스키마
├── crud.py                    # DB CRUD 함수
├── flash.py                   # Flash 메시지 유틸리티
├── csrf.py                    # CSRF 토큰 관리
│
├── parsers/                   # PDF 파서 모듈
│   ├── __init__.py
│   ├── base.py                # 베이스 파서 클래스
│   ├── roster.py              # 명단 파서
│   ├── receipt.py             # 영수증 파서
│   └── certificate.py         # 이수증 파서
│
├── detectors/                 # PDF 유형 감지
│   ├── __init__.py
│   └── type_detector.py
│
├── exporters/                 # 출력 모듈
│   ├── __init__.py
│   ├── excel.py               # Excel 출력
│   └── google_sheets.py       # Google 스프레드시트 (선택)
│
├── templates/                 # Jinja2 템플릿
│   ├── base.html              # 기본 레이아웃
│   ├── login.html             # 로그인
│   ├── register.html          # 회원가입
│   ├── upload.html            # 메인 업로드
│   ├── convert.html           # 변환 설정
│   ├── downloading.html       # 변환 진행 중
│   ├── result.html            # 결과 페이지
│   └── history.html           # 변환 이력
│
├── static/                    # 정적 파일
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── upload.js          # 파일 업로드 JS
│
├── uploads/                   # 업로드 임시 저장소
├── output/                    # 변환 결과 저장소
└── instance/                  # SQLite DB 저장소
    └── app.db
```

---

## 7. 핵심 기능 상세 설계

### 7.1 파일 업로드 기능
```python
# 업로드 처리 흐름
1. 파일 선택/드래그앤드롭
2. 파일 유형 검증 (PDF만 허용)
3. 파일 크기 검증 (최대 50MB)
4. 파일명 위생 처리 (UUID + 원본 파일명)
5. uploads/ 디렉토리에 저장
6. DB에 변환 레코드 생성 (status: pending)
7. 변환 설정 페이지로 리다이렉트
```

### 7.2 PDF 변환 기능
```python
# 변환 처리 흐름
1. DB에서 변환 레코드 조회
2. PDF 유형 자동 감지 (detectors/type_detector.py)
3. 유형별 파서 선택 및 실행
4. 데이터를 DataFrame으로 변환
5. 출력 형식에 따라 내보내기 (Excel 또는 Google Sheets)
6. output/ 디렉토리에 저장
7. DB 상태 업데이트 (status: completed)
8. 결과 페이지로 리다이렉트
```

### 7.3 실시간 상태 확인 (AJAX)
```javascript
// 3초마다 상태 확인
setInterval(async () => {
    const response = await fetch(`/api/status/${conversionId}`);
    const data = await response.json();
    
    if (data.status === 'completed') {
        // 다운로드 버튼 활성화
        window.location.href = `/download/${conversionId}`;
    } else if (data.status === 'failed') {
        // 에러 메시지 표시
        showError(data.error_message);
    }
}, 3000);
```

---

## 8. Docker 설정

### 8.1 Dockerfile
```dockerfile
FROM python:3.11-slim

# 시스템 의존성 설치
RUN apt-get update && apt-get install -y \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스코드 복사
COPY . .

# 디렉토리 생성
RUN mkdir -p uploads output instance

# 포트 노출
EXPOSE 8000

# 앱 실행
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 8.2 docker-compose.yml
```yaml
version: '3.8'

services:
  pdf2sheet:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./uploads:/app/uploads
      - ./output:/app/output
      - ./instance:/app/instance
    environment:
      - SECRET_KEY=${SECRET_KEY:-your-secret-key-change-in-production}
      - DATABASE_URL=sqlite:///./instance/app.db
    restart: unless-stopped
```

---

## 9. 의존성 파일 (requirements.txt)

```txt
# 웹 프레임워크
fastapi==0.115.0
uvicorn[standard]==0.30.0
jinja2==3.1.4
python-multipart==0.0.9

# 데이터베이스
sqlalchemy==2.0.35
passlib[bcrypt]==1.7.4
itsdangerous==2.2.0

# PDF 처리
pdfplumber==0.11.4
pandas==2.2.2
openpyxl==3.1.5

# 설정 관리
python-dotenv==1.0.1
pydantic==2.9.0
pydantic-settings==2.5.0

# (선택) Google 스프레드시트
# gspread==6.1.4
# google-auth==2.35.0
```

---

## 10. 구현 단계

### Phase 1: 기본 구조 (1일)
- [ ] 프로젝트 디렉토리 생성
- [ ] requirements.txt 작성
- [ ] Dockerfile 작성
- [ ] main.py 기본 구조
- [ ] database.py, models.py 설정

### Phase 2: 인증 시스템 (1일)
- [ ] 사용자 모델 (users 테이블)
- [ ] 로그인/로그아웃 페이지
- [ ] 회원가입 페이지
- [ ] 세션 미들웨어 설정
- [ ] CSRF 보호

### Phase 3: 파일 업로드 (1일)
- [ ] 업로드 페이지 (드래그앤드롭)
- [ ] 파일 검증 (PDF, 크기)
- [ ] uploads/ 저장 처리
- [ ] 변환 레코드 생성

### Phase 4: PDF 변환 (2일)
- [ ] PDF 유형 감지 모듈
- [ ] 명단 파서 (roster.py)
- [ ] 영수증 파서 (receipt.py)
- [ ] 이수증 파서 (certificate.py)
- [ ] Excel 출력 모듈

### Phase 5: 결과 처리 (1일)
- [ ] 변환 상태 API
- [ ] 결과 다운로드 페이지
- [ ] 변환 이력 페이지
- [ ] AJAX 상태 확인

### Phase 6: UI/UX 개선 (1일)
- [ ] 반응형 웹 디자인
- [ ] 프로그레스 바
- [ ] 에러 메시지 처리
- [ ] Flash 메시지

---

## 11. 보안 체크리스트

| 항목 | 구현 방법 |
|------|----------|
| 비밀번호 해싱 | passlib + bcrypt |
| 세션 보안 | SessionMiddleware + 강력한 secret_key |
| CSRF 방어 | 토큰 기반 CSRF 보호 |
| 파일명 위생 | UUID 기반 파일명 생성 |
| 파일 크기 제한 | 서버 측 50MB 제한 |
| XSS 방어 | Jinja2 자동 이스케이핑 |
| SQL Injection | SQLAlchemy ORM 사용 |

---

## 12. 실행 방법

```bash
# 개발 모드
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Docker 실행
docker-compose up --build

# 브라우저에서 접속
http://localhost:8000
```

---

## 13. 향후 확장 계획

1. **Google 스프레드시트 연동** - gspread + OAuth 2.0
2. **OCI Object Storage 연동** - 클라우드 파일 저장
3. **배치 처리** - 여러 PDF 일괄 변환
4. **커스텀 파서** - 사용자 정의 PDF 유형 지원
5. **API 제공** - REST API로 외부 시스템 연동
