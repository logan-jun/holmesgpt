# 통합 설정 참조 (config.yaml)

HolmesGPT의 모든 설정을 관리하는 config.yaml 파일의 전체 구조와 각 필드를 설명합니다. CLI 직접 실행과 Helm Chart를 통한 Kubernetes 배포 모두에서 이 설정 파일을 사용합니다.

---

## config.yaml 위치

CLI에서 직접 실행하는 경우 기본 경로는 `~/.holmes/config.yaml`입니다. 별도 경로의 설정 파일을 사용하려면 `--config` 옵션으로 지정합니다.

```bash
# 기본 경로 사용
holmes ask "클러스터 상태 확인"

# 별도 경로의 설정 파일 지정
holmes ask "클러스터 상태 확인" --config /path/to/config.yaml
```

Helm Chart로 배포하는 경우에는 `values.yaml`의 `config:` 섹션에 동일한 설정 항목을 작성합니다.

---

## 전체 구조

다음은 config.yaml에서 사용할 수 있는 모든 설정 항목의 전체 구조입니다.

```yaml
# =================================================
# LLM 설정
# =================================================
model: "gpt-oss-120b"           # 사용할 모델명 (modelList의 키 또는 직접 모델명)
api_key: "none"                  # LLM API 키 (또는 OPENAI_API_KEY 환경변수)
api_base: ""                     # LLM API 기본 URL (또는 OPENAI_API_BASE 환경변수)
api_version: ""                  # API 버전 (Azure OpenAI 사용 시)
fast_model: ""                   # 요약 등 경량 작업에 사용할 빠른 모델
max_steps: 40                    # 에이전틱 루프 최대 스텝 수

# =================================================
# 클러스터 식별
# =================================================
cluster_name: "onprem-prod"      # 클러스터 이름 (멀티 클러스터 구분용)

# =================================================
# 소스 설정 (알림 소스)
# =================================================
# AlertManager
alertmanager_url: ""              # AlertManager URL
alertmanager_username: ""         # 인증 사용자명
alertmanager_password: ""         # 인증 비밀번호
alertmanager_alertname: ""        # 특정 알림 이름 필터
alertmanager_label: []            # 라벨 기반 필터 목록

# Jira
jira_url: ""                      # Jira URL (http:// 또는 https:// 필수)
jira_username: ""                 # Jira 사용자명
jira_api_key: ""                  # Jira API 키
jira_query: ""                    # JQL 쿼리 문자열

# GitHub
github_url: ""                    # GitHub URL (http:// 또는 https:// 필수)
github_owner: ""                  # 저장소 소유자
github_pat: ""                    # Personal Access Token
github_repository: ""             # 저장소 이름
github_query: ""                  # 검색 쿼리

# PagerDuty
pagerduty_api_key: ""             # PagerDuty API 키
pagerduty_user_email: ""          # PagerDuty 사용자 이메일
pagerduty_incident_key: ""        # 특정 인시던트 키

# OpsGenie
opsgenie_api_key: ""              # OpsGenie API 키
opsgenie_team_integration_key: "" # 팀 통합 키
opsgenie_query: ""                # OpsGenie 쿼리

# Slack (결과 전송 대상)
slack_token: ""                   # Slack Bot 토큰
slack_channel: ""                 # 결과를 보낼 Slack 채널

# =================================================
# 커스텀 도구셋 / 런북
# =================================================
custom_toolsets:                  # 커스텀 도구셋 파일 경로 목록
  - /path/to/minio-toolset.yaml
  - /path/to/spark-operator-toolset.yaml

custom_runbooks:                  # [DEPRECATED] 커스텀 런북 마크다운 파일 경로
  - /path/to/runbooks/spark-job-failure.md

custom_runbook_catalogs:          # 런북 카탈로그 경로 (JSON) -- custom_runbooks 대체
  - /path/to/runbooks/catalog.json

# =================================================
# 도구셋 설정 (활성화/비활성화 및 설정)
# =================================================
toolsets:
  kubernetes/core:
    enabled: true
  prometheus/metrics:
    enabled: true
    config:
      prometheus_url: "http://prometheus.monitoring.svc:9090"
  grafana/dashboards:
    enabled: true
    config:
      api_url: "http://grafana.monitoring.svc:3000"
      api_key: "{{ env.GRAFANA_API_KEY }}"

# =================================================
# MCP 서버 설정
# =================================================
mcp_servers: {}
```

