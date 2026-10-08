# Azure 전체 리소스 통합 마이그레이션 계획

> 작성일: 2026-09-19
> 상태: Phase 1 완료

---

## 1. 현황 분석

### 1.1 구독 체계

| 구독 ID | 이름 | 상태 |
|---------|------|------|
| 89c6a8ee-eb11-4ec2-b077-7f524f752815 | 기본 구독 | 해지 예정 |
| a942e898-e1ee-47f4-b9b3-d9475672ff4e | Azure for Students | 사용 유지 |

### 1.2 기존 리소스 목록

#### 구독 89c6a8ee (기본)
| 리소스 | 유형 | 리소스 그룹 | 위치 |
|--------|------|-------------|------|
| kv-devforge-prod-krc | Key Vault | rg-shared-devforge-prod-krc | koreacentral |

#### 구독 a942e898 (Azure for Students)
| 리소스 | 유형 | 리소스 그룹 | 위치 |
|--------|------|-------------|------|
| vm-devforge-prod-cin | VM | rg-devforge-prod-cin | centralindia |
| vm-devforge-prod-cin-vnet | VNet | rg-devforge-prod-cin | centralindia |
| doc-intel-kuhwa | Doc Intelligence | rg-devforge-prod-cin | koreacentral |
| gallery_devforge_prod_cin | Image Gallery | rg-devforge-prod-cin | centralindia |
| snap-qwen3-30b | Snapshot | rg-devforge-prod-cin | centralindia |
| NSG x 20+ | Network Security Group | rg-devforge-prod-cin | centralindia |
| Disk x 5+ | Managed Disk | rg-devforge-prod-cin | centralindia |
| NetworkWatcher x 2 | Network Watcher | NetworkWatcherRG | central/korea |

---

## 2. 목표 아키텍처

### 2.1 리소스 그룹 구조

```
Azure for Students 구독 (a942e898)
├── rg-devforge-prod-krc          (개발/포지 프로젝트)
├── rg-kuhwa-prod-krc           (온마이독 프로젝트)
└── rg-server-common-prod-krc     (공통 서버 인프라)
```

### 2.2 리소스 그룹별 배치

#### rg-server-common-prod-krc (공통 인프라)
| 리소스 | 설명 | 중요도 |
|--------|------|--------|
| kv-kuhwa-prod | Key Vault (시크릿 통합 관리) | 높음 |
| doc-intel-kuhwa | Azure Document Intelligence | 높음 |
| nsg-common-* | 공통 NSG 규칙 | 중간 |

#### rg-devforge-prod-krc (개발/포지 프로젝트)
| 리소스 | 설명 | 중요도 |
|--------|------|--------|
| vm-devforge-prod-001 | 방화벽 VM | 높음 |
| vnet-devforge-prod | 가상 네트워크 | 높음 |
| nsg-devforge-* | 서버별 NSG | 중간 |
| gallery-devforge-prod | Golden Image Gallery | 중간 |
| snap-qwen3-30b | LLM 스냅샷 | 낮음 |

#### rg-kuhwa-prod-krc (온마이독 프로젝트)
| 리소스 | 설명 | 상태 |
|--------|------|------|
| vm-kuhwa-prod-001 | 온마이독 VM | 추후 배포 |
| vnet-kuhwa-prod | 가상 네트워크 | 추후 배포 |

---

## 3. Key Vault 설계

### 3.1 시크릿 분류

#### 공통 시크릿 (모든 프로젝트 사용)
| 시크릿 이름 | 설명 |
|-------------|------|
| APP_PIN | 앱 접속 PIN |
| SECRET_KEY | 세션 암호화 키 |
| GOOGLE-CLIENT-ID | Google OAuth Client ID |
| GOOGLE-CLIENT-SECRET | Google OAuth Client Secret |
| DUCKDNS-TOKEN-KEY | DuckDNS 업데이트 토큰 |
| DOCUMENTINTELLIGENCE-ENDPOINT | Doc Intel 엔드포인트 |
| DOCUMENTINTELLIGENCE-API-KEY | Doc Intel API 키 |

#### 프로젝트별 시크릿
| 시크릿 이름 | 프로젝트 | 설명 |
|-------------|----------|------|
| OCI-TENANCY | devforge | OCI 테넌시 OCID |
| OCI-USER | devforge | OCI 사용자 OCID |
| OCI-FINGERPRINT | devforge | API 키 지문 |
| OCI-KEY-FILE | devforge | API 개인키 (base64) |

### 3.2 Key Vault 보안 설정

```
이름: kv-kuhwa-prod
위치: koreacentral
스킴: standard
RBAC: 활성화 (권장)
Soft Delete: 90일
Purge Protection: 활성화
네트워크: Azure Services Only (prod)
```

### 3.3 앱에서 Key Vault 접근

```python
# 앱 시작 시
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

credential = DefaultAzureCredential()
client = SecretClient(
    vault_url="https://kv-kuhwa-prod.vault.azure.net/",
    credential=credential
)

# 시크릿 로드
app_pin = client.get_secret("APP_PIN").value
```

---

## 4. 마이그레이션 실행 계획

