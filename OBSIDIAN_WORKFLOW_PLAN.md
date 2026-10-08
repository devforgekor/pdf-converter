# 옵시디언 워크플로우 및 서버 통신 프로토콜 계획서 (v4)

> 작성일: 2026-09-19
> 대상: Dataview + Obsidian Git 기반 볼트 + 서버 통신 프로토콜
> 총 소요: 약 3주 (30분~1시간/일)
> 원칙: 한 단계씩 적용, Git 커밋 백업 후 다음 단계 진행

---

## 1단계: 환경 정비 (1~2일)

### 1-1. .gitignore

```gitignore
.DS_Store
._*
Thumbs.db
desktop.ini

# 로컬 상태 (기기별로 다름)
.obsidian/workspace.json
.obsidian/workspace-mobile.json
.obsidian/workspace*.json
.obsidian/graph.json
.obsidian/cache/
.obsidian/copilot-index*.json

# 플러그인 설정 (민감 정보)
.obsidian/plugins/*/data.json
!/.obsidian/plugins/dataview/data.json
!/.obsidian/plugins/obsidian-git/data.json
```

### 1-2. 추적 해제 및 .gitattributes

```bash
git rm --cached .obsidian/workspace.json .obsidian/graph.json
git commit -m "chore: stop tracking local workspace and graph state"
```

`.gitattributes`:
```
* text=auto eol=lf
*.md text eol=lf
*.json text eol=lf
*.png binary
*.jpg binary
```

### 1-3. PARA 폴더 구조 (2026 표준)

```
00_Inbox/
10_Projects/
20_Areas/
30_Resources/
40_Archive/
50_Atlas/        ← MOC(Maps of Content) 전용
_Templates/
_Attachments/
```

- Properties 플러그인(코어)으로 frontmatter 관리
- 필수 속성: `type`, `status`, `created`, `tags`
- frontmatter 뒤쪽 공백 주의: Dataview 0.5.x에서 공백 있으면 노트 누락

### 검증
- [ ] workspace.json이 추적되지 않음
- [ ] 다른 기기 pull 후 충돌 없음
- [ ] PARA 폴더 구조 생성 완료

---

## 2단계: Templater + Linter + Daily Notes (3~5일)

### 2-1. Templater 설정

- Folder Templates:
  - `_Templates/Project` → 프로젝트 노트 템플릿
  - `_Templates/Area` → 영역 노트 템플릿
- Templater는 기존 Templates 코어 플러그인을 **대체** (병행 사용 불가)
- JavaScript 실행 지원으로 동적 변수, 날짜 계산 가능

### 2-2. Daily Notes 템플릿 예시

```markdown
---
type: daily
created: <% tp.date.now("YYYY-MM-DD") %>
tags: [daily]
---
# <% tp.date.now("YYYY-MM-DD dddd") %>

## 캡처
<% tp.file.cursor(0) %>

## 오늘 할 일
- [ ]
```

### 2-3. Properties(코어 플러그인) 활용

2026년 기준 frontmatter는 Properties UI로 관리:
- 타입 선택: text, number, date, checkbox, list, tag
- Obsidian이 YAML을 자동 생성
- 태그는 `tags` 속성에 list로 관리 (태그 패널에서 이름 변경/병합 가능)

### 2-4. Linter 설정 (v1.33+)

Linter로 Markdown 포맷 자동 일관성 유지:

| 설정 항목 | 권장값 |
|-----------|--------|
| YAML dedupe | 켬 |
| YAML format tags | 켬 |
| Trailing spaces 제거 | 켬 |
| Empty line around code blocks | 켬 |
| Custom Ignore Strings | `dataview`, `excalidraw`, `tasks`, `base` |

**코드블록 보호가 핵심**: Dataview, Tasks, Bases 쿼리 블록이 Linter에 의해 깨지지 않도록 반드시 설정.

### 2-5. 태그 관리

Tag Wrangler 플러그인은 지원 중단됨. 옵시디언 기본 기능 사용:
- Tags 패널에서 우클릭 → 이름 변경/병합
- 계층형 태그: `#project/`, `#area/`, `#status/`

