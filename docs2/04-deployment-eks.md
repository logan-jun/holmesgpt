# Amazon EKS 배포 가이드

Amazon EKS 환경에 HolmesGPT를 배포하는 방법을 설명합니다.
기본 배포 방식은 온프레미스 Kubernetes와 동일하게 Helm chart를 사용하며, EKS 고유의 설정(IRSA, AWS 서비스 통합, 네트워크 구성)을 추가로 다룹니다.

## On-prem 배포와의 차이점

HolmesGPT의 핵심 배포 방법은 환경에 관계없이 동일합니다. Helm chart로 설치하고, `values.yaml`로 설정을 관리합니다.

EKS 환경에서 추가로 고려해야 할 사항은 다음과 같습니다.

- **IRSA (IAM Roles for Service Accounts)**: AWS 서비스에 접근이 필요한 경우 ServiceAccount에 IAM Role을 연결합니다.
- **AWS 서비스 통합**: Amazon Managed Prometheus(AMP), CloudWatch 등 AWS 관리형 서비스와 연동할 수 있습니다.
- **네트워크 구성**: VPC 내부의 vLLM 엔드포인트 접근, 보안 그룹 설정 등을 확인해야 합니다.

## 사전 요구사항

- EKS 클러스터에 대한 `kubectl` 접근 권한 (`aws eks update-kubeconfig` 설정 완료)
- AWS CLI v2 설치 및 인증 설정
- Helm 3.x 설치
- vLLM 추론 서버 엔드포인트 (EKS 클러스터 내부 서비스 또는 외부 URL)

클러스터 접근을 확인합니다.

```bash
# EKS 클러스터 kubeconfig 설정
aws eks update-kubeconfig --name YOUR_CLUSTER_NAME --region YOUR_REGION

# 클러스터 접근 확인
kubectl get nodes
```

## Helm 저장소 추가

```bash
helm repo add robusta https://robusta-charts.storage.googleapis.com
helm repo update
```

## EKS values.yaml 구성

아래는 EKS 환경에 맞춘 `values-eks.yaml` 예시입니다.
vLLM 자체 호스팅 모델(`gpt-oss-120b`)을 사용하는 구성을 기준으로 합니다.

```yaml
# values-eks.yaml

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

# EKS 노드 선택
nodeSelector:
  kubernetes.io/os: linux

tolerations: []

serviceAccount:
  annotations: {}
```

`OPENAI_API_BASE`는 vLLM 서버의 클러스터 내부 주소입니다.
vLLM이 다른 네임스페이스에 있는 경우, `http://SERVICE_NAME.NAMESPACE.svc.cluster.local:PORT/v1` 형식으로 지정합니다.

## Helm 배포

```bash
helm install holmes robusta/holmes \
  -n holmes --create-namespace \
  -f values-eks.yaml
```

## 설치 확인

```bash
# Pod 상태 확인
kubectl get pods -n holmes

# 로그 확인
kubectl logs -n holmes deployment/holmes --tail=20
```

정상적으로 배포되면 Pod가 `Running` 상태이고, 로그에 에러가 없어야 합니다.

## IRSA 설정 (선택)

HolmesGPT는 기본적으로 Kubernetes API와 클러스터 내부 서비스만 사용합니다.
AWS 서비스(CloudWatch, S3, Amazon Managed Prometheus 등)에 직접 접근해야 하는 경우에만 IRSA를 설정합니다.

IRSA가 필요한 경우, ServiceAccount에 IAM Role ARN 어노테이션을 추가합니다.

```yaml
# values-eks.yaml 내 serviceAccount 섹션
serviceAccount:
  annotations:
    eks.amazonaws.com/role-arn: arn:aws:iam::ACCOUNT_ID:role/holmes-role
```

IAM Role에는 필요한 AWS 서비스 접근 권한만 부여합니다.
예를 들어 Amazon Managed Prometheus 읽기 권한이 필요한 경우, `aps:QueryMetrics`와 `aps:GetMetricMetadata` 액션을 허용하는 정책을 연결합니다.

## AWS Managed Prometheus 연동 (선택)

Amazon Managed Prometheus(AMP)를 사용하는 경우, Prometheus 도구셋에 AMP 엔드포인트를 설정합니다.

```yaml
# values-eks.yaml 내 toolsets 섹션
toolsets:
  prometheus/metrics:
    enabled: true
    config:
      prometheus_url: "https://aps-workspaces.REGION.amazonaws.com/workspaces/WORKSPACE_ID"
      prometheus_headers:
        Authorization: "{{ env.AMP_AUTH_TOKEN }}"
```

AMP 인증에는 SigV4 서명이 필요합니다. IRSA를 통해 인증하거나, 별도의 인증 프록시를 사용할 수 있습니다.

## 멀티 클러스터 운영

여러 클러스터(On-prem, EKS)에 HolmesGPT를 배포하는 경우, 각 클러스터에 별도의 Helm release를 설치합니다.

각 클러스터의 `values.yaml`에서 동일한 vLLM 엔드포인트를 참조할 수 있으며, `cluster_name`으로 클러스터를 구분합니다.

```yaml
config:
  model: "gpt-oss-120b"
  cluster_name: "eks-prod"
```

다른 클러스터에서는 다른 `cluster_name`을 사용합니다.

```yaml
config:
  model: "gpt-oss-120b"
  cluster_name: "onprem-prod"
```

## 업그레이드

```bash
helm repo update
helm upgrade holmes robusta/holmes \
  -n holmes \
  -f values-eks.yaml
```

## 삭제

```bash
helm uninstall holmes -n holmes
```
