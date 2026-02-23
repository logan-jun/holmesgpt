# HolmesGPT 개요

## 소개

HolmesGPT는 AI 기반 인프라 자동 진단 에이전트입니다.
Kubernetes, Prometheus, Grafana 등 관찰가능성(Observability) 플랫폼에 연결하여, 에이전틱 루프(Agentic Loop)를 통해 여러 데이터 소스에서 정보를 수집하고 인프라 및 애플리케이션 이슈를 자동으로 진단합니다.

운영자가 자연어로 질문하면 HolmesGPT가 관련 도구를 호출하여 데이터를 수집하고, 수집된 정보를 기반으로 근본 원인을 분석한 뒤 결론을 제시합니다.

## 주요 기능

### ask -- 자연어 질문으로 인프라 조사

자연어로 질문하면 HolmesGPT가 사용 가능한 도구셋을 활용하여 조사를 수행합니다.

```bash
holmes ask "production 네임스페이스에서 CrashLoopBackOff 상태인 파드를 찾아서 원인을 분석해줘"
```

```bash
holmes ask "최근 1시간 내 Prometheus에서 firing 상태인 알림을 요약해줘"
```

### investigate -- AlertManager 알림 자동 조사

AlertManager에서 현재 firing 상태인 알림을 가져와 각 알림에 대해 자동으로 조사를 수행합니다.

```bash
holmes investigate alertmanager --alertmanager-url http://alertmanager:9093
```

### 도구셋 시스템

HolmesGPT는 YAML 기반 도구셋(Toolset) 시스템을 통해 외부 시스템과 연동합니다.

**내장 도구셋**

별도 설정 없이 바로 사용할 수 있는 도구셋입니다.

- Kubernetes (core, logs): 클러스터 리소스 조회, 파드 로그 확인
- Helm: 릴리스 상태 조회, 릴리스 히스토리 확인
- bash: 안전한 셸 명령 실행 (읽기 전용 명령만 허용)

**설정이 필요한 내장 도구셋**

API 키 또는 URL 설정이 필요한 도구셋입니다.

- Prometheus: PromQL 쿼리 실행, 메트릭 조회
- Grafana Dashboards: 대시보드 목록 및 패널 데이터 조회
- Grafana Loki: 로그 쿼리 실행
- ArgoCD: 애플리케이션 상태 및 동기화 상태 확인
- Elasticsearch / OpenSearch: 인덱스 상태 및 로그 검색

**커스텀 도구셋**

사내 고유 시스템을 위한 도구셋을 YAML, HTTP, 또는 Python으로 직접 작성할 수 있습니다.
`config.yaml`의 `custom_toolsets` 필드에 파일 경로를 지정하면 HolmesGPT가 로드합니다.

```yaml
# ~/.holmes/config.yaml
custom_toolsets:
  - /etc/holmes/toolsets/minio-toolset.yaml
  - /etc/holmes/toolsets/spark-operator-toolset.yaml
```

### 런북 시스템

Markdown 기반 조사 가이드인 런북(Runbook)을 정의하면 HolmesGPT가 알림 조사 시 관련 런북을 자동으로 참조합니다.
`catalog.json`을 통해 런북 카탈로그를 관리하며, LLM이 on-demand로 관련 런북을 가져옵니다.

```yaml
# ~/.holmes/config.yaml
custom_runbook_catalogs:
  - /etc/holmes/runbooks/catalog.json
```

### 대화형 모드

`--interactive` 플래그를 사용하면 지속적인 대화형 조사가 가능합니다.
이전 문맥을 유지하면서 추가 질문을 통해 심층 분석을 수행할 수 있습니다.

```bash
holmes ask --interactive "spark-driver 파드가 왜 실패했는지 알려줘"
```

## 사내 환경 활용 시나리오

### 멀티 클러스터 운영 (On-prem + EKS)

On-prem Kubernetes 클러스터와 Amazon EKS를 동시에 운영하는 환경에서, kubeconfig 컨텍스트를 전환하며 각 클러스터의 이슈를 조사할 수 있습니다.
내장 Kubernetes 도구셋은 현재 활성 kubeconfig 컨텍스트의 클러스터를 대상으로 동작합니다.