### Phase 1: 리소스 그룹 준비 [완료]

- [x] rg-devforge-prod-krc 생성 (koreacentral)
- [x] rg-kuhwa-prod-krc 생성 (koreacentral)
- [x] rg-server-common-prod-krc 생성 (koreacentral)

### Phase 2: Key Vault 마이그레이션

| 단계 | 작업 | CLI |
|------|------|-----|
| 1 | 기존 KV 시크릿 목록 확인 | `az keyvault secret list --vault-name kv-devforge-prod-krc` |
| 2 | 새 KV 생성 | `az keyvault create -n kv-kuhwa-prod -g rg-server-common-prod-krc -l koreacentral` |
| 3 | 시크릿 복사 | `az keyvault secret set --vault-name kv-kuhwa-prod --name <name> --value <value>` |
| 4 | RBAC 설정 | `az role assignment create --role "Key Vault Secrets User" --assignee <principal>` |
| 5 | 앱 코드 업데이트 | .env에서 새 KV 엔드포인트로 변경 |
| 6 | 테스트 | 앱 재시작 후 시크릿 로드 확인 |
| 7 | 기존 KV 삭제 | `az keyvault delete -n kv-devforge-prod-krc` |

### Phase 3: VM/VNet 마이그레이션

| 단계 | 작업 | CLI |
|------|------|-----|
| 1 | 기존 VM 스냅샷 | `az snapshot create --name snap-vm-backup -g rg-devforge-prod-cin --source vm-devforge-prod-cin` |
| 2 | VM 중지 | `az vm stop -g rg-devforge-prod-cin -n vm-devforge-prod-cin` |
| 3 | 새 VM 생성 | `az vm create -g rg-devforge-prod-krc -n vm-devforge-prod-001 --image <image> --vnet-name vnet-devforge-prod` |
| 4 | 서비스 확인 | 앱 접속 테스트 |
| 5 | 기존 VM 삭제 | `az vm delete -g rg-devforge-prod-cin -n vm-devforge-prod-cin` |

### Phase 4: Doc Intel 마이그레이션

| 단계 | 작업 | CLI |
|------|------|-----|
| 1 | 새 Doc Intel 생성 | `az cognitiveservices account create -n doc-intel-kuhwa -g rg-server-common-prod-krc -k CognitiveServices --kind FormRecognizer --sku F0` |
| 2 | 키 확인 | `az cognitiveservices account keys list -n doc-intel-kuhwa -g rg-server-common-prod-krc` |
| 3 | 앱 코드 업데이트 | .env에서 새 엔드포인트/키로 변경 |
| 4 | 테스트 | PDF 파싱 테스트 |
| 5 | 기존 Doc Intel 삭제 | `az cognitiveservices account delete -n doc-intel-kuhwa -g rg-devforge-prod-cin` |

### Phase 5: 기존 리소스 정리

| 단계 | 작업 | CLI |
|------|------|-----|
| 1 | centralindia 리소스 삭제 | `az group delete -n rg-devforge-prod-cin --no-wait` |
| 2 | 89c6a8ee KV 삭제 | `az group delete -n rg-shared-devforge-prod-krc --subscription 89c6a8ee` |
| 3 | 89c6a8ee 구독 해지 | Azure 포털에서 해지 신청 |
| 4 | NetworkWatcher 확인 | 자동 유지됨 |

---

## 5. 리소스 네이밍 컨벤션

| 리소스 유형 | 네이밍 패턴 | 예시 |
|-------------|-------------|------|
| 리소스 그룹 | rg-{project}-{env}-{region} | rg-devforge-prod-krc |
| Key Vault | kv-{project}-{env} | kv-kuhwa-prod |
| VM | vm-{project}-{env}-{seq} | vm-devforge-prod-001 |
| VNet | vnet-{project}-{env} | vnet-devforge-prod |
| NSG | nsg-{project}-{purpose} | nsg-devforge-web |
| Disk | osdisk_{vm-name}_{hash} | (자동 생성) |
| Snapshot | snap-{vm-name} | snap-qwen3-30b |

---

## 6. 주의사항

| 항목 | 설명 |
|------|------|
| 리소스 그룹 이동 | Azure에서 불가. 반드시 삭제 후 재생성 |
| VM 데이터 | 삭제 전 스냅샷 백업 필수 |
| Key Vault | 소프트 삭제 90일 보존. Purge Protection으로 영구 삭제 방지 |
| 구독 해지 | 89c6a8ee는 모든 리소스 삭제 후 해지 |
| 비용 | Azure for Students $200 크레딧 (30일), 12개월 무료 서비스 |
| 문서 Intel | F0 등급 500페이지/월 무료 |

---

## 7. 검증 체크리스트

- [ ] Key Vault에서 모든 시크릿 로드 가능
- [ ] 앱 정상 동작 (pdf2sheet)
- [ ] PDF 파싱 기능 동작
- [ ] Azure Document Intelligence 연동 동작
- [ ] OCI 업로드/다운로드 동작
- [ ] Google Sheets 연동 동작
- [ ] 기존 리소스 모두 삭제
- [ ] 89c6a8ee 구독 해지
