# FastAPI 커스텀 도구셋

FastAPI 기반 마이크로서비스의 상태를 조사하기 위한 HTTP 타입 커스텀 도구셋입니다. 헬스체크, 메트릭, OpenAPI 스펙 등 표준 엔드포인트를 활용하여 서비스 상태를 진단합니다.

## 도구셋 타입

HTTP(API-based) 방식의 커스텀 도구셋입니다. FastAPI가 제공하는 표준 엔드포인트(`/health`, `/metrics`, `/openapi.json`)에 직접 HTTP 요청을 보내는 방식으로 동작합니다.

동작 흐름은 다음과 같습니다.

1. 와일드카드 호스트 패턴으로 클러스터 내부의 모든 서비스에 접근 허용
2. LLM이 Kubernetes 도구셋으로 서비스 이름과 포트를 파악
3. HTTP 도구셋으로 해당 서비스의 상태 엔드포인트를 직접 호출
4. 응답 결과를 LLM이 분석하여 진단 결과를 제시

별도의 인증 설정 없이 클러스터 내부 네트워크를 통해 접근합니다. 인증이 필요한 서비스는 별도 도구셋으로 분리하여 구성합니다.

## 도구셋 YAML

다음 내용을 `fastapi-toolset.yaml` 파일로 저장합니다. 전체 예시 파일은 `docs2/examples/toolsets/fastapi-toolset.yaml`에 있습니다.

```yaml
toolsets:
  fastapi/services:
    type: http
    enabled: true
    config:
      endpoints:
        - hosts:
            - "*.svc.cluster.local"
          paths: ["/health", "/healthz", "/ready", "/readyz", "/metrics", "/openapi.json", "/docs", "/api/v1/*"]
          methods: ["GET"]
      verify_ssl: false
      timeout_seconds: 15
    llm_instructions: |
      FastAPI 기반 마이크로서비스의 상태를 조회합니다.
      클러스터 내부의 FastAPI 서비스에 HTTP 요청을 보낼 수 있습니다.

      서비스 URL 패턴: http://{service-name}.{namespace}.svc.cluster.local:{port}

      주요 엔드포인트:
      - GET /health 또는 /healthz - 헬스체크 (서비스 정상 여부)
      - GET /ready 또는 /readyz - 레디니스체크 (트래픽 수신 가능 여부)
      - GET /metrics - Prometheus 메트릭 (응답 시간, 요청 수 등)
      - GET /openapi.json - API 스펙 (사용 가능한 API 목록)
      - GET /docs - Swagger UI (API 문서)
      - GET /api/v1/* - API 엔드포인트 (읽기 전용)

      서비스가 응답하지 않으면 파드 상태와 이벤트를 먼저 확인하세요.
```

설정 항목별 설명은 다음과 같습니다.

**`hosts: ["*.svc.cluster.local"]`** -- 와일드카드 패턴으로 클러스터 내부의 모든 Kubernetes 서비스에 접근을 허용합니다. `*.svc.cluster.local`은 `{service}.{namespace}.svc.cluster.local` 형식의 모든 서비스 DNS에 매칭됩니다.

**`paths`** -- 접근을 허용할 URL 경로 목록입니다. 표준 헬스체크, 메트릭, OpenAPI 엔드포인트와 `/api/v1/*` 하위 경로만 허용하여 읽기 전용 접근을 보장합니다.

**`methods: ["GET"]`** -- GET 메서드만 허용합니다. 서비스 상태를 조회하는 용도이므로 데이터 변경 메서드(POST, PUT, DELETE)는 차단합니다.

**인증 없음** -- `auth` 설정을 생략하면 인증 헤더 없이 요청을 보냅니다. 클러스터 내부 네트워크의 서비스 간 통신에서 인증이 불필요한 경우에 적합합니다.

**`timeout_seconds: 15`** -- 마이크로서비스의 헬스체크 엔드포인트는 빠르게 응답해야 하므로 타임아웃을 짧게 설정합니다. 응답이 느린 서비스는 그 자체가 문제 징후입니다.

## 와일드카드 호스트 패턴

`*.svc.cluster.local` 패턴은 클러스터 내 모든 서비스에 접근할 수 있습니다. 보안 요구사항에 따라 더 제한적인 패턴을 사용할 수 있습니다.

```yaml
# 특정 네임스페이스의 서비스만 허용
hosts:
  - "*.my-namespace.svc.cluster.local"

# 특정 접두사를 가진 서비스만 허용
hosts:
  - "api-*.default.svc.cluster.local"

# 여러 네임스페이스를 명시적으로 지정
hosts:
  - "*.production.svc.cluster.local"
  - "*.staging.svc.cluster.local"
```

호스트 패턴 매칭 규칙은 다음과 같습니다.