---

## LLM 설정 필드

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `model` | string | `null` | 사용할 모델명. `modelList`에 정의한 별칭 또는 LiteLLM 형식의 모델명 |
| `api_key` | string | `null` | LLM API 키. 미설정 시 `OPENAI_API_KEY` 또는 `AZURE_API_KEY` 환경변수 사용 |
| `api_base` | string | `null` | LLM API 엔드포인트 기본 URL |
| `api_version` | string | `null` | API 버전 (Azure OpenAI 전용) |
| `fast_model` | string | `null` | 요약 등 경량 작업에 사용할 모델. 미설정 시 `model` 사용 |
| `max_steps` | int | `40` | 에이전틱 루프 최대 스텝 수. LLM이 도구를 호출하며 조사하는 최대 반복 횟수 |

---

## 클러스터 설정

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `cluster_name` | string | `null` | 클러스터 이름. 멀티 클러스터 환경에서 구분 식별자로 사용 |

`cluster_name`은 `CLUSTER_NAME` 환경변수로도 설정할 수 있습니다. 환경변수가 설정되어 있으면 config.yaml 값보다 우선합니다.

---

## 알림 소스 설정

### AlertManager

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `alertmanager_url` | string | `null` | AlertManager API URL |
| `alertmanager_username` | string | `null` | Basic Auth 사용자명 |
| `alertmanager_password` | string | `null` | Basic Auth 비밀번호 |
| `alertmanager_alertname` | string | `null` | 특정 알림 이름으로 필터링 |
| `alertmanager_label` | list | `[]` | 라벨 기반 필터 (예: `["severity=critical"]`) |

### Jira

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `jira_url` | string | `null` | Jira 인스턴스 URL (`http://` 또는 `https://` 필수) |
| `jira_username` | string | `null` | Jira 사용자명 |
| `jira_api_key` | string | `null` | Jira API 토큰 |
| `jira_query` | string | `""` | JQL 쿼리 문자열 |

### PagerDuty

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `pagerduty_api_key` | string | `null` | PagerDuty API 키 |
| `pagerduty_user_email` | string | `null` | PagerDuty 사용자 이메일 |
| `pagerduty_incident_key` | string | `null` | 특정 인시던트 키 |

### OpsGenie

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `opsgenie_api_key` | string | `null` | OpsGenie API 키 |
| `opsgenie_team_integration_key` | string | `null` | 팀 통합 키 |
| `opsgenie_query` | string | `null` | OpsGenie 알림 쿼리 |

### GitHub

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `github_url` | string | `null` | GitHub 인스턴스 URL (`http://` 또는 `https://` 필수) |
| `github_owner` | string | `null` | 저장소 소유자 (조직 또는 사용자) |
| `github_pat` | string | `null` | Personal Access Token |
| `github_repository` | string | `null` | 대상 저장소 이름 |
| `github_query` | string | `""` | 이슈/PR 검색 쿼리 |

---

## Slack 전송 설정

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `slack_token` | string | `null` | Slack Bot 토큰 |
| `slack_channel` | string | `null` | 결과를 전송할 Slack 채널명 |

---

## 커스텀 도구셋 / 런북

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `custom_toolsets` | list | `null` | 커스텀 도구셋 YAML 파일 경로 목록 |
| `custom_runbooks` | list | `[]` | **[DEPRECATED]** 커스텀 런북 마크다운 파일 경로 목록. `custom_runbook_catalogs` 사용 권장 |
| `custom_runbook_catalogs` | list | `[]` | 런북 카탈로그 파일 경로 목록 (JSON 또는 URL) |

`custom_runbooks`는 더 이상 사용되지 않습니다. LLM이 상황에 맞는 런북을 지능적으로 검색하는 카탈로그 기반 시스템인 `custom_runbook_catalogs`를 대신 사용하십시오.

---

## 도구셋 설정

`toolsets` 섹션에서 내장 도구셋의 활성화/비활성화와 개별 설정을 관리합니다.