### 검증
- [ ] 새 노트 생성 시 frontmatter 자동 삽입
- [ ] Linter 실행 후 코드블록 깨지지 않음
- [ ] Daily note가 날짜와 함께 정상 생성

---

## 3단계: Dataview + Bases (5~7일)

### 3-1. Dataview

SQL-like 구문으로 노트를 쿼리:

```markdown
## 활성 프로젝트
```dataview
TABLE status, created, due
FROM "10_Projects"
WHERE status = "active"
SORT created DESC
```

## 이번 주 노트
```dataview
TABLE file.name, file.mtime
FROM "00_Inbox"
WHERE file.mtime >= date(today) - dur(7 days)
SORT file.mtime DESC
```
```

**주의사항**:
- frontmatter 뒤쪽 공백 제거 (Dataview 0.5.x 누락 버그)
- Tasks 쿼리와 Dataview 쿼리는 **동일 구문 아님** 혼용 금지

### 3-2. Bases (코어 플러그인, v1.12+)

Dataview의 부분적 대체. 코어 플러그인이므로 별도 설치 불필요:

```markdown
```base
table status, created, due
from "10_Projects"
sort created desc
```
```

| 기준 | Bases | Dataview |
|------|-------|----------|
| 설치 | 코어 (불필요) | 커뮤니티 |
| 뷰 | 테이블, 카드, 맵 | 테이블, 리스트, 태스크 |
| 인라인 쿼리 | 불가 | 가능 |
| 계산 필드 | 기본 수식 | JavaScript |
| 쿼리 깊이 | 단순 필터/정렬 | 복잡한 조건/조인 |
| 모바일 | 완벽 지원 | 플러그인 의존 |

**권장**: 단순 목록/카드 뷰는 Bases, 복잡한 대시보드는 Dataview 사용.

### 검증
- [ ] Dataview 쿼리가 frontmatter를 정상 읽음
- [ ] Bases에서 프로젝트 목록 테이블/카드 뷰 확인

---

## 4단계: Excalidraw + Periodic Notes (3~5일)

### 4-1. Excalidraw

- `.excalidraw.md` 파일로 저장
- `![[다이어그램.excalidraw]]`로 노트에 임베드
- v1.12+: Canvas에서 임베드된 파일의 백링크 감지, Graph view에 표시
- Scripting으로 Obsidian 노트와 양방향 링크 가능

### 4-2. Periodic Notes

Daily Notes를 확장:
- Daily → Weekly → Monthly → Quarterly → Yearly
- Calendar 플러그인과 연동하여 사이드바에서 빠른 탐색
- 주간 리뷰 루틴: Inbox 비우기, 프로젝트 상태 업데이트, MOC 갱신

### 4-3. 주간 리뷰 체크리스트

```markdown
## 주간 리뷰 (매주 일요일)
- [ ] Inbox 비우기 → PARA 폴더로 이동
- [ ] 활성 프로젝트 상태 확인
- [ ] 이번 주 Daily Notes에서 영구 노트 추출
- [ ] 관련 MOC에 새 노트 추가
- [ ] 완료된 프로젝트 → Archive로 이동
```

### 검증
- [ ] Excalidraw 노트가 Graph view에 표시
- [ ] Calendar에서 주간/월간 노트 생성 가능

---

## 5단계: AI 통합 (5~7일)

### 5-1. Smart Connections

vault 내 노트 간 연결 추천:
- Embedding 모델: 로컬 모델 권장 (BGE-small-ko 등)
- Exclude: `.obsidian/`, `_Templates/`, `_Attachments/`
- **주의**: data.json에 API 키 저장될 수 있음 → .gitignore 확인 필수
- AI 플러그인의 `vaultPath`가 절대 경로로 저장되는 문제: 기기 이동 시 수동 수정 필요

### 5-2. Copilot (대안)

vault와 대화형 AI 인터페이스:
- 내 노트 기반으로 질문/답변 (RAG)
- 로컬 모델 또는 API 키 필요
- Smart Connections보다 대화형, Smart Connections보다 연결 탐색에 강함

### 5-3. Obsidian + Claude Code (고급)

vault를 Claude Code에 직접 연결:
```bash
# vault 폴더에서 실행
claude
# CLAUDE.md 파일에 볼트 구조/규칙 정의
```
- 강력하지만 데스크톱 + 터미널 전용
- 토큰 사용량 발생

