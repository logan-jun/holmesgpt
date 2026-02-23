# 내장 도구셋 활용 가이드

HolmesGPT에는 사내 인프라 환경에서 바로 활용할 수 있는 내장 도구셋이 포함되어 있습니다. 이 문서에서는 각 내장 도구셋의 주요 도구와 활성화 방법을 설명합니다.

---

## kubernetes/core

클러스터 리소스에 대한 읽기 전용 접근을 제공합니다. Secret 등 민감한 데이터는 제외됩니다.

**사전 조건:** kubectl 설치 및 클러스터 접근 권한

**주요 도구:**

| 도구 이름 | 설명 |
|-----------|------|
| kubectl_describe | 리소스 상세 정보 조회 (`kubectl describe`) |
| kubectl_get_by_name | 이름으로 특정 리소스 조회 (라벨 포함) |
| kubectl_get_by_kind_in_namespace | 네임스페이스 내 특정 종류 리소스 전체 조회 |
| kubectl_get_by_kind_in_cluster | 클러스터 전체에서 특정 종류 리소스 조회 |
| kubectl_find_resource | 키워드로 리소스 검색 (이름, IP, 네임스페이스, 라벨 부분 일치) |
| kubectl_get_yaml | 리소스의 YAML 정의 조회 |
| kubectl_events | 특정 리소스의 이벤트 조회 |
| kubernetes_jq_query | JSON 출력에 jq 필터를 적용하여 리소스 질의 |
| kubernetes_tabular_query | 커스텀 컬럼으로 테이블 형식 출력 (필터링 지원) |
| kubernetes_count | jq 필터를 적용한 리소스 카운트 |

**설정 (기본 활성화):**

```yaml
toolsets:
  kubernetes/core:
    enabled: true
```

---

## kubernetes/logs

Kubernetes 파드 로그를 읽기 위한 도구셋입니다. 현재 로그, 이전(크래시 전) 로그, 특정 컨테이너 로그, 로그 검색 기능을 제공합니다.

**사전 조건:** kubectl 설치 및 클러스터 접근 권한

**주요 도구:**

| 도구 이름 | 설명 |
|-----------|------|
| kubectl_logs | 단일 파드의 로그 조회 |
| kubectl_logs_all_containers | 파드 내 모든 컨테이너의 로그 조회 |
| kubectl_previous_logs | 크래시 이전 로그 조회 (`--previous`) |
| kubectl_previous_logs_all_containers | 모든 컨테이너의 크래시 이전 로그 조회 |
| kubectl_container_logs | 특정 컨테이너의 로그 조회 |
| kubectl_container_previous_logs | 특정 컨테이너의 크래시 이전 로그 조회 |
| kubectl_logs_grep | 파드 로그에서 특정 패턴 검색 |
| kubectl_logs_all_containers_grep | 모든 컨테이너 로그에서 특정 패턴 검색 |

**설정 (기본 활성화):**

```yaml
toolsets:
  kubernetes/logs:
    enabled: true
```

Loki를 로그 소스로 사용하는 경우, `kubernetes/logs`를 비활성화하고 `grafana/loki`를 대신 사용해야 합니다.

---

## kubernetes/live-metrics

파드와 노드의 실시간 CPU/메모리 사용량을 조회합니다.

**사전 조건:** 클러스터에 metrics-server가 설치되어 있어야 합니다.

**주요 도구:**

| 도구 이름 | 설명 |
|-----------|------|
| kubectl_top_pods | 모든 파드의 실시간 CPU/메모리 사용량 조회 |
| kubectl_top_nodes | 모든 노드의 실시간 CPU/메모리 사용량 조회 |

현재 스냅샷만 제공하며, 시계열 데이터나 그래프 생성에는 사용할 수 없습니다. 시계열 분석이 필요한 경우 Prometheus 도구셋을 사용하십시오.

**설정:**

```yaml
toolsets:
  kubernetes/live-metrics:
    enabled: true
```

---

## helm/core

Helm 릴리스의 관리 정보를 조회하는 도구셋입니다. 배포 이력 확인, values 비교, 롤백 필요성 판단 등에 활용할 수 있습니다.

