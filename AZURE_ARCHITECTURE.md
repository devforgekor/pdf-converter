# Azure 서버 운영 아키텍처 계획

## 업계 표준: Key Vault 분리 전략

业界 标准 권장사항:
- **앱당 Key Vault 1개** (blast radius 최소화)
- **환경별 분리** (dev/prod隔离)
- **공통 시크릿은 별도 공유 Vault**

---

## 권장 구조: 3-그룹 분리

```
┌─────────────────────────────────────────────────────┐
│              Azure for Students 구독                  │
│  a942e898-e1ee-47f4-b9b3-d9475672ff4e               │
└─────────────────────────────────────────────────────┘
          │
          ├── Resource Group: rg-shared
          │     └── kv-common-prod          (공통 시크릿)
          │           ├── APP_PIN
          │           ├── GOOGLE_CLIENT_ID
          │           ├── GOOGLE_CLIENT_SECRET
          │           ├── DUCKDNS-TOKEN
          │           └── AZURE-DOC-INTEL-KEY
          │
          ├── Resource Group: rg-server1
          │     ├── kv-kuhwa-prod           (서버1 시크릿)
          │     │     ├── OCI-TENANCY
          │     │     ├── OCI-USER
          │     │     ├── OCI-FINGERPRINT
          │     │     └── OCI-KEY-FILE (base64)
          │     └── Docker: pdf2sheet (port 8000)
          │
          └── Resource Group: rg-server2
                ├── kv-server2-prod         (서버2 시크릿)
                │     └── (서버2 전용 시크릿)
                └── Docker: (추후 배포)
```

## 시크릿 분리 기준

| 그룹 | 시크릿 | 이유 |
|------|--------|------|
| **공통 (kv-common-prod)** | APP_PIN, Google OAuth, DuckDNS, Doc Intel Key | 모든 서버가 공유 |
| **서버1 (kv-kuhwa-prod)** | OCI 설정, DB 설정 | 서버1 고유 |
| **서버2 (kv-server2-prod)** | 서버2 전용 시크릿 | 서버2 고유 |

## 앱에서 Key Vault 접근 방식

### 1. Managed Identity 사용 (권장)
```python
# Azure VM/Docker에서 managed identity으로 접근
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

credential = DefaultAzureCredential()  # managed identity 자동 사용
common_client = SecretClient("https://kv-common-prod.vault.azure.net/", credential)
server_client = SecretClient("https://kv-kuhwa-prod.vault.azure.net/", credential)

app_pin = common_client.get_secret("APP_PIN").value
oci_tenancy = server_client.get_secret("OCI-TENANCY").value
```

### 2. 서비스 프린시펄 사용 (Docker용)
```python
# .env에 SP 설정만 남기고 나머지는 Key Vault에서 로드
from azure.identity import ClientSecretCredential

credential = ClientSecretCredential(
    tenant_id=os.getenv("AZURE_TENANT_ID"),
    client_id=os.getenv("AZURE_CLIENT_ID"),
    client_secret=os.getenv("AZURE_CLIENT_SECRET")
)
client = SecretClient("https://kv-common-prod.vault.azure.net/", credential)
```

## 리소스 네이밍 컨벤션

| 리소스 | 네이밍 | 예시 |
|--------|--------|------|
| Resource Group | `rg-{ workload}-{env}` | `rg-kuhwa-prod` |
| Key Vault | `kv-{app}-{env}` | `kv-common-prod` |
| Docker Container | `{app}-{server}` | `pdf2sheet-s1` |

## `.env` → Key Vault 마이그레이션 순서

1. `az login` (Azure for Students 계정)
2. 리소스 그룹 3개 생성
3. Key Vault 3개 생성 (공통/서버1/서버2)
4. 기존 `.env` 값들을 Key Vault에 저장
5. 앱 코드에 Key Vault 클라이언트 추가
6. `.env`에서 시크릿 항목 제거 (SP 설정만 유지)
7. Docker에 Managed Identity 또는 SP 설정

## 현재 `.env` 항목 분류

### 공통 → kv-common-prod
- APP_PIN
- SECRET_KEY
- GOOGLE_CLIENT_ID
- GOOGLE_CLIENT_SECRET
- GOOGLE_REDIRECT_URI
- DUCKDNS-TOKEN-KEY
- DOCUMENTINTELLIGENCE_ENDPOINT
- DOCUMENTINTELLIGENCE_API_KEY

### 서버1 → kv-kuhwa-prod
- OCI_USER
- OCI_TENANCY
- OCI_FINGERPRINT
- OCI_KEY_FILE (base64 인코딩)
- OCI_NAMESPACE
- OCI_BUCKET
- OCI_REGION
- DATABASE_URL

### 서버2 → kv-server2-prod
- (추후 결정)