### 검증
- [ ] Smart Connections가 관련 노트를 정상 추천
- [ ] API 키가 Git에 포함되지 않음

---

## 6단계: Git 운영 최적화 (1~2일)

### 6-1. Obsidian Git 설정 (v2.38.0+)

| 설정 항목 | 권장값 | 설명 |
|-----------|--------|------|
| Auto-pull on startup | 켬 | 시작 시 자동 풀 |
| Auto-commit-and-sync | 10분 | 커밋 + 풀 + 푸시 |
| Pull strategy | pull --rebase | 리베이스로 깔끔한 히스토리 |
| Commit message | `vault backup: {{date}}` | 날짜 포함 커밋 |
| Auto-stash | 켬 | 풀 전 변경사항 자동 stash |

**v2.38.0 신규 기능**:
- 개별 파일 staged commit 지원 (`auto commit only staged files`)
- merge 전략 설정 가능 (`specify merge strategy`)
- status bar 커스터마이징 (`granular settings`)

### 6-2. 다중 기기 규칙

1. **편집 전 반드시** `git pull` (Obsidian Git이 자동으로 처리)
2. 충돌 발생 시 `.obsidian/workspace.json` 충돌 무시하고 accepts theirs

### 6-3. 주간 점검

```bash
git log --oneline -20
git status
# 추적되면 안 될 파일 확인
# 충돌 마커(<<<<<<<) 검색
```

### 6-4. 백업 전략

| 레이어 | 방법 | 주기 |
|--------|------|------|
| 실시간 | Obsidian Git 자동 커밋 | 10분 |
| 주간 | rclone으로 별도 클라우드 저장소에 복사 | 매주 일요일 |

> **Sync ≠ Backup**: 한 기기에서 삭제하면 모든 기기에서 삭제됨. rclone 백업은 별도 복사본으로 롤백 가능.

### 검증
- [ ] 시작 시 자동 풀 정상 작동
- [ ] 10분마다 자동 커밋/푸시
- [ ] rclone 주간 백업 스크립트 동작 확인

---

## 7단계: 서버 통신 프로토콜 + 파일 잠금 (5~7일)

### 7-1. 컨셉: 대칭적 아키텍처 (Symmetric Architecture)

두 서버(devforge, kuhwa)가 동등한 권한으로 작동하는 구조:

| 구성 요소 | 기존 구현체 | 적용 방식 |
|-----------|-------------|-----------|
| Markdown = 티켓 | TicGit, MDT | 요청/응답 파일 생성 |
| YAML Frontmatter = 헤더 | MDT, GitHub Docs | status, type, priority 등 |
| Git = 메시지 큐 | Obsidian Git | 자동 동기화 |
| 파일 잠금 = 충돌 방지 | Git LFS Locking + 커스텀 락 | 대용량 파일은 LFS, Markdown은 .lock 파일 |
| Git Remote = 소스 오브 트루스 | GitHub/GitLab | 분쟁 해결을 위한 최종 소스 |

### 7-2. 대칭적 vs 비대칭적 아키텍처

| 항목 | 비대칭 (현재 계획) | 대칭 (목표) |
|------|-------------------|-------------|
| 서버 역할 | devforge: 주, kuhwa: 보조 | 두 서버 모두 동등 |
| 편집 권한 | devforge에서만 편집 | 두 서버 모두 편집 가능 |
| 락 관리 | devforge가 생성, kuhwa이 확인 | 두 서버 모두 생성/확인 가능 |
| Git Push | devforge가 주도 | 두 서버 모두 동일하게 푸시 |
| 분쟁 해결 | devforge 우선 | Git Remote가 최종 소스 |

### 7-3. 아키텍처 개요

```
devforge (Obsidian)  ←→  GitHub Remote  ←→  kuhwa (Obsidian)
    ↓                        ↑                        ↓
.lock 파일 생성          소스 오브 트루스          .lock 파일 생성
    ↓                        ↑                        ↓
Git Push  ←────────────  분쟁 해결  ────────────→  Git Push
```

