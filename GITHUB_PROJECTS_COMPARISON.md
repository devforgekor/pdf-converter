# 유사 GitHub 프로젝트 비교 분석

> 작성일: 2026-09-19
> 목적: devforge + kuhwa 대칭적 아키텍처 구현을 위한 기존 프로젝트 비교

---

## 요약

| 프로젝트 | 유사도 | 핵심 특징 | 락 방식 | 분쟁 해결 |
|----------|--------|-----------|---------|-----------|
| **PKV Sync** | ★★★★★ | Git = 소스 오브 트루스, 셀프 호스팅 | Per-vault push locks | `.conflict-*` 파일 |
| **SupSync** | ★★★★☆ | 실시간 동기화, 파일 잠금 | Heartbeat + idle timeout | Side-by-side diff |
| **Constellation Sync** | ★★★☆☆ | GitHub 브랜치 기반, 멀티 볼트 | Git LFS Locking | Three-way merge |

---

## 1. PKV Sync (가장 유사)

**GitHub**: https://github.com/CyberKurry/pkv-sync

### 아키텍처

```
Obsidian Client  ←→  PKV Sync Server  ←→  Bare Git Repo
    ↓                      ↓                      ↓
Plugin (TypeScript)    Single Binary          SQLite DB
```

### 핵심 특징

| 항목 | 설명 |
|------|------|
| Git = 소스 오브 트루스 | 모든 볼트가 bare git repo, 파일 히스토리/복원/병합 지원 |
| Per-vault push locks | 볼트 단위 잠금으로 동시 푸시 방지 |
| Conflict-safe | `.conflict-*` 파일로 분쟁 해결 (자동 덮어쓰기 없음) |
| 심플 구조 | Single binary + SQLite + bare git repo (클러스터/S3 불필요) |
| MCP 지원 | Model Context Protocol로 AI 통합 |

### 락 메커니즘

```go
// Per-vault push lock (Go)
type Vault struct {
    ID        string
    Lock      sync.RWMutex  // 볼트 단위 읽기/쓰기 잠금
    PushLock  sync.Mutex     // 동시 푸시 방지
    // ...
}
```

### 장단점

**장점:**
- Git이 소스 오브 트루스 → 분쟁 해결이 직관적
- 단일 바이너리로 배포 간단
- 파일 히스토리/복원/병합 자동 지원
- MCP로 AI 통합 가능

**단점:**
- Go로 작성 (Python 스크립트와 통합 어려움)
- 서버 사이드에서 볼트 내용 읽기 가능 (E2EE 없음)
- 2서버 대칭 지원 안 됨 (단일 서버 아키텍처)

---

## 2. SupSync (파일 잠금 가장 유사)

**GitHub**: https://github.com/jaliriogbarrios19/SupSync

### 아키텍처

```
Obsidian Client  ←→  Supabase (DB + Storage)
    ↓                      ↓
Plugin (TypeScript)    PostgreSQL + Realtime
```

### 핵심 특징

| 항목 | 설명 |
|------|------|
| 실시간 동기화 | WebSocket으로 즉시 반영 |
| 파일 잠금 | 자동 잠금 생성, heartbeat, idle timeout |
| 분쟁 해결 | Side-by-side diff 모달 |
| 멀티 유저 | 볼트별 초대 시스템 |

### 락 메커니즘

```typescript
// SupSync lock-manager.ts
interface Lock {
    file_path: string;
    user_id: string;
    acquired_at: Date;
    last_heartbeat: Date;
    expires_at: Date;
}

// 잠금 획득 시
async function acquireLock(filePath: string): Promise<Lock> {
    // 1. 기존 잠금 확인
    const existing = await getLock(filePath);
    if (existing && !isExpired(existing)) {
        throw new Error(`File locked by ${existing.user_id}`);
    }
    
    // 2. 새 잠금 생성
    const lock = {
        file_path: filePath,
        user_id: currentUser.id,
        acquired_at: new Date(),
        last_heartbeat: new Date(),
        expires_at: new Date(Date.now() + 2 * 60 * 1000) // 2분 idle timeout
    };
    
    await supabase.from('locks').upsert(lock);
    return lock;
}

// Heartbeat (30초마다)
setInterval(async () => {
    await supabase.from('locks')
        .update({ last_heartbeat: new Date() })
        .eq('user_id', currentUser.id);
}, 30000);
```

### 락 해제 조건

1. 노트 닫을 때
2. 2분간 입력 없을 때
3. 다른 노트로 전환할 때

### 장단점

**장점:**
- Heartbeat으로 실시간 잠금 상태 유지
- Idle timeout으로 만료된 락 자동 해제
- Side-by-side diff로 분쟁 해결直观

**단점:**
- Supabase 의존 (셀프 호스팅 불가)
- Git 히스토리 없음
- 2서버 대칭 지원 안 됨

---

## 3. Constellation Sync (분쟁 해결 가장 유사)

**GitHub**: https://github.com/rexvane/obsidian-constellation-sync

### 아키텍처

```
Obsidian Client  ←→  GitHub Private Repo
    ↓                      ↓
Plugin (TypeScript)    Branch per Vault
```

### 핵심 특징

