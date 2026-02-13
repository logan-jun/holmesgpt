# HolmesGPT 폐쇄망 배포 가이드

폐쇄망(Air-Gapped) Kubernetes 환경에 HolmesGPT를 배포하기 위한 단계별 가이드.

## 목차

1. [사전 요구사항](#1-사전-요구사항)
2. [이미지 빌드 (인터넷 환경)](#2-이미지-빌드-인터넷-환경)
3. [이미지 반입 (폐쇄망)](#3-이미지-반입-폐쇄망)
4. [values.yaml 설정](#4-valuesyaml-설정)
5. [Helm 배포](#5-helm-배포)
6. [배포 검증](#6-배포-검증)
7. [운영 가이드](#7-운영-가이드)
8. [트러블슈팅](#8-트러블슈팅)

---

## 1. 사전 요구사항

**인터넷 접근 가능한 빌드 서버:**

- Docker 20.10+
- Trivy (취약점 스캔용, 선택)
- Python 3.9+ (Trivy 리포트 파싱용)

**폐쇄망 Kubernetes 클러스터:**

- Kubernetes 1.24+
- Helm 3.x
- Private Container Registry (Harbor, Nexus 등)
- vLLM 서비스 (gpt-oss-120b 모델 서빙 중)
- Prometheus (선택)
- Grafana (선택)

---

## 2. 이미지 빌드 (인터넷 환경)

인터넷이 되는 서버에서 수행한다.

### 2-1. 소스 코드 준비

```bash
git clone <holmesgpt-repo-url>
cd holmesgpt
```

### 2-2. 기본 빌드 + Trivy 스캔

```bash
cd deploy
./build.sh
```

빌드 스크립트가 자동으로 수행하는 작업:

1. `Dockerfile.airgap`으로 Docker 이미지 빌드
2. Trivy로 HIGH/CRITICAL 취약점 스캔
3. 취약점 발견 시 자동 패치 후 재빌드
4. 최종 이미지를 tar 파일로 export

### 2-3. 빌드 옵션

```bash
# 레지스트리/이미지명/태그 커스터마이징
REGISTRY=myregistry IMAGE_TAG=v1.0.0 ./build.sh

# Trivy 스캔 건너뛰기
./build.sh --skip-scan

# Private Registry에 직접 push (인터넷이 되는 환경에서)
REGISTRY=harbor.internal.com/holmes IMAGE_TAG=v1.0.0 ./build.sh --push
```

### 2-4. Private Package Registry 사용 (선택)

사내 PyPI 미러가 있는 경우:

```bash
docker build \
  -t myregistry/holmesgpt-airgap:v1.0.0 \
  -f deploy/Dockerfile.airgap \
  --build-arg PRIVATE_PACKAGE_REGISTRY=https://pypi.internal.com/simple \
  --build-arg TARGETPLATFORM=linux/amd64 \
  .
```

### 2-5. 빌드 산출물 확인

```bash
ls -lh deploy/
# holmesgpt-airgap-latest.tar   ← 이미지 tar 파일
# trivy-report.json              ← 취약점 스캔 결과 (JSON)
# trivy-report.txt               ← 취약점 스캔 결과 (테이블)
```

---

## 3. 이미지 반입 (폐쇄망)

### 3-1. tar 파일 전송

빌드 서버에서 폐쇄망으로 이미지를 전송한다. (USB, 전용 반입 장비, 또는 망간 전송 시스템 사용)

```bash
# 예시: SCP로 전송 (망간 게이트웨이 경유)
scp deploy/holmesgpt-airgap-latest.tar user@gateway:/transfer/
```

### 3-2. Private Registry에 로드

폐쇄망 내부에서 수행한다.

```bash
# tar 파일에서 Docker 이미지 로드
docker load -i holmesgpt-airgap-latest.tar

# 로드된 이미지 확인
docker images | grep holmesgpt-airgap

# Private Registry로 태깅 및 push
docker tag holmesgpt/holmesgpt-airgap:latest harbor.internal.com/holmes/holmesgpt-airgap:v1.0.0
docker push harbor.internal.com/holmes/holmesgpt-airgap:v1.0.0
```

---

## 4. values.yaml 설정

`deploy/helm/holmesgpt-airgap/values.yaml`을 환경에 맞게 수정한다.

### 4-1. 필수 설정

```yaml
# 이미지 (Private Registry 주소로 변경)
registry: "harbor.internal.com/holmes"
image: "holmesgpt-airgap:v1.0.0"

# vLLM 연동 (실제 서비스 주소로 변경)
vllm:
  endpoint: "http://vllm-server.ai-platform.svc.cluster.local:8000/v1"
  apiKey: "none"
  modelName: "gpt-oss-120b"
  requestTimeout: "600"
```

### 4-2. 모니터링 연동 (선택)

```yaml
# Prometheus
prometheus:
  url: "http://prometheus-server.monitoring.svc.cluster.local:9090"

# Grafana
grafana:
  url: "http://grafana.monitoring.svc.cluster.local:3000"
  apiKey: "your-grafana-api-key"    # Viewer 권한 이상
```

Prometheus/Grafana를 사용하지 않는 경우:

```yaml
toolsets:
  prometheus/metrics:
    enabled: false
  grafana/dashboards:
    enabled: false
```

### 4-3. ImagePullSecret 설정 (Private Registry 인증 필요 시)

```bash
# Secret 생성
kubectl create namespace holmes
kubectl create secret docker-registry regcred \
  --docker-server=harbor.internal.com \
  --docker-username=admin \
  --docker-password=<password> \
  -n holmes
```

```yaml
# values.yaml
imagePullSecrets:
  - name: regcred
```

### 4-4. NetworkPolicy 커스터마이징

기본으로 다음 egress만 허용된다:

| 대상 | 포트 | 용도 |
|------|------|------|
| CoreDNS | 53 (UDP/TCP) | DNS 조회 |
| K8s API Server | 443, 6443 | kubectl 명령 |
| vLLM | 8000 | LLM 추론 |
| Prometheus | 9090 | 메트릭 조회 |
| Grafana | 3000 | 대시보드 조회 |
| Kubelet | 10250 | 파드 로그 |

추가 egress가 필요한 경우:

```yaml
networkPolicy:
  enabled: true
  vllmPort: 8000
  additionalEgress:
    - port: 9200
      cidr: "10.0.0.0/8"    # Elasticsearch 등
```

NetworkPolicy를 사용하지 않는 경우:

```yaml
networkPolicy:
  enabled: false
```

### 4-5. CRD 권한 (선택)

클러스터에 설치된 CRD에 따라 활성화한다:

```yaml
crdPermissions:
  argo: true       # ArgoCD 사용 시
  istio: true      # Istio 서비스 메시 사용 시
  # 나머지는 필요에 따라 true로 변경
```

### 4-6. 리소스 조정

```yaml
resources:
  requests:
    cpu: 100m
    memory: 2048Mi
  limits:
    memory: 2048Mi
    # cpu: "2"      # CPU 제한이 필요한 경우
```

---

## 5. Helm 배포

### 5-1. Namespace 생성 및 설치

```bash
helm install holmesgpt deploy/helm/holmesgpt-airgap/ \
  --namespace holmes \
  --create-namespace \
  -f deploy/helm/holmesgpt-airgap/values.yaml
```

### 5-2. 커스텀 values 파일로 설치

환경별 values 파일을 별도로 관리하는 경우:

```bash
helm install holmesgpt deploy/helm/holmesgpt-airgap/ \
  --namespace holmes \
  --create-namespace \
  -f my-values.yaml
```

### 5-3. 업그레이드

```bash
helm upgrade holmesgpt deploy/helm/holmesgpt-airgap/ \
  --namespace holmes \
  -f deploy/helm/holmesgpt-airgap/values.yaml
```

### 5-4. 삭제

```bash
helm uninstall holmesgpt --namespace holmes
```

---

## 6. 배포 검증

### 6-1. 파드 상태 확인

```bash
kubectl get pods -n holmes
# NAME                                READY   STATUS    RESTARTS   AGE
# holmesgpt-holmes-xxxxxxxxx-xxxxx   1/1     Running   0          2m

kubectl get svc -n holmes
# NAME               TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)   AGE
# holmesgpt-holmes   ClusterIP   10.96.xxx.xxx   <none>        80/TCP    2m
```

### 6-2. 로그 확인

```bash
kubectl logs -n holmes deployment/holmesgpt-holmes --tail=50
```

정상 기동 시 다음과 유사한 로그가 출력된다:
```
INFO: Started server process
INFO: Waiting for application startup.
INFO: Application startup complete.
INFO: Uvicorn running on http://0.0.0.0:5050
```

### 6-3. Health Check

```bash
kubectl exec -n holmes deployment/holmesgpt-holmes -- \
  curl -s http://localhost:5050/healthz
# {"status":"ok"}

kubectl exec -n holmes deployment/holmesgpt-holmes -- \
  curl -s http://localhost:5050/readyz
# {"status":"ok"}
```

### 6-4. vLLM 연결 확인

```bash
kubectl exec -n holmes deployment/holmesgpt-holmes -- \
  curl -s http://VLLM_SERVICE.VLLM_NAMESPACE.svc.cluster.local:8000/v1/models
```

### 6-5. RBAC 확인

```bash
kubectl auth can-i list pods --as=system:serviceaccount:holmes:holmesgpt-holmes-service-account --all-namespaces
# yes
```

### 6-6. NetworkPolicy 확인

```bash
kubectl get networkpolicy -n holmes
kubectl describe networkpolicy holmesgpt-holmes-netpol -n holmes
```

---

## 7. 운영 가이드

### 7-1. Holmes CLI 사용

```bash
# 파드 내에서 직접 질문
kubectl exec -n holmes deployment/holmesgpt-holmes -- \
  python holmes_cli.py ask "Why is my-app pod in CrashLoopBackOff?"

# 포트포워딩으로 API 호출
kubectl port-forward -n holmes svc/holmesgpt-holmes 8080:80
curl -X POST http://localhost:8080/api/investigate \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the status of all pods in namespace default?"}'
```

### 7-2. 이미지 업데이트

1. 인터넷 환경에서 새 이미지 빌드:
   ```bash
   IMAGE_TAG=v1.1.0 ./build.sh
   ```
2. tar 파일을 폐쇄망으로 전송
3. Private Registry에 push
4. Helm upgrade:
   ```bash
   helm upgrade holmesgpt deploy/helm/holmesgpt-airgap/ \
     --namespace holmes \
     --set image=holmesgpt-airgap:v1.1.0
   ```

### 7-3. 커스텀 Toolset 추가

values.yaml에서 toolset을 추가하거나 ConfigMap을 직접 수정할 수 있다:

```yaml
toolsets:
  kubernetes/core:
    enabled: true
  kubernetes/logs:
    enabled: true
  # 새 toolset 추가
  my-custom-toolset:
    enabled: true
    config:
      some_option: "value"
```

---

## 8. 트러블슈팅

### 파드가 시작되지 않는 경우

```bash
# 이벤트 확인
kubectl describe pod -n holmes -l app=holmes

# ImagePullBackOff → 레지스트리 주소 또는 ImagePullSecret 확인
# CrashLoopBackOff → 로그 확인
kubectl logs -n holmes -l app=holmes --previous
```

### vLLM 연결 실패

```bash
# 파드 내에서 vLLM 엔드포인트 접근 테스트
kubectl exec -n holmes deployment/holmesgpt-holmes -- \
  curl -v http://VLLM_SERVICE:8000/v1/models

# NetworkPolicy가 vLLM 포트를 차단하고 있지 않은지 확인
# values.yaml의 networkPolicy.vllmPort가 실제 vLLM 포트와 일치하는지 확인
```

### DNS 조회 실패

```bash
kubectl exec -n holmes deployment/holmesgpt-holmes -- \
  nslookup kubernetes.default.svc.cluster.local

# NetworkPolicy에서 DNS(53번 포트)가 허용되어 있는지 확인
```

### Prometheus/Grafana 연결 실패

```bash
# 서비스 주소 확인
kubectl get svc -n monitoring

# 파드에서 직접 접근 테스트
kubectl exec -n holmes deployment/holmesgpt-holmes -- \
  curl -s http://prometheus-server.monitoring:9090/api/v1/status/config | head -c 200
```

### 리소스 부족

```bash
# 현재 리소스 사용량 확인
kubectl top pod -n holmes

# 필요 시 values.yaml에서 리소스 상향
# resources.requests.memory: 4096Mi
# resources.limits.memory: 4096Mi
```