**핵심 원칙:**
1. 두 서버는 동일한 코드와 스크립트를 사용
2. 파일 잠금으로 동시 편집 방지
3. Git Remote(GitHub)가 최종 분쟁 해결
4. 어떤 서버든 장애 발생 시 다른 서버가 대체 가능

### 7-4. 폴더 구조 (Zone Rule)

```
vault/
├── .obsidian/              # Obsidian 설정
├── .git/                   # Git 저장소
├── .gitattributes          # LFS 설정
├── .gitignore              # Git 제외 파일
├── 00_Inbox/               # 사용자 캡처 (편집 가능)
├── 10_Requests/            # 서버 요청 (사용자 생성, 서버 읽기)
├── 20_Processing/          # 서버 처리 중 (서버만 편집)
├── 30_Responses/           # 서버 응답 (서버 생성, 사용자 읽기)
├── 40_Archive/             # 완료된 요청/응답
├── _Templates/             # 템플릿 파일
├── _Meta/                  # 대시보드
├── _Attachments/           # 이미지, PDF (LFS 대상)
└── scripts/                # 서버 자동화 스크립트
```

### 7-4. YAML Frontmatter 표준

```markdown
---
type: request
status: pending
requester: devforge
assignee: kuhwa
priority: high
created: 2026-09-19
due: 2026-09-20
tags: [data-processing, automation]
---
```

### 7-5. 파일 잠금 시스템

**잠금 방식 2가지:**

| 방식 | 대상 | 방법 |
|------|------|------|
| Git LFS Locking | 대용량 파일 (이미지, PDF) | `git lfs lock` |
| 커스텀 .lock 파일 | Markdown 노트 | `file.md.lock` 생성 (JSON) |

**.lock 파일 구조 (JSON):**
```json
{
  "locked_by": "devforge",
  "locked_at": "2026-09-19T10:00:00+09:00",
  "last_heartbeat": "2026-09-19T10:05:00+09:00",
  "expires_at": "2026-09-19T10:32:00+09:00",
  "reason": "편집 중 - API 문서 작성"
}
```

**heartbeat 메커니즘:**
- 편집 중 30초마다 heartbeat 갱신
- 2분간 입력 없으면 idle timeout으로 락 해제
- 만료된 락은 자동 삭제

### 7-6. 락 관리 스크립트 (Python + bash)

#### Python 핵심 로직

`scripts/lock-manager.py`:

```python
#!/usr/bin/env python3
"""Obsidian Vault Lock Manager (Symmetric)
두 서버(devforge, kuhwa) 모두 동일하게 사용"""

import os
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

class LockManager:
    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path)
        self.server_name = os.uname().nodename
        self.lock_duration = 1800  # 30분
        self.idle_timeout = 120    # 2분 (초)
    
    def get_lock_file(self, file_path: str) -> Path:
        return self.vault_path / f"{file_path}.lock"
    
    def lock(self, file_path: str, reason: str = "편집 중") -> dict:
        lock_file = self.get_lock_file(file_path)
        
        if lock_file.exists():
            existing = self.read_lock(lock_file)
            if existing and not self.is_expired(existing):
                return {
                    "success": False,
                    "error": f"{existing['locked_by']}에서 잠겨있습니다",
                    "expires": existing["expires_at"]
                }
        
        now = datetime.now()
        lock_data = {
            "locked_by": self.server_name,
            "locked_at": now.isoformat(),
            "last_heartbeat": now.isoformat(),
            "expires_at": (now + timedelta(seconds=self.lock_duration)).isoformat(),
            "reason": reason
        }
        
        lock_file.write_text(json.dumps(lock_data, indent=2))
        
        return {
            "success": True,
            "server": self.server_name,
            "expires": lock_data["expires_at"]
        }
    
    def unlock(self, file_path: str) -> dict:
        lock_file = self.get_lock_file(file_path)
        
        if not lock_file.exists():
            return {"success": True, "message": "이미 잠금 해제됨"}
        
        lock_data = self.read_lock(lock_file)
        
        if lock_data["locked_by"] != self.server_name:
            return {
                "success": False,
                "error": f"{lock_data['locked_by']}에서 잠금"
            }
        
        lock_file.unlink()
        return {"success": True}
    
    def heartbeat(self, file_path: str) -> dict:
        lock_file = self.get_lock_file(file_path)
        
        if not lock_file.exists():
            return {"success": False, "error": "잠금 없음"}
        
        lock_data = self.read_lock(lock_file)
        
        if lock_data["locked_by"] != self.server_name:
            return {"success": False, "error": "다른 서버 소유"}
        
        lock_data["last_heartbeat"] = datetime.now().isoformat()
        lock_data["expires_at"] = (datetime.now() + timedelta(seconds=self.lock_duration)).isoformat()
        
        lock_file.write_text(json.dumps(lock_data, indent=2))
        
        return {"success": True, "expires": lock_data["expires_at"]}
    
    def status(self, file_path: str) -> dict:
        lock_file = self.get_lock_file(file_path)
        
        if not lock_file.exists():
            return {"locked": False}
        
        lock_data = self.read_lock(lock_file)
        
        if self.is_expired(lock_data):
            lock_file.unlink()
            return {"locked": False, "message": "만료된 락 삭제됨"}
        
        return {"locked": True, **lock_data}
    
    def clean_expired(self) -> dict:
        count = 0
        for lock_file in self.vault_path.rglob("*.lock"):
            lock_data = self.read_lock(lock_file)
            if self.is_expired(lock_data):
                lock_file.unlink()
                count += 1
        
        return {"deleted": count}
    
    def read_lock(self, lock_file: Path) -> dict:
        return json.loads(lock_file.read_text())
    
    def is_expired(self, lock_data: dict) -> bool:
        expires = datetime.fromisoformat(lock_data["expires_at"])
        return datetime.now() > expires


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("사용법: lock-manager.py [lock|unlock|status|heartbeat|clean] <file> [reason]")
        sys.exit(1)
    
    manager = LockManager("/path/to/vault")
    command = sys.argv[1]
    file_path = sys.argv[2]
    
    if command == "lock":
        reason = sys.argv[3] if len(sys.argv) > 3 else "편집 중"
        result = manager.lock(file_path, reason)
    elif command == "unlock":
        result = manager.unlock(file_path)
    elif command == "status":
        result = manager.status(file_path)
    elif command == "heartbeat":
        result = manager.heartbeat(file_path)
    elif command == "clean":
        result = manager.clean_expired()
    else:
        print(f"알 수 없는 명령어: {command}")
        sys.exit(1)
    
    print(json.dumps(result, indent=2, ensure_ascii=False))
```

#### bash 래퍼 (기존 스크립트와 호환)

`scripts/lock-manager.sh`:

```bash
#!/bin/bash
# Obsidian Vault Lock Manager (bash wrapper)
# Python 스크립트를 호출하여 기존 cron/스크립트와 호환 유지

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/lock-manager.py"

python3 "$PYTHON_SCRIPT" "$@"
```

**실행 권한 부여:**
```bash
chmod +x scripts/lock-manager.py
chmod +x scripts/lock-manager.sh
```

### 7-7. 자동 동기화 스크립트

`scripts/auto-sync.sh`:

```bash
#!/bin/bash
# Obsidian Vault Auto-Sync with Lock Management

VAULT_PATH="/path/to/vault"
SERVER_NAME=$(hostname -s)
LOCK_MANAGER="$VAULT_PATH/scripts/lock-manager.sh"

cd "$VAULT_PATH"

# 1. 만료된 락 정리
echo "만료된 락 정리 중..."
$LOCK_MANAGER clean

# 2. Git Pull (rebase로 깔끔한 히스토리 유지)
echo "Git Pull 실행..."
git pull --rebase origin main

# 3. 로컬 변경사항 확인
if [[ -n $(git status -s) ]]; then
    echo "변경사항 감지됨"
    
    # 4. 락 파일 제외하고 커밋
    git add --all ':!*.lock'
    
    # 5. 커밋 & 푸시
    git commit -m "Auto-sync: $(date '+%Y-%m-%d %H:%M:%S') [$SERVER_NAME]"
    git push origin main
    
    echo "동기화 완료"
else
    echo "변경사항 없음"
fi
```

### 7-8. Heartbeat 데몬 (Python)

`scripts/heartbeat-daemon.py`:

```python
#!/usr/bin/env python3
"""Heartbeat daemon - 열린 락의 heartbeat을 갱신"""

import time
import json
from pathlib import Path

class HeartbeatDaemon:
    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path)
        self.interval = 30  # 30초마다 heartbeat
    
    def update_heartbeats(self):
        for lock_file in self.vault_path.rglob("*.lock"):
            try:
                lock_data = json.loads(lock_file.read_text())
                
                # 본인 소유 락만 갱신
                import os
                if lock_data.get("locked_by") == os.uname().nodename:
                    from datetime import datetime, timedelta
                    lock_data["last_heartbeat"] = datetime.now().isoformat()
                    lock_data["expires_at"] = (datetime.now() + timedelta(seconds=1800)).isoformat()
                    
                    lock_file.write_text(json.dumps(lock_data, indent=2))
                    print(f"Heartbeat 갱신: {lock_file.stem}")
            except Exception as e:
                print(f"에러: {lock_file} - {e}")
    
    def run(self):
        print("Heartbeat daemon 시작...")
        while True:
            self.update_heartbeats()
            time.sleep(self.interval)


if __name__ == "__main__":
    daemon = HeartbeatDaemon("/path/to/vault")
    daemon.run()
```

**실행:**
```bash
# 백그라운드로 실행
python3 scripts/heartbeat-daemon.py &

# 또는 systemd 서비스로 등록
sudo cp scripts/obsidian-heartbeat.service /etc/systemd/system/
sudo systemctl enable --now obsidian-heartbeat
```

### 7-9. Cron 설정 (대칭적)

두 서버 모두 동일하게 설정:

```bash
# devforge 서버
crontab -e
# 5분마다 동기화
*/5 * * * * /path/to/vault/scripts/auto-sync.sh >> /var/log/obsidian-sync.log 2>&1

# kuhwa 서버 (동일)
crontab -e
# 5분마다 동기화
*/5 * * * * /path/to/vault/scripts/auto-sync.sh >> /var/log/obsidian-sync.log 2>&1
```

**Heartbeat 데몬:**
```bash
# systemd 서비스로 등록 (권장)
sudo systemctl enable --now obsidian-heartbeat
```

**참고:** 두 서버 모두 5분마다 동기화. Heartbeat은 30초마다 갱신.

### 7-10. 모니터링 대시보드

`_Meta/Lock Dashboard.md`:

````markdown
---
type: dashboard
created: 2026-09-19
---

# 잠금 상태 대시보드

## 현재 잠긴 파일

```dataview
TABLE 
  locked_by as "잠금 서버",
  last_heartbeat as "Heartbeat",
  expires_at as "만료 시간",
  reason as "사유"
FROM "*.lock"
WHERE expires_at > date(now)
SORT expires_at ASC
```

## 만료 예정 (30분 이내)

```dataview
TABLE 
  locked_by as "잠금 서버",
  last_heartbeat as "Heartbeat",
  expires_at as "만료 시간"
FROM "*.lock"
WHERE expires_at <= date(now) + duration(30 minutes)
  AND expires_at > date(now)
SORT expires_at ASC
```

## Heartbeat 상태

```dataview
TABLE 
  locked_by as "서버",
  last_heartbeat as "마지막 Heartbeat",
  date(now) - date(last_heartbeat) as "경과 시간"
FROM "*.lock"
WHERE expires_at > date(now)
SORT last_heartbeat ASC
```
````

### 7-11. 운영 시나리오

**시나리오 1: devforge에서 문서 편집**
```bash
# 락 생성
scripts/lock-manager.sh lock "10_Requests/new-request.md" "요청 작성 중"
# 출력: {"success": true, "server": "devforge", "expires": "2026-09-19T10:30:00"}

# 편집 중 heartbeat 갱신 (30초마다 자동 또는 수동)
scripts/lock-manager.sh heartbeat "10_Requests/new-request.md"
# 출력: {"success": true, "expires": "2026-09-19T10:32:00"}

# 편집 완료 후 락 해제
scripts/lock-manager.sh unlock "10_Requests/new-request.md"
# 출력: {"success": true}
```

**시나리오 2: kuhwa에서 같은 파일 편집 시도**
```bash
scripts/lock-manager.sh lock "10_Requests/new-request.md"
# 출력: {"success": false, "error": "devforge에서 잠겨있습니다", "expires": "2026-09-19T10:32:00"}
```