**사전 조건:** helm CLI 설치

**주요 도구:**

| 도구 이름 | 설명 |
|-----------|------|
| helm_list | 현재 모든 Helm 릴리스 목록 조회 |
| helm_values | Helm 릴리스의 values 조회 (JSON 형식) |
| helm_status | Helm 릴리스 상태 확인 |
| helm_history | Helm 릴리스의 리비전 이력 조회 |
| helm_manifest | Helm 릴리스에서 생성된 Kubernetes 매니페스트 조회 |
| helm_hooks | Helm 릴리스의 훅(hook) 조회 |
| helm_chart | Helm 릴리스에 사용된 차트 정보 조회 |
| helm_notes | Helm 차트에서 제공하는 안내 메시지 조회 |

**설정 (기본 활성화):**

```yaml
toolsets:
  helm/core:
    enabled: true
```

Kubernetes(Helm Chart)로 배포하는 경우 Helm이 Secret을 통해 릴리스 정보를 저장하므로, 추가 ClusterRole 권한이 필요할 수 있습니다.

```yaml
holmes:
  toolsets:
    helm/core:
      enabled: true
  customClusterRoleRules:
    - apiGroups: [""]
      resources: ["secrets"]
      verbs: ["get", "list", "watch"]
```

---

## argocd/core

ArgoCD 애플리케이션의 상태 조회, 배포 이력 확인, Git 저장소와의 비교 등 GitOps 기반 배포 디버깅을 위한 도구셋입니다.

**사전 조건:**

- argocd CLI 설치
- `ARGOCD_AUTH_TOKEN` 환경변수 설정

**주요 도구:**

| 도구 이름 | 설명 |
|-----------|------|
| argocd_app_list | 모든 ArgoCD 애플리케이션 목록 조회 |
| argocd_app_get | 애플리케이션 상태 및 설정 조회 |
| argocd_app_diff | Git 저장소의 선언 상태와 현재 클러스터 상태 비교 |
| argocd_app_manifests | 애플리케이션 매니페스트 조회 |
| argocd_app_resources | 애플리케이션 리소스 목록 조회 |
| argocd_app_manifest_source_revision | 멀티소스 애플리케이션의 특정 리비전 매니페스트 조회 |
| argocd_app_history | 애플리케이션 배포 이력 조회 |
| argocd_repo_list | ArgoCD에 등록된 Git 저장소 목록 조회 |
| argocd_proj_list | 모든 프로젝트 목록 조회 |
| argocd_proj_get | 특정 프로젝트의 상세 정보 조회 |
| argocd_cluster_list | 등록된 클러스터 목록 조회 |

**설정 (Helm Chart):**

```yaml
holmes:
  additionalEnvVars:
    - name: ARGOCD_AUTH_TOKEN
      valueFrom:
        secretKeyRef:
          name: holmes-secrets
          key: argocd-token
    - name: ARGOCD_OPTS
      value: "--port-forward --port-forward-namespace argocd --server argocd-server.argocd.svc.cluster.local --grpc-web"
  toolsets:
    argocd/core:
      enabled: true
```

**설정 (CLI):**

```bash
export ARGOCD_AUTH_TOKEN="<your-argocd-token>"
export ARGOCD_SERVER="argocd.example.com"
```

```yaml
toolsets:
  argocd/core:
    enabled: true
```

---

## prometheus/metrics

PromQL 쿼리 실행, 메트릭 메타데이터 조회, Prometheus 규칙 조회 등 메트릭 기반 분석을 위한 도구셋입니다.

**사전 조건:** Prometheus 엔드포인트에 접근 가능해야 합니다.

**주요 도구:**