```yaml
toolsets:
  <toolset-name>:
    enabled: true|false
    config:
      <toolset-specific-options>
```

각 도구셋의 `config` 하위 항목은 도구셋마다 다릅니다. 자주 사용하는 도구셋의 설정 옵션은 아래와 같습니다.

### prometheus/metrics

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `prometheus_url` | - | Prometheus 서버 URL |
| `additional_headers` | `{}` | 인증 등 추가 HTTP 헤더 |
| `discover_metrics_from_last_hours` | `1` | 메트릭 검색 시간 범위 (시간) |
| `query_timeout_seconds_default` | `20` | PromQL 쿼리 타임아웃 (초) |
| `rules_cache_duration_seconds` | `1800` | 규칙 캐시 유지 시간 (초) |
| `verify_ssl` | `true` | SSL 인증서 검증 활성화 |

### grafana/dashboards

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `api_url` | - | Grafana 서버 URL |
| `api_key` | - | Grafana 서비스 계정 토큰 |
| `external_url` | `null` | 외부 접근용 Grafana URL (내부 URL과 다른 경우) |

### grafana/loki

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `api_url` | - | Grafana 또는 Loki 직접 접근 URL |
| `api_key` | `null` | Grafana 서비스 계정 토큰 (Grafana 프록시 방식) |
| `grafana_datasource_uid` | `null` | Loki 데이터소스 UID (Grafana 프록시 방식) |
| `additional_headers` | `{}` | 추가 HTTP 헤더 (멀티테넌시 등) |

### bash

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `allow` | `[]` | 허용 명령어 접두사 목록 |
| `deny` | `[]` | 차단 명령어 접두사 목록 |
| `include_default_allow_deny_list` | `false` | 기본 읽기 전용 명령어 자동 포함 |

도구셋의 전체 목록과 상세 설정은 [05-builtin-toolsets.md](05-builtin-toolsets.md)를 참고하십시오.

---

## MCP 서버 설정

`mcp_servers` 섹션에서 외부 MCP(Model Context Protocol) 서버를 등록합니다. 등록된 MCP 서버의 도구는 HolmesGPT가 자동으로 로드하여 사용합니다.

```yaml
mcp_servers:
  my-mcp-server:
    command: "npx"
    args: ["-y", "@my-org/mcp-server"]
    env:
      API_TOKEN: "{{ env.MCP_API_TOKEN }}"
```

---

## 환경변수 참조 패턴

config.yaml 내에서 환경변수를 참조하는 두 가지 패턴이 있습니다.

**Jinja2 패턴** -- 도구셋 YAML의 `config` 필드, `llm_instructions` 등 HolmesGPT가 렌더링하는 영역에서 사용합니다.

```yaml
config:
  api_key: "{{ env.GRAFANA_API_KEY }}"
  api_url: "{{ env.GRAFANA_URL }}"
```

**Shell 패턴** -- 도구셋의 `command` 필드에서 셸이 직접 치환하는 영역에 사용합니다.

```yaml
tools:
  - name: check_minio_status
    command: "mc ls ${MC_ALIAS}"
```

두 패턴의 차이점을 요약합니다.

| 항목 | Jinja2 (`{{ env.VAR }}`) | Shell (`${VAR}`) |
|------|--------------------------|-------------------|
| 치환 시점 | YAML 로드 시 | 명령어 실행 시 |
| 사용 위치 | `config`, `llm_instructions` | `command` |
| 미설정 시 동작 | 빈 문자열 | 셸 기본 동작 |

---

## CLI config.yaml과 Helm values.yaml 변환 관계

CLI에서 사용하는 config.yaml 항목이 Helm Chart의 values.yaml에서 어떻게 매핑되는지 정리합니다.

