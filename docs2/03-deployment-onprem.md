# 온프레미스 Kubernetes 배포 가이드

외부 인터넷 연결 없이 자체 인프라에서 HolmesGPT를 운영하기 위한 Kubernetes 배포 절차를 설명합니다. vLLM 등 자체 호스팅 추론 서버를 LLM 백엔드로 사용하는 구성을 다룹니다.

## 사전 요구사항

- kubectl이 설치되어 있고 대상 클러스터에 접근 가능한 상태
- Helm 3 설치
- vLLM 등 OpenAI-compatible API를 제공하는 추론 서버 엔드포인트
- Function calling(tool calling)을 지원하는 모델 (필수 -- 미지원 모델은 정상 동작하지 않음)

## Helm Chart 설치

Robusta Helm 저장소를 추가하고 최신 차트 정보를 가져옵니다.

```bash
helm repo add robusta https://robusta-charts.storage.googleapis.com
helm repo update
```

## vLLM 연동 설정

vLLM 서버를 LLM 백엔드로 사용하려면 `values.yaml`에 다음과 같이 설정합니다.

```yaml
# values.yaml
additionalEnvVars:
  - name: OPENAI_API_BASE
    value: "http://vllm-server.inference.svc.cluster.local:8000/v1"
  - name: OPENAI_API_KEY
    value: "none"

modelList:
  gpt-oss-120b:
    api_key: "{{ env.OPENAI_API_KEY }}"
    api_base: "{{ env.OPENAI_API_BASE }}"
    model: openai/gpt-oss-120b
    temperature: 1

config:
  model: "gpt-oss-120b"
```

각 설정 항목의 의미는 다음과 같습니다.

**`OPENAI_API_BASE`** -- vLLM 서버의 OpenAI-compatible API 엔드포인트 URL입니다. 클러스터 내부에 vLLM이 배포되어 있다면 Kubernetes 내부 DNS 주소를 사용합니다.

**`OPENAI_API_KEY`** -- vLLM은 기본적으로 인증을 요구하지 않지만, HolmesGPT가 사용하는 LiteLLM 라이브러리에서 이 값을 필수 파라미터로 요구합니다. 인증이 불필요한 경우 `"none"` 등 임의의 문자열을 설정합니다.

**`modelList`** -- Helm chart에서 LiteLLM 모델 별칭을 정의하는 섹션입니다. 키(`gpt-oss-120b`)는 HolmesGPT 내부에서 모델을 참조할 때 사용하는 이름이며, `model` 필드에는 `openai/` 접두사 뒤에 vLLM 서버가 제공하는 실제 모델명을 지정합니다. `openai/` 접두사는 LiteLLM의 OpenAI-compatible 프로바이더 패턴입니다.

**`config.model`** -- HolmesGPT가 기본으로 사용할 모델을 `modelList`에 정의된 별칭으로 지정합니다.

## Helm 배포

`values.yaml` 파일을 작성한 후 다음 명령으로 배포합니다.

```bash
helm install holmes robusta/holmes \
  -n holmes --create-namespace \
  -f values.yaml
```

네임스페이스가 이미 존재하는 경우 `--create-namespace` 플래그를 생략할 수 있습니다.

업그레이드 시에는 `install` 대신 `upgrade`를 사용합니다.

```bash
helm upgrade holmes robusta/holmes \
  -n holmes \
  -f values.yaml
```

## RBAC 설정

HolmesGPT Helm chart는 기본적으로 ServiceAccount, ClusterRole, ClusterRoleBinding을 자동 생성합니다. 부여되는 모든 권한은 읽기 전용(`get`, `list`, `watch`)이며, 클러스터 리소스를 수정하거나 삭제하지 않습니다.

### CRD 권한 제어

`crdPermissions`를 통해 ArgoCD, Kafka 등 자주 사용되는 CRD에 대한 읽기 권한을 선택적으로 활성화하거나 비활성화할 수 있습니다.

```yaml
crdPermissions:
  argo: true          # ArgoCD Application, Rollout 등
  flux: true           # Flux GitOps 리소스
  kafka: false         # 사용하지 않는 CRD는 비활성화
  keda: true           # KEDA ScaledObject 등
  crossplane: false    # Crossplane 리소스
  istio: true          # Istio VirtualService 등
  gatewayApi: true     # Gateway API 리소스
  velero: false        # Velero 백업 리소스
  externalSecrets: true # ExternalSecrets 리소스
```

### 커스텀 ClusterRole 규칙 추가

기본 권한 외에 추가 리소스에 대한 접근이 필요한 경우 `customClusterRoleRules`를 사용합니다.

```yaml
customClusterRoleRules:
  - apiGroups: ["sparkoperator.k8s.io"]
    resources: ["sparkapplications", "scheduledsparkapplications"]
    verbs: ["get", "list", "watch"]
```

### 기존 ServiceAccount 사용

자체 관리하는 ServiceAccount를 사용하려면 자동 생성을 비활성화하고 기존 계정을 지정합니다.

```yaml
createServiceAccount: false
customServiceAccountName: "your-existing-service-account"
```

## 네트워크 접근 설정

### 클러스터 내부 서비스 통신

vLLM 서버가 같은 Kubernetes 클러스터에 배포되어 있는 경우 내부 DNS를 사용합니다.

```
http://{service-name}.{namespace}.svc.cluster.local:{port}/v1
```

예를 들어, `inference` 네임스페이스에 `vllm-server`라는 서비스가 포트 8000에서 동작한다면 다음과 같습니다.

```
http://vllm-server.inference.svc.cluster.local:8000/v1
```

### 자체 서명 인증서 사용

프록시나 추론 서버가 자체 서명 CA 인증서를 사용하는 경우 `certificate` 필드에 base64로 인코딩한 CA 인증서를 지정합니다.

```yaml
certificate: "LS0tLS1CRUdJTi..."
```

인증서를 base64로 인코딩하는 방법은 다음과 같습니다.

```bash
cat /path/to/ca.crt | base64
```

## Secret 관리

API 토큰, 인증 정보 등 민감한 값은 `values.yaml`에 직접 기재하지 않고 Kubernetes Secret으로 관리할 것을 권장합니다.

먼저 Secret을 생성합니다.

```bash
kubectl create secret generic holmes-secrets \
  -n holmes \
  --from-literal=argocd-token="your-argocd-token" \
  --from-literal=openai-api-key="none"
```

`values.yaml`에서 `secretKeyRef`로 참조합니다.

```yaml
additionalEnvVars:
  - name: ARGOCD_AUTH_TOKEN
    valueFrom:
      secretKeyRef:
        name: holmes-secrets
        key: argocd-token
  - name: OPENAI_API_KEY
    valueFrom:
      secretKeyRef:
        name: holmes-secrets
        key: openai-api-key
```

## 설치 확인

배포가 완료되면 Pod 상태와 로그를 확인합니다.

```bash
# Pod 상태 확인
kubectl get pods -n holmes

# 로그 확인
kubectl logs -n holmes deployment/holmes --tail=20
```

정상 동작 여부를 API 호출로 검증합니다.

```bash
# 포트 포워딩
kubectl port-forward svc/holmes-holmes 8080:80 -n holmes

# API 호출 테스트
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"ask": "list pods in namespace default", "model": "gpt-oss-120b"}'
```

`model` 필드에는 `modelList`에서 정의한 별칭을 사용합니다.

## 제거

HolmesGPT를 클러스터에서 제거하려면 다음 명령을 실행합니다.

```bash
helm uninstall holmes -n holmes
```