| 도구 이름 | 설명 |
|-----------|------|
| list_prometheus_rules | 정의된 모든 Prometheus 규칙(알림 규칙 포함) 조회 |
| get_metric_names | 메트릭 이름 목록 조회 (match 필터 필요) |
| get_label_values | 특정 라벨의 모든 값 조회 (예: 파드 이름, 네임스페이스) |
| get_all_labels | 사용 가능한 모든 라벨 이름 조회 |
| get_series | 셀렉터와 일치하는 시계열 조회 (전체 라벨셋 반환) |
| get_metric_metadata | 메트릭의 메타데이터(타입, 설명, 단위) 조회 |
| execute_prometheus_instant_query | 특정 시점의 즉시 PromQL 쿼리 실행 |
| execute_prometheus_range_query | 시간 범위 PromQL 쿼리 실행 (그래프 생성 지원) |

**설정:**

```yaml
toolsets:
  prometheus/metrics:
    enabled: true
    config:
      prometheus_url: "http://prometheus-server.monitoring.svc.cluster.local:9090"
```

인증이 필요한 경우 `additional_headers`를 설정합니다.

```yaml
toolsets:
  prometheus/metrics:
    enabled: true
    config:
      prometheus_url: "http://prometheus-server.monitoring.svc.cluster.local:9090"
      additional_headers:
        Authorization: "Basic <base64_encoded_credentials>"
```

**고급 설정 옵션:**

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `prometheus_url` | - | Prometheus 서버 URL (프로토콜과 포트 포함) |
| `additional_headers` | `{}` | 인증 헤더 |
| `discover_metrics_from_last_hours` | `1` | 최근 N시간 이내 데이터가 있는 메트릭만 검색 |
| `query_timeout_seconds_default` | `20` | PromQL 쿼리 기본 타임아웃(초) |
| `rules_cache_duration_seconds` | `1800` | 규칙 캐시 유지 시간(초) |
| `verify_ssl` | `true` | SSL 인증서 검증 활성화 |

AWS Managed Prometheus, Google Managed Prometheus, Azure Managed Prometheus, Grafana Cloud(Mimir) 등 관리형 서비스와도 연동할 수 있습니다. 각 환경별 상세 설정은 영문 문서를 참고하십시오.

---

## grafana/dashboards

Grafana 대시보드를 검색하고 조회하는 도구셋입니다. 대시보드에 포함된 Prometheus 쿼리를 추출하여 추가 분석에 활용할 수 있습니다.

**사전 조건:** Viewer 이상의 권한을 가진 Grafana 서비스 계정 토큰

**주요 도구:**

| 도구 이름 | 설명 |
|-----------|------|
| grafana_search_dashboards | 쿼리, 태그, UID, 폴더 기준으로 대시보드 검색 |
| grafana_get_dashboard_by_uid | UID로 대시보드 전체 JSON 조회 (패널, 쿼리 포함) |
| grafana_get_home_dashboard | 홈 대시보드 설정 조회 |
| grafana_get_dashboard_tags | 대시보드에 사용된 모든 태그 목록 조회 |

**설정 (CLI):**

```yaml
toolsets:
  grafana/dashboards:
    enabled: true
    config:
      api_url: "http://localhost:3000"
      api_key: "<your-grafana-service-account-token>"
```

**설정 (Helm Chart):**

```yaml
holmes:
  toolsets:
    grafana/dashboards:
      enabled: true
      config:
        api_url: "http://grafana.monitoring.svc.cluster.local:3000"
        api_key: "{{ env.GRAFANA_API_KEY }}"
```

내부 URL과 외부 URL이 다른 경우, `external_url` 옵션을 설정하면 결과에 포함되는 링크가 외부 URL을 사용합니다.

```yaml
toolsets:
  grafana/dashboards:
    enabled: true
    config:
      api_url: "http://grafana.internal:3000"
      external_url: "https://grafana.example.com"
      api_key: "<your-api-key>"
```

---

## grafana/loki

Loki를 통해 LogQL 로그 쿼리를 실행하는 도구셋입니다. Grafana 프록시를 통한 접근과 Loki 직접 접근 두 가지 방식을 지원합니다.

**사전 조건:**

- Loki 인스턴스에 Kubernetes 로그가 수집되고 있어야 합니다.
- Grafana 프록시 방식: Grafana 서비스 계정 토큰 및 Loki 데이터소스 UID
- 직접 접근 방식: Loki API 엔드포인트 접근 가능

**주요 도구:**

