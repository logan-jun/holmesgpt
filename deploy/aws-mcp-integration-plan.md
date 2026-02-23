# AWS MCP 서버 통합 계획 (Air-Gap 환경)

## 배경

HolmesGPT에서 AWS 서비스를 활용한 트러블슈팅을 위해 AWS MCP 서버를 폐쇄망(Private VPC) EKS 환경에 배포한다.

### 왜 MCP 서버 방식인가 (boto3 내장 툴셋 vs MCP)

| 항목 | boto3 내장 툴셋 | MCP 서버 (채택) |
|------|----------------|----------------|
| LLM에 노출되는 도구 수 | 20~30개 (서비스별 1개씩) | **3개** (call_aws, suggest_aws_commands, get_execution_plan) |
| 도구 정의 토큰 소비 | ~40K 추가 | ~3K 추가 |
| AWS 서비스 커버리지 | 구현한 것만 | **AWS CLI 전체 (300+)** |
| 새 서비스 추가 | 코드 수정 필요 | AWS CLI 업데이트만으로 자동 |
| 보안 격리 | HolmesGPT Pod에 IAM 직접 부여 | 별도 Pod에 IAM 격리 |
| 운영 복잡도 | 이미지 1개 | 이미지 2개 |

HolmesGPT는 활성화된 모든 도구를 필터링 없이 매 LLM 호출에 전송(현재 ~220개, ~220K 토큰)하므로, 도구 수를 최소화하는 MCP 서브에이전트 구조가 아키텍처적으로 우수하다.

### awslabs/aws-api-mcp-server 동작 구조

```
HolmesGPT (MCP 클라이언트)
    │  HTTP/SSE (port 8000)
    ▼
Supergateway (stdio → HTTP 변환)        ← robusta-dev 래퍼
    │  stdio
    ▼
awslabs/aws-api-mcp-server              ← AWS 공식 (Apache-2.0)
    │  subprocess
    ▼
AWS CLI
    │  HTTPS/SigV4
    ▼
AWS API Endpoints (VPC Endpoint 경유)
```

- 소스코드: https://github.com/awslabs/mcp/tree/main/src/aws-api-mcp-server
- HolmesGPT 래퍼: https://github.com/robusta-dev/holmes-mcp-integrations/tree/master/servers/aws
- 이미지: `us-central1-docker.pkg.dev/genuine-flight-317411/devel/aws-api-mcp-server:1.0.1`

---

## 사전 조건

### 1. VPC Endpoints 생성

MCP 서버가 인터넷 없이 AWS API에 접근하기 위해 필요한 VPC Endpoints:

**필수:**
| VPC Endpoint | 서비스 | 타입 | 용도 |
|-------------|--------|------|------|
| `com.amazonaws.<region>.sts` | STS | Interface | IRSA 토큰 교환 |
| `com.amazonaws.<region>.ec2` | EC2 | Interface | 인스턴스/보안그룹 조회 |
| `com.amazonaws.<region>.logs` | CloudWatch Logs | Interface | 로그 조회 |
| `com.amazonaws.<region>.monitoring` | CloudWatch Metrics | Interface | 메트릭 조회 |

**권장:**
| VPC Endpoint | 서비스 | 타입 | 용도 |
|-------------|--------|------|------|
| `com.amazonaws.<region>.cloudtrail` | CloudTrail | Interface | API 감사 로그 |
| `com.amazonaws.<region>.rds` | RDS | Interface | DB 인스턴스 상태 |
| `com.amazonaws.<region>.elasticloadbalancing` | ELB | Interface | 로드밸런서 상태 |
| `com.amazonaws.<region>.s3` | S3 | Gateway | 스토리지 메타데이터 |
| `com.amazonaws.<region>.eks` | EKS | Interface | 클러스터 상태 |
| `com.amazonaws.<region>.lambda` | Lambda | Interface | 함수 상태 |

### 2. IAM Role 생성 (IRSA)

**OIDC Provider 활성화:**
```bash
eksctl utils associate-iam-oidc-provider \
  --cluster <CLUSTER_NAME> \
  --region <REGION> \
  --approve
```

**IAM Policy (Read-Only):**

Robusta 제공 정책 사용: https://github.com/robusta-dev/holmes-mcp-integrations/blob/master/servers/aws/aws-mcp-iam-policy.json

