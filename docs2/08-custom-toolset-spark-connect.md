# Spark Connect 커스텀 도구셋

Spark Connect 서버의 상태를 조사하기 위한 YAML 기반 도구셋입니다. Spark Connect는 gRPC 프로토콜을 통해 클라이언트 애플리케이션과 Spark 클러스터를 연결하며, 이 도구셋은 서버 파드, 서비스, 로그를 kubectl로 조회하여 연결 문제를 진단합니다.

## 도구셋 타입: YAML (kubectl 기반)

- Spark Connect 서버 파드 및 서비스 상태 조회
- gRPC 연결 문제 디버깅
- 서버 로그 수집 및 분석

kubectl만 사용하므로 추가 바이너리가 필요하지 않습니다.

## 도구셋 YAML

아래 YAML 파일을 생성하고 `config.yaml`의 `custom_toolsets`에 경로를 추가합니다.

```yaml
# ~/.holmes/config.yaml
custom_toolsets:
  - /etc/holmes/toolsets/spark-connect-toolset.yaml
```

**spark-connect-toolset.yaml:**

```yaml
toolsets:
  spark/connect:
    description: "Spark Connect 서버 상태 조사 도구"
    prerequisites:
      - command: "kubectl version --client"
    llm_instructions: |
      Spark Connect 서버의 상태를 조사하는 도구입니다.
      Spark Connect는 gRPC 기반으로 클라이언트와 통신합니다.
      연결 문제 시 서버 파드 상태, 서비스 엔드포인트, 로그를 확인하세요.
      기본 gRPC 포트: 15002
    tools:
      - name: "spark_connect_server_status"
        description: "Check the status of Spark Connect server pods"
        command: "kubectl get pods -n {{ namespace }} -l app=spark-connect -o wide"

      - name: "spark_connect_server_logs"
        description: "Get recent logs from Spark Connect server"
        command: "kubectl logs -n {{ namespace }} -l app=spark-connect --tail=200"

      - name: "spark_connect_service"
        description: "Check Spark Connect service endpoints and ports"
        command: "kubectl get svc -n {{ namespace }} -l app=spark-connect -o wide"

      - name: "spark_connect_describe"
        description: "Describe Spark Connect server deployment for detailed status"
        command: "kubectl describe deployment -n {{ namespace }} -l app=spark-connect"
```

## 변수 설명

| 변수 | 설명 | 예시 |
|------|------|------|
| `{{ namespace }}` | Spark Connect 서버가 배포된 네임스페이스 | `spark-system` |

## 레이블 커스터마이징

위 도구셋은 `app=spark-connect` 레이블을 기준으로 파드와 서비스를 조회합니다. 실제 환경에서 사용하는 레이블이 다른 경우 YAML의 `-l` 옵션을 변경합니다.

```yaml
# 예: 레이블이 app.kubernetes.io/name=spark-connect인 경우
command: "kubectl get pods -n {{ namespace }} -l app.kubernetes.io/name=spark-connect -o wide"
```

## gRPC 연결 문제 트러블슈팅

Spark Connect 클라이언트에서 서버에 연결할 수 없는 경우 다음 순서로 확인합니다.

```bash
# 1. 서버 파드가 Running 상태인지 확인
kubectl get pods -n <namespace> -l app=spark-connect

# 2. 서비스 엔드포인트가 올바르게 설정되어 있는지 확인
kubectl get endpoints -n <namespace> -l app=spark-connect

# 3. gRPC 포트(15002) 접근 가능 여부 확인
kubectl port-forward -n <namespace> svc/spark-connect 15002:15002

# 4. 서버 로그에서 gRPC 관련 에러 확인
kubectl logs -n <namespace> -l app=spark-connect --tail=100 | grep -i "grpc\|error\|exception"
```

HolmesGPT를 사용하면 위 단계를 자연어로 요청할 수 있습니다.

## 사용 예시

```bash
holmes ask "Spark Connect 서버가 정상 동작하고 있는지 확인해줘"
```

```bash
holmes ask "Spark Connect 서버 로그에서 에러를 찾아줘"
```

```bash
holmes ask "spark-system 네임스페이스의 Spark Connect 서비스 엔드포인트를 확인해줘"
```