**시나리오 3: 만료된 락 강제 해제**
```bash
scripts/lock-manager.sh clean
# 출력: {"deleted": 3}
```

**시나리오 4: 락 상태 확인**
```bash
scripts/lock-manager.sh status "10_Requests/new-request.md"
# 출력: {"locked": true, "locked_by": "devforge", "last_heartbeat": "...", "expires_at": "..."}
```

### 7-12. 분쟁 해결 전략

**2서버 대칭 아키텍처의 한계:**
- 2서버는 합의(consensus) 불가능 (최소 3서버 필요)
- Git Remote(GitHub)가 최종 분쟁 해결

**시나리오별 처리:**

| 시나리오 | 처리 방식 |
|----------|-----------|
| 두 서버가 동시에 같은 파일 편집 | Git push에서 충돌 발생 → Git이 자동 병합 시도 |
| Git 자동 병합 실패 | `.conflict-*` 파일로 보존 → 수동 해결 |
| 한 서버 장애 | 다른 서버가 정상 작동, 장애 복구 후 동기화 |
| 락 충돌 (동시 잠금 시도) | Git에서 락 파일 병합 → 최신 락이 유지됨 |

**Git 충돌 해결 예시:**
```bash
# 충돌 발생 시
git pull --rebase origin main
# 충돌 파일 수정
git add .
git rebase --continue
git push origin main
```

---

## 3주 마일스톤

| 주차 | 단계 | 목표 |
|------|------|------|
| 1주 | 1, 2단계 | Git 안전망, PARA 구조, Templater, Linter |
| 2주 | 3, 4단계 | Dataview + Bases, Excalidraw |
| 3주 | 5, 6, 7단계 | AI, Git 최적화, 서버 통신 + 파일 잠금 |

---

## 핵심 조언

1. **PARA + Properties를 1주차에 끝내세요.** 메타데이터 일관성이 나머지 플러그인의 기반입니다.
2. **매 단계 종료 시 Git 커밋.** "2단계 완료: Templater"처럼 남기면 롤백 가능.
3. **플러그인은 필요할 때 추가.** 노트 100개 이상 쌓인 후 Excalidraw/AI 도입.
4. **2026년부터는 Bases(코어)로 단순 뷰를 대체.** Dataview는 복잡한 쿼리에만 집중.
5. **백업은 Sync와 별개로 관리.** rclone으로 주간 백업 필수.
6. **플러그인 설치 후 2주간 추가 설치 금지.** 익숙해질 때까지 집중.
7. **서버 통신은 Zone Rule을 지키세요.** 물리적 폴더 분리로 충돌 방지.
8. **파일 편집 전 락을 확인하세요.** `lock-manager.sh status <file>`로 확인 후 편집 시작.
9. **bash는 간단한 로직만, Python은 복잡한 로직만.** Git操作은 bash, 락 관리/Webhook은 Python.

---

## 참고 자료

- Obsidian Git 공식: https://github.com/Vinzent03/obsidian-git
- Obsidian Git v2.38.0 CHANGELOG: https://github.com/Vinzent03/obsidian-git/blob/master/CHANGELOG.md
- TicGit (Git-native 이슈 트래커): https://github.com/schacon/ticgit
- Markdown Ticket (MDT): https://github.com/andkirby/markdown-ticket
- obsidian-shellcommands: https://github.com/Taitava/obsidian-shellcommands
- PKV Sync (가장 유사 프로젝트): https://github.com/CyberKurry/pkv-sync
- SupSync (파일 잠금 참조): https://github.com/jaliriogbarrios19/SupSync
- Constellation Sync (분쟁 해결 참조): https://github.com/rexvane/obsidian-constellation-sync
- Obsidian Bases 가이드: https://enersys.co.th/en/insights/obsidian-systematic-pkm-guide-2026
- Obsidian 2026 플러그인 가이드: https://www.obsibrain.com/blog/top-obsidian-plugins-in-2026
- Obsidian Second Brain: https://ainotely.com/blog/obsidian-second-brain/
- Obsidian 플러그인 실제 사용기: https://www.scoding.kr/2026/07/obsidian-plugins-that-actually-work-in.html