| CLI config.yaml | Helm values.yaml | 비고 |
|-----------------|-------------------|------|
| `model: "gpt-oss-120b"` | `config: { model: "gpt-oss-120b" }` | `config:` 하위에 작성 |
| `api_key: "..."` | `additionalEnvVars:` + `OPENAI_API_KEY` | 환경변수로 주입 권장 |
| `custom_toolsets: [path]` | `toolsets:` 섹션에 직접 정의 | 파일 경로 대신 인라인 정의 |
| `custom_runbook_catalogs: [path]` | ConfigMap/Volume으로 마운트 | `additionalVolumeMounts` 사용 |
| 환경변수 직접 설정 | `additionalEnvVars:` 섹션 | Secret 참조 가능 |
| `toolsets:` | `toolsets:` | 동일한 구조 |
| `mcp_servers:` | `mcp_servers:` (config 내) | 동일한 구조 |

---

## Helm values.yaml 주요 필드

Kubernetes에 Helm Chart로 배포할 때 사용하는 values.yaml의 주요 설정 항목을 설명합니다.

```yaml
# =================================================
# 환경변수
# =================================================
additionalEnvVars:
  - name: OPENAI_API_BASE
    value: "http://vllm:8000/v1"
  - name: OPENAI_API_KEY
    value: "none"

# =================================================
# 모델 목록 (LiteLLM 별칭)
# =================================================
modelList:
  gpt-oss-120b:
    api_key: "{{ env.OPENAI_API_KEY }}"
    api_base: "{{ env.OPENAI_API_BASE }}"
    model: openai/gpt-oss-120b
    temperature: 1

# =================================================
# HolmesGPT 설정
# =================================================
config:
  model: "gpt-oss-120b"
  max_steps: 40

# =================================================
# 도구셋 설정
# =================================================
toolsets:
  kubernetes/core:
    enabled: true
  prometheus/metrics:
    enabled: true
    config:
      prometheus_url: "http://prometheus.monitoring.svc:9090"

# =================================================
# RBAC 설정
# =================================================
crdPermissions:
  argo: true
  flux: true
  kafka: false
  keda: true

customClusterRoleRules:
  - apiGroups: ["sparkoperator.k8s.io"]
    resources: ["sparkapplications"]
    verbs: ["get", "list", "watch"]

# =================================================
# 리소스 제한
# =================================================
resources:
  requests:
    cpu: 100m
    memory: 2048Mi
  limits:
    memory: 2048Mi

# =================================================
# 자체 서명 인증서
# =================================================
certificate: ""   # base64로 인코딩한 CA 인증서

# =================================================
# 볼륨 (커스텀 도구셋/런북 마운트)
# =================================================
additionalVolumes: []
additionalVolumeMounts: []
```

### modelList 구조

`modelList`는 LiteLLM 모델 별칭을 정의합니다. 키가 별칭 이름이며, `config.model`에서 이 별칭을 참조합니다.

| 필드 | 설명 |
|------|------|
| `model` | LiteLLM 형식의 모델명 (예: `openai/gpt-oss-120b`) |
| `api_key` | 모델별 API 키 (환경변수 참조 가능) |
| `api_base` | 모델별 API 엔드포인트 URL |
| `temperature` | 생성 온도 파라미터 |

`openai/` 접두사는 LiteLLM의 OpenAI-compatible 프로바이더를 나타냅니다. vLLM, Ollama 등 OpenAI API를 호환하는 서버에는 이 접두사를 사용합니다.

### additionalEnvVars 구조

환경변수를 직접 값으로 설정하거나 Kubernetes Secret에서 참조할 수 있습니다.

```yaml
additionalEnvVars:
  # 직접 값 설정
  - name: OPENAI_API_BASE
    value: "http://vllm:8000/v1"

  # Kubernetes Secret 참조
  - name: ARGOCD_AUTH_TOKEN
    valueFrom:
      secretKeyRef:
        name: holmes-secrets
        key: argocd-token
```

민감한 정보(API 키, 토큰 등)는 `valueFrom.secretKeyRef`를 통해 Kubernetes Secret에서 참조하는 것을 권장합니다.

---

## 환경변수 목록

config.yaml 외에 환경변수로 직접 설정할 수 있는 항목입니다. 환경변수가 설정되어 있으면 config.yaml 값보다 우선합니다.