약 50개 AWS 서비스에 대해 Describe/Get/List만 허용. 주요 대상:
- 모니터링: CloudWatch (Logs, Metrics, Alarms), EventBridge, X-Ray
- 컴퓨팅: EC2, ELB, Auto Scaling, EKS, ECS, Lambda
- 데이터베이스: RDS, ElastiCache, DocumentDB, Neptune, Redshift
- 보안: IAM, CloudTrail, GuardDuty, Security Hub, WAF
- 네트워킹: VPC, Route 53, CloudFront, Network Firewall
- 스토리지: S3, EBS, EFS, FSx
- 메시징: SNS, SQS, Kinesis, MSK
- 비용: Cost Explorer, Budgets
- 설정: SSM, Secrets Manager (값 제외), CloudFormation

```bash
aws iam create-policy \
  --policy-name HolmesMCPReadOnly \
  --policy-document file://aws-mcp-iam-policy.json

aws iam create-role \
  --role-name HolmesMCPRole \
  --assume-role-policy-document file://trust-policy.json

aws iam attach-role-policy \
  --role-name HolmesMCPRole \
  --policy-arn arn:aws:iam::<ACCOUNT_ID>:policy/HolmesMCPReadOnly
```

**Trust Policy (trust-policy.json):**
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {
      "Federated": "arn:aws:iam::<ACCOUNT_ID>:oidc-provider/<OIDC_PROVIDER>"
    },
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": {
        "<OIDC_PROVIDER>:sub": "system:serviceaccount:<NAMESPACE>:aws-api-mcp-sa"
      }
    }
  }]
}
```

### 3. 이미지 반입

```bash
# 인터넷 환경에서
docker pull us-central1-docker.pkg.dev/genuine-flight-317411/devel/aws-api-mcp-server:1.0.1
docker save -o aws-mcp-server-1.0.1.tar \
  us-central1-docker.pkg.dev/genuine-flight-317411/devel/aws-api-mcp-server:1.0.1

# 폐쇄망에서
podman load -i aws-mcp-server-1.0.1.tar
podman tag us-central1-docker.pkg.dev/genuine-flight-317411/devel/aws-api-mcp-server:1.0.1 \
  <사내레지스트리>/aws-api-mcp-server:1.0.1
podman push <사내레지스트리>/aws-api-mcp-server:1.0.1
```

---

## 구현 작업

### Task 1: airgap Helm 차트에 MCP 서버 Deployment 추가

**새 파일: `deploy/helm/holmesgpt-airgap/templates/aws-mcp.yaml`**

```yaml
{{- if .Values.awsMcp.enabled }}
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: {{ .Values.awsMcp.serviceAccount.name }}
  namespace: {{ .Release.Namespace }}
  annotations:
    eks.amazonaws.com/role-arn: {{ .Values.awsMcp.serviceAccount.roleArn | quote }}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ .Release.Name }}-aws-mcp
  namespace: {{ .Release.Namespace }}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: aws-mcp
  template:
    metadata:
      labels:
        app: aws-mcp
    spec:
      serviceAccountName: {{ .Values.awsMcp.serviceAccount.name }}
      containers:
        - name: aws-mcp
          image: "{{ .Values.awsMcp.image.registry }}/{{ .Values.awsMcp.image.repository }}:{{ .Values.awsMcp.image.tag }}"
          ports:
            - containerPort: 8000
              protocol: TCP
          env:
            - name: AWS_REGION
              value: {{ .Values.awsMcp.region | quote }}
            - name: READ_OPERATIONS_ONLY
              value: "true"
          startupProbe:
            tcpSocket:
              port: 8000
            initialDelaySeconds: 20
            periodSeconds: 5
          resources:
            requests:
              memory: {{ .Values.awsMcp.resources.requests.memory | quote }}
              cpu: {{ .Values.awsMcp.resources.requests.cpu | quote }}
            limits:
              memory: {{ .Values.awsMcp.resources.limits.memory | quote }}
              cpu: {{ .Values.awsMcp.resources.limits.cpu | quote }}
---
apiVersion: v1
kind: Service
metadata:
  name: {{ .Release.Name }}-aws-mcp
  namespace: {{ .Release.Namespace }}
spec:
  selector:
    app: aws-mcp
  ports:
    - port: 8000
      targetPort: 8000
      protocol: TCP
{{- end }}
```

### Task 2: values.yaml에 AWS MCP 설정 추가

**수정 파일: `deploy/helm/holmesgpt-airgap/values.yaml`**

```yaml
# AWS MCP Server
awsMcp:
  enabled: false
  region: "ap-northeast-2"
  serviceAccount:
    name: "aws-api-mcp-sa"
    roleArn: ""  # arn:aws:iam::<ACCOUNT_ID>:role/HolmesMCPRole
  image:
    registry: "<사내레지스트리>"
    repository: "aws-api-mcp-server"
    tag: "1.0.1"
  resources:
    requests:
      memory: "512Mi"
      cpu: "250m"
    limits:
      memory: "1Gi"
      cpu: "500m"