| 도구 이름 | 설명 |
|-----------|------|
| fetch_pod_logs | Loki에서 파드 로그를 조회 |

Loki를 로그 소스로 사용하는 경우, `kubernetes/logs` 도구셋을 반드시 비활성화해야 합니다.

**설정 (Grafana 프록시):**

```yaml
toolsets:
  grafana/loki:
    enabled: true
    config:
      api_key: "<your-grafana-api-key>"
      api_url: "https://your-grafana-instance.grafana.net"
      grafana_datasource_uid: "<loki-datasource-uid>"

  kubernetes/logs:
    enabled: false
```

**설정 (Loki 직접 접근):**

```yaml
toolsets:
  grafana/loki:
    enabled: true
    config:
      api_url: "http://loki.logging.svc.cluster.local:3100"

  kubernetes/logs:
    enabled: false
```

멀티테넌시가 활성화된 환경에서는 `additional_headers`에 테넌트 ID를 설정합니다.

```yaml
toolsets:
  grafana/loki:
    enabled: true
    config:
      api_url: "http://loki.logging.svc.cluster.local:3100"
      additional_headers:
        X-Scope-OrgID: "<tenant-id>"
```

---

## bash

안전한 bash 명령어 실행을 위한 도구셋입니다. 허용 목록과 차단 목록으로 실행 가능한 명령어를 제어합니다.

**주요 도구:**

| 도구 이름 | 설명 |
|-----------|------|
| bash | 검증된 셸 명령어 실행 |

명령어는 접두사(prefix) 기반으로 검증됩니다. 예를 들어 `kubectl get`이 허용 목록에 있으면 `kubectl get pods`, `kubectl get pods -n production` 등이 모두 허용됩니다. 파이프(`|`)로 연결된 명령어는 각 세그먼트가 개별적으로 검증됩니다.

`sudo`, `su`, 서브셸(`$(...)`, 백틱)은 항상 차단되며 허용 목록으로 우회할 수 없습니다.

**설정 (CLI):**

```yaml
toolsets:
  bash:
    enabled: true
    config:
      allow:
        - "kubectl get"
        - "kubectl describe"
        - "kubectl logs"
        - "grep"
        - "cat"
      deny:
        - "kubectl get secret"
        - "kubectl describe secret"
```

**설정 (Helm Chart):**

```yaml
holmes:
  toolsets:
    bash:
      enabled: true
      config:
        include_default_allow_deny_list: true
        allow:
          - "my-custom-command"
        deny:
          - "kubectl get secret"
```

`include_default_allow_deny_list: true`로 설정하면 기본 읽기 전용 명령어(kubectl get, grep, jq, ls 등)가 자동으로 허용 목록에 포함됩니다.

---

## 도구셋 상태 확인

활성화된 도구셋과 각 도구의 목록을 CLI에서 확인할 수 있습니다.

```bash
# 활성화된 도구셋 확인
holmes toolset list

# 각 도구셋의 도구 목록까지 상세 확인
holmes toolset list --verbose
```

---

## 추가 도구셋 참고

이 문서에서 다룬 도구셋 외에도 HolmesGPT는 다음과 같은 내장 도구셋을 제공합니다.

- **elasticsearch**: Elasticsearch/OpenSearch 클러스터 상태 및 쿼리
- **datadog**: Datadog 메트릭 및 로그 조회
- **aws**: AWS 리소스 조회 (EC2, ECS, RDS 등)
- **gcp**: Google Cloud 리소스 조회
- **docker**: Docker 컨테이너 및 이미지 관리
- **kafka**: Kafka 클러스터 및 토픽 조회
- **rabbitmq**: RabbitMQ 큐 및 연결 조회
- **servicenow**: ServiceNow 테이블 데이터 조회
- **confluence**: Confluence 페이지 검색 및 조회
- **newrelic**: New Relic 메트릭 및 알림 조회
- **grafana/tempo**: Grafana Tempo를 통한 분산 트레이싱 조회

각 도구셋의 상세 설정은 [HolmesGPT 공식 문서](https://holmesgpt.dev/data-sources/builtin-toolsets/)를 참고하십시오.