```bash
# On-prem 클러스터 조사
kubectl config use-context onprem-prod
holmes ask "kube-system 네임스페이스의 coredns 상태를 확인해줘"

# EKS 클러스터 조사
kubectl config use-context eks-prod
holmes ask "data-pipeline 네임스페이스의 파드 상태를 확인해줘"
```

### Spark 작업 실패 자동 진단

Spark Operator가 관리하는 SparkApplication의 실패 원인을 Kubernetes 이벤트, 드라이버 로그, Executor 로그를 종합하여 분석합니다.

```bash
holmes ask "spark-jobs 네임스페이스에서 실패한 SparkApplication을 찾고 드라이버 로그를 분석해줘"
```

### ArgoCD 배포 이슈 조사

ArgoCD에서 OutOfSync 또는 Degraded 상태인 애플리케이션을 식별하고, desired state와 live state의 diff를 확인하여 배포 문제를 진단합니다.

```bash
holmes ask "ArgoCD에서 Sync 실패한 앱이 있는지 확인하고 원인을 분석해줘"
```

### JupyterHub 사용자 세션 문제 해결

JupyterHub 사용자의 노트북 서버 파드 상태를 확인하고, 세션 시작 실패나 리소스 부족 문제를 진단합니다.

```bash
holmes ask "jhub 네임스페이스에서 Pending 상태인 jupyter 파드를 찾아서 원인을 알려줘"
```

### FastAPI 서비스 헬스체크

FastAPI 기반 내부 서비스의 헬스 엔드포인트 상태를 확인하고, 비정상 응답 시 파드 로그와 리소스 상태를 함께 조사합니다.

```bash
holmes ask "api-gateway 서비스의 파드 상태와 최근 로그를 확인해줘"
```

## 보안 고려사항

HolmesGPT의 보안 모델은 다음 원칙에 기반합니다.

**읽기 전용 접근**

모든 도구는 읽기 전용(read-only)으로 설계되어 있습니다.
kubectl 명령은 `get`, `describe`, `logs` 등 조회 명령만 허용하며, bash 도구셋은 안전한 명령만 실행하도록 검증 로직을 포함합니다.

**RBAC 기반 권한**

Kubernetes 클러스터 접근은 ServiceAccount에 바인딩된 ClusterRole을 통해 제어합니다.
Helm 차트로 배포하면 필요한 최소 권한의 ServiceAccount가 자동 생성됩니다.

**Secret으로 API 키 관리**

LLM API 키, Grafana 토큰, Prometheus 인증 정보 등 민감 정보는 Kubernetes Secret으로 관리하고, 환경 변수로 주입합니다.

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: holmes-secrets
  namespace: holmes
type: Opaque
stringData:
  llm-api-key: "<LLM_API_KEY>"
  grafana-api-key: "<GRAFANA_API_KEY>"
```

## LLM 설정

사내 환경에서는 vLLM으로 자체 호스팅한 `gpt-oss-120b` 모델을 사용하여 외부 API 호출 없이 운영합니다.

```yaml
# ~/.holmes/config.yaml
model: openai/gpt-oss-120b
api_key: "<VLLM_API_KEY>"
api_base: "http://vllm.internal:8000/v1"
```

`config.yaml`의 `model` 필드에 LiteLLM 형식의 모델 이름을 지정하고, `api_base`에 vLLM 서버 엔드포인트를 설정합니다. HolmesGPT는 LiteLLM을 통해 OpenAI 호환 API를 지원하므로, vLLM의 OpenAI 호환 서버와 그대로 연동됩니다.

## 다음 단계

- 아키텍처 이해: [02-architecture.md](02-architecture.md)
- 배포 가이드: [03-deployment-onprem.md](03-deployment-onprem.md) 또는 [04-deployment-eks.md](04-deployment-eks.md)
- 설정 참조: [11-config-reference.md](11-config-reference.md)