| 항목 | 설명 |
|------|------|
| GitHub 브랜치 기반 | 볼트당 독립 브랜치 |
| Three-way merge | 자동 분쟁 해결 |
| Conflict copies | 분쟁 파일 보존 (`.conflict-*`) |
| 멀티 볼트 | 단일 리포지토리에서 여러 볼트 관리 |

### 분쟁 해결 메커니즘

```typescript
// Constellation Sync conflict resolution
function resolveConflict(
    local: string,
    remote: string,
    base: string
): { result: string; conflicts: Conflict[] } {
    // Three-way merge 시도
    const merged = threeWayMerge(local, remote, base);
    
    if (merged.success) {
        return { result: merged.content, conflicts: [] };
    }
    
    // 분쟁 발생 시 conflict 파일 생성
    const conflictFiles = [
        { path: `${filePath}.conflict-local`, content: local },
        { path: `${filePath}.conflict-remote`, content: remote }
    ];
    
    return { result: null, conflicts: conflictFiles };
}
```

### 장단점

**장점:**
- GitHub가 소스 오브 트루스 → 분쟁 해결 직관적
- Three-way merge로 자동 병합
- Conflict files로 수동 해결 가능

**단점:**
- GitHub 의존
- 파일 잠금 없음 (동시 편집 시 충돌 발생)
- 2서버 대칭 지원 안 됨

---

## 비교: 우리의 아키텍처 vs 기존 프로젝트

| 항목 | 우리의 계획 | PKV Sync | SupSync | Constellation |
|------|-------------|----------|---------|---------------|
| **소스 오브 트루스** | GitHub Remote | Bare Git Repo | Supabase DB | GitHub Branch |
| **파일 잠금** | .lock 파일 + heartbeat | Per-vault push locks | Heartbeat + timeout | 없음 |
| **분쟁 해결** | Git 충돌 해결 | .conflict-* 파일 | Side-by-side diff | Three-way merge |
| **서버 아키텍처** | 2서버 대칭 | 단일 서버 | Supabase (단일) | GitHub (단일) |
| **셀프 호스팅** | O (Linux 서버) | O (Single binary) | X (Supabase) | X (GitHub) |
| **Git 히스토리** | O | O | X | O |
| **실시간 동기화** | 5분 cron | SSE (Sub-second) | WebSocket (Real-time) | 15초 cron |

---

## 추천: 기존 프로젝트 장점 흡수

### 1. PKV Sync에서 흡수할 점

- **Git = 소스 오브 트루스**: 이미 우리의 계획과 일치
- **Per-vault push locks**: 볼트 단위 잠금 → 파일 단위 잠금으로 확장
- **.conflict-* 파일**: Git 충돌 시 conflict 파일로 보존

### 2. SupSync에서 흡수할 점

- **Heartbeat 메커니즘**: 30초마다 락 갱신 → 만료 자동 처리
- **Idle timeout**: 2분간 입력 없으면 락 해제 → 사용자 편의
- **Real-time notification**: WebSocket으로 락 상태 즉시 알림

### 3. Constellation Sync에서 흡수할 점

- **Three-way merge**: Git이 자동으로 병합 시도
- **Conflict copies**: 분쟁 파일 보존 → 수동 해결 가능

---

## 우리의 아키텍처에 적용할 점

### 1. 락 메커니즘 강화

```bash
# 현재: 단순 .lock 파일
locked_by: devforge
locked_at: 2026-09-19T10:00:00
expires_at: 2026-09-19T10:30:00

# 개선: Heartbeat + idle timeout
locked_by: devforge
locked_at: 2026-09-19T10:00:00
last_heartbeat: 2026-09-19T10:05:00
expires_at: 2026-09-19T10:32:00  # idle 2분 후 만료
```

### 2. 분쟁 해결 강화

```bash
# 현재: Git 충돌 해결 수동
# 개선: 자동 병합 시도 + conflict 파일 보존

# Git 충돌 발생 시
git merge HEAD origin/main
# 충돌 파일 생성
# → .conflict-local.md, .conflict-remote.md
# → 사용자가 수동으로 선택
```

### 3. 실시간 알림

```bash
# 현재: 5분 cron
# 개선: WebSocket으로 락 상태 즉시 알림

# lock-manager.sh에서 webhook 호출
curl -X POST https://slack.webhook/...
```

---

## 결론

**가장 비슷한 프로젝트: PKV Sync**

- Git = 소스 오브 트루스 (일치)
- Per-vault push locks (유사)
- Self-hosted (일치)

**차별점:**
1. **2서버 대칭**: PKV Sync는 단일 서버, 우리는 2서버 대칭
2. ** 파일 단위 락**: PKV Sync는 볼트 단위, 우리는 파일 단위
3. **bash 스크립트**: PKV Sync는 Go 바이너리, 우리는 bash 스크립트

**추천 접근법:**
1. PKV Sync의 Git = 소스 오브 트루스 컨셉 차용
2. SupSync의 heartbeat + idle timeout 락 메커니즘 적용
3. Constellation의 conflict files로 분쟁 해결
4. 우리의 2서버 대칭 아키텍처로 구현

---

## 참고 자료

- PKV Sync: https://github.com/CyberKurry/pkv-sync
- SupSync: https://github.com/jaliriogbarrios19/SupSync
- Constellation Sync: https://github.com/rexvane/obsidian-constellation-sync
- PKV Sync Plugin: https://github.com/CyberKurry/pkv-sync-plugin