| 환경변수 | config.yaml 대응 필드 | 설명 |
|----------|----------------------|------|
| `OPENAI_API_KEY` | `api_key` | OpenAI API 키 |
| `AZURE_API_KEY` | `api_key` | Azure OpenAI API 키 |
| `ANTHROPIC_API_KEY` | - | Anthropic API 키 |
| `OPENROUTER_API_KEY` | - | OpenRouter API 키 |
| `MODEL` | `model` | 기본 모델명 |
| `FAST_MODEL` | `fast_model` | 경량 모델명 |
| `MAX_STEPS` | `max_steps` | 최대 스텝 수 |
| `CLUSTER_NAME` | `cluster_name` | 클러스터 이름 |
| `ALERTMANAGER_URL` | `alertmanager_url` | AlertManager URL |
| `ALERTMANAGER_USERNAME` | `alertmanager_username` | AlertManager 사용자명 |
| `ALERTMANAGER_PASSWORD` | `alertmanager_password` | AlertManager 비밀번호 |
| `JIRA_URL` | `jira_url` | Jira URL |
| `JIRA_USERNAME` | `jira_username` | Jira 사용자명 |
| `JIRA_API_KEY` | `jira_api_key` | Jira API 키 |
| `SLACK_TOKEN` | `slack_token` | Slack 토큰 |
| `SLACK_CHANNEL` | `slack_channel` | Slack 채널 |
| `GITHUB_URL` | `github_url` | GitHub URL |
| `GITHUB_OWNER` | `github_owner` | GitHub 소유자 |
| `GITHUB_REPOSITORY` | `github_repository` | GitHub 저장소 |
| `GITHUB_PAT` | `github_pat` | GitHub PAT |
| `CERTIFICATE` | - | base64 CA 인증서 (Helm `certificate` 대응) |

---

## CLI 옵션과 config.yaml 관계

CLI 옵션으로 전달한 값은 config.yaml에 정의된 값을 덮어씁니다 (CLI 우선).

```bash
# config.yaml의 model 값을 CLI 옵션으로 덮어쓰기
holmes ask "상태 확인" --model anthropic/claude-sonnet-4-5-20250929

# 커스텀 도구셋 추가 (config.yaml의 custom_toolsets에 추가됨)
holmes ask "MinIO 상태" --custom-toolsets /path/to/minio-toolset.yaml
```

주요 CLI 옵션과 대응되는 config.yaml 필드는 다음과 같습니다.

| CLI 옵션 | config.yaml 필드 | 설명 |
|----------|------------------|------|
| `--model` | `model` | 모델명 |
| `--api-key` | `api_key` | API 키 |
| `--max-steps` | `max_steps` | 최대 스텝 수 |
| `--config` | - | 설정 파일 경로 지정 |
| `--custom-toolsets`, `-t` | `custom_toolsets` | 커스텀 도구셋 경로 |
| `--custom-runbooks`, `-r` | `custom_runbooks` | **[DEPRECATED]** 런북 경로 |

---

## 전체 통합 설정 예시

다음은 온프레미스 환경에서 vLLM, Prometheus, Grafana, ArgoCD, 커스텀 도구셋을 모두 사용하는 CLI config.yaml 예시입니다.

```yaml
# ~/.holmes/config.yaml
model: "gpt-oss-120b"
api_key: "none"
api_base: "http://vllm-server.inference.svc.cluster.local:8000/v1"
max_steps: 40
cluster_name: "onprem-prod"

toolsets:
  kubernetes/core:
    enabled: true
  kubernetes/logs:
    enabled: true
  kubernetes/live-metrics:
    enabled: true
  helm/core:
    enabled: true
  prometheus/metrics:
    enabled: true
    config:
      prometheus_url: "http://prometheus-server.monitoring.svc.cluster.local:9090"
  grafana/dashboards:
    enabled: true
    config:
      api_url: "http://grafana.monitoring.svc.cluster.local:3000"
      api_key: "{{ env.GRAFANA_API_KEY }}"
  argocd/core:
    enabled: true

custom_toolsets:
  - /home/user/.holmes/toolsets/minio-toolset.yaml
  - /home/user/.holmes/toolsets/spark-operator-toolset.yaml

custom_runbook_catalogs:
  - /home/user/.holmes/runbooks/catalog.json
```

Helm Chart values.yaml로 변환한 예시는 [03-deployment-onprem.md](03-deployment-onprem.md)의 배포 절차를 참고하십시오.