```

### Task 3: ConfigMap에 mcp_servers 설정 연결

**수정 파일: `deploy/helm/holmesgpt-airgap/templates/configmap.yaml`**

`mcp_servers: {}` 부분을 조건부로 변경:

```yaml
{{- if .Values.awsMcp.enabled }}
mcp_servers:
  aws_api:
    url: "http://{{ .Release.Name }}-aws-mcp:8000/sse"
    mode: "sse"
{{- else }}
mcp_servers: {}
{{- end }}
```

### Task 4: NetworkPolicy 업데이트

HolmesGPT → MCP 서버 (8000번 포트) egress 허용 추가.

**수정 파일: `deploy/helm/holmesgpt-airgap/templates/networkpolicy.yaml`**

```yaml
# AWS MCP Server
{{- if .Values.awsMcp.enabled }}
- ports:
    - protocol: TCP
      port: 8000
{{- end }}
```

---

## 검증 절차

### 1. 배포 확인

```bash
# Helm 설치
helm upgrade --install holmesgpt deploy/helm/holmesgpt-airgap \
  --namespace holmes --create-namespace \
  --set awsMcp.enabled=true \
  --set awsMcp.region=ap-northeast-2 \
  --set awsMcp.serviceAccount.roleArn="arn:aws:iam::<ACCOUNT_ID>:role/HolmesMCPRole" \
  --set awsMcp.image.registry="<사내레지스트리>"

# Pod 상태 확인
kubectl get pods -n holmes
# holmesgpt-holmes-xxx       Running
# holmesgpt-aws-mcp-xxx     Running

# MCP 서버 health check
kubectl exec -n holmes deployment/holmesgpt-aws-mcp -- \
  wget -q -O- http://localhost:8000/health || echo "health endpoint 없으면 TCP 확인"
```

### 2. AWS 연결 확인

```bash
# IRSA 확인 — MCP Pod에서 AWS 자격증명 확인
kubectl exec -n holmes deployment/holmesgpt-aws-mcp -- \
  aws sts get-caller-identity

# VPC Endpoint 연결 확인
kubectl exec -n holmes deployment/holmesgpt-aws-mcp -- \
  aws ec2 describe-instances --max-items 1
```

### 3. HolmesGPT 통합 테스트

```bash
# port-forward
kubectl port-forward -n holmes svc/holmesgpt-holmes 8080:80

# API 호출
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"ask": "AWS EC2 인스턴스 목록을 조회해줘"}'
```

예상 동작:
1. HolmesGPT LLM → `suggest_aws_commands` 호출
2. MCP 서버 → AWS CLI 명령어 추천 반환
3. HolmesGPT LLM → `call_aws` 호출
4. MCP 서버 → `aws ec2 describe-instances` 실행
5. 결과 반환 → LLM 분석 → 사용자 응답

### 4. 주요 시나리오 테스트

```bash
# CloudWatch 로그 조회
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"ask": "최근 1시간 동안 에러가 발생한 CloudWatch 로그 그룹을 찾아줘"}'

# EKS 노드 상태 확인
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"ask": "EKS 클러스터의 노드그룹 상태와 용량을 확인해줘"}'

# CloudTrail 변경 이력
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"ask": "최근 24시간 동안 보안그룹이 변경된 이력이 있는지 CloudTrail에서 확인해줘"}'
```

---

## 참고 사항

### 멀티 어카운트 지원

여러 AWS 계정을 조회해야 하는 경우, multi-account 이미지 사용:
- 이미지: `multi-aws-api-mcp-server:2.0.0`
- 각 계정별 IAM Role + accounts.yaml ConfigMap 필요
- EKS 토큰 프로젝션 방식으로 STS AssumeRoleWithWebIdentity 수행

### AMP (AWS Managed Prometheus) 연동

AWS MCP와 별개로, Prometheus 툴셋에서 AMP를 직접 지원:
```yaml
toolsets:
  prometheus/metrics:
    config:
      prometheus_url: "https://aps-workspaces.<region>.amazonaws.com/workspaces/<ws-id>/"
      aws_region: ap-northeast-2
      aws_service_name: aps
```
AMP는 MCP 없이 HolmesGPT 내장 Prometheus 툴셋 + SigV4로 직접 연결.

### Bedrock LLM 사용 시

vLLM 대신 AWS Bedrock을 LLM 백엔드로 사용 가능:
- VPC Endpoint 필요: `com.amazonaws.<region>.bedrock-runtime`
- HolmesGPT Pod의 ServiceAccount에 Bedrock IAM 권한 추가
- values.yaml에서 model 설정을 `bedrock/anthropic.claude-sonnet-4-5-20250929` 등으로 변경
