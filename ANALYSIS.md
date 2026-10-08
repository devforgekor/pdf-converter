# KUHWA Portal - 전체 코드베이스 분석 (2026-09-19)

## 10개 영역별 이슈 요약

### 1. 인증/인가 (main.py)
- CSRF 미들웨어가 pass-through (실제 검증 없음)
- user_id 하드코딩 (0 또는 1)
- Google OAuth 토큰 미저장 → 시트 동기화 불가
- 세션 고정 공격 취약

### 2. DB 모델 (models.py)
- FK에 인덱스 없음
- SafetyEducation/SchoolEducation 구조 동일 → 통합 가능
- ondelete 미설정 → User 삭제 시 고아 레코드

### 3. 템플릿 학습 (layout_analyzer.py)
- learn으로 생성한 parsing_patterns이 auto_parse에서 미사용
- FIELD_LABELS 하드코딩
- 단일 페이지 가정

### 4. 배치 처리 (batch.py)
- 병렬 구조(Semaphore)가 있지만 순차 실행
- BatchJob 결과 미업데이트
- BatchUploadManager 전역 인스턴스 → 메모리 오염

### 5. 정규화기 (normalizers/)
- base.py의 institution 파라미터 미사용
- Azure 전용 라벨 매핑 하드코딩
- LABEL_KEYWORDS 불일치

### 6. 파서 레지스트리 (parsers/)
- RosterParser/ReceiptParser 모듈 부재 → ImportError
- AzureDIParser의 pdf_bytes 의존 → BaseParser 계약 위반
- confidence 미사용

### 7. 저장소 (storage.py)
- 대용량 파일 스트리밍 미지원
- PAR 만료시간 불일치 (24h vs 1h)
- delete_file 에러 무시

### 8. Google 연동 (sheets_integration.py)
- Google 토큰 미저장 → 연동 불가
- SCOPES 과다
- httpx import 미사용

### 9. Flash 메시지 (flash.py)
- get_flashed_messages() 호출 시 request 인자 미전달
- 세션 기반 한계 (재시작 시 소실)

### 10. CSRF (csrf.py)
- validate_csrf_token() 어디서도 호출 안 됨 → 보호 무력화
- 토큰 갱신 메커니즘 없음

---

## 시급한 수정 사항

| 순위 | 이슈 | 심각도 |
|------|------|--------|
| 1 | CSRF 검증 미수행 | High |
| 2 | Google OAuth 토큰 미저장 | High |
| 3 | RosterParser/ReceiptParser 부재 | High |
| 4 | 인증 체크 분산 (Depends 통합 필요) | Medium |
| 5 | user_id 하드코딩 | Medium |
| 6 | 배치 처리 순차 실행 | Medium |

---

## 참조 소스

| 파일 | 참조 |
|------|------|
| main.py | FastAPI 공식 문서, Authlib Google Login, Flask flash/CSRF, Vercel 배포 |
| database.py | FastAPI + SQLAlchemy 공식 문서 |
| flash.py | Flask flash() 패턴 포팅 |
| csrf.py | Flask-WTF CSRF 패턴 포팅 |
| storage.py | OCI Python SDK 공식 예제 |
| parsers/registry.py | py-pdf-parser, 플러그인 패턴 |
| exporters/excel.py | pdfplumber + pandas + openpyxl |
| sheets_integration.py | Google Sheets API Quickstart |
| static/css/style.css | Tailwind CSS 색상 토큰 |