- `*`는 서브도메인의 어느 위치에나 사용할 수 있습니다.
- `*.example.com`은 `api.example.com`, `dev.example.com` 등에 매칭됩니다.
- 정확한 호스트 이름도 지정할 수 있습니다: `user-service.production.svc.cluster.local`

## 인증이 필요한 서비스 분리

동일한 클러스터에 인증이 필요한 서비스와 불필요한 서비스가 혼재하는 경우, 별도 도구셋으로 분리하여 구성합니다.

```yaml
toolsets:
  fastapi/internal:
    type: http
    enabled: true
    config:
      endpoints:
        - hosts:
            - "*.internal.svc.cluster.local"
          paths: ["/health", "/healthz", "/metrics", "/openapi.json", "/api/v1/*"]
          methods: ["GET"]
      verify_ssl: false
      timeout_seconds: 15
    llm_instructions: |
      내부 FastAPI 서비스를 조회합니다. 인증 없이 접근 가능합니다.
      서비스 URL: http://{service}.internal.svc.cluster.local:{port}

  fastapi/secured:
    type: http
    enabled: true
    config:
      endpoints:
        - hosts:
            - "*.secured.svc.cluster.local"
          paths: ["/api/*"]
          methods: ["GET"]
          auth:
            type: bearer
            token: "{{ env.INTERNAL_API_TOKEN }}"
      verify_ssl: false
      timeout_seconds: 15
    llm_instructions: |
      인증이 필요한 FastAPI 서비스를 조회합니다.
      서비스 URL: http://{service}.secured.svc.cluster.local:{port}
```

이 구성에서 HolmesGPT는 두 개의 도구를 사용할 수 있습니다.

- `fastapi_internal_request` -- 인증 없이 내부 서비스에 접근
- `fastapi_secured_request` -- Bearer 토큰으로 보안 서비스에 접근

## CLI 환경 설정

`~/.holmes/config.yaml`에 도구셋 파일 경로를 추가합니다.

```yaml
custom_toolsets:
  - /path/to/fastapi-toolset.yaml
```

도구셋이 정상 로드되었는지 확인합니다.

```bash
holmes toolset list
```

## Helm Chart 설정

Kubernetes에 배포된 HolmesGPT에 FastAPI 도구셋을 연동하는 Helm values 설정입니다.

```yaml
holmes:
  toolsets:
    fastapi/services:
      type: http
      enabled: true
      config:
        endpoints:
          - hosts:
              - "*.svc.cluster.local"
            paths: ["/health", "/healthz", "/ready", "/readyz", "/metrics", "/openapi.json", "/docs", "/api/v1/*"]
            methods: ["GET"]
        verify_ssl: false
        timeout_seconds: 15
      llm_instructions: |
        FastAPI 기반 마이크로서비스의 상태를 조회합니다.
        클러스터 내부의 FastAPI 서비스에 HTTP 요청을 보낼 수 있습니다.

        서비스 URL 패턴: http://{service-name}.{namespace}.svc.cluster.local:{port}

        주요 엔드포인트:
        - GET /health 또는 /healthz - 헬스체크
        - GET /ready 또는 /readyz - 레디니스체크
        - GET /metrics - Prometheus 메트릭
        - GET /openapi.json - API 스펙
        - GET /api/v1/* - API 엔드포인트 (읽기 전용)

        서비스가 응답하지 않으면 파드 상태와 이벤트를 먼저 확인하세요.
```

인증이 필요한 서비스 도구셋을 함께 사용하는 경우, Secret과 환경 변수를 추가합니다.

```yaml
holmes:
  additionalEnvVars:
    - name: INTERNAL_API_TOKEN
      valueFrom:
        secretKeyRef:
          name: fastapi-credentials
          key: api-token
```

Helm 배포 또는 업그레이드를 실행합니다.

```bash
helm upgrade holmes robusta/holmes \
  -n holmes \
  -f values.yaml
```

## 사용 예시

```bash
holmes ask "user-service의 헬스체크 상태를 확인해줘"
```

```bash
holmes ask "order-service의 /metrics에서 응답 시간을 조회해줘"
```

```bash
holmes ask "payment-service의 API 스펙을 보여줘"
```

```bash
holmes ask "production 네임스페이스의 모든 FastAPI 서비스 상태를 점검해줘"
```

## 트러블슈팅

```bash
# 서비스 DNS 확인 -- 클러스터 내부에서 서비스명으로 접근 가능한지 확인
kubectl exec -n holmes deployment/holmes -- \
  wget -q -O- http://user-service.production.svc.cluster.local:8000/health

# 서비스 엔드포인트 확인 -- 서비스에 연결된 파드가 있는지 확인
kubectl get endpoints user-service -n production

# 파드 상태 확인 -- 서비스가 응답하지 않을 때
kubectl get pods -n production -l app=user-service

# HolmesGPT 도구셋 로드 상태 확인
holmes toolset list | grep fastapi
```
