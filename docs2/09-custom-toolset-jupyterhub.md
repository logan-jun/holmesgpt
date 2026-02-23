# JupyterHub 커스텀 도구셋

JupyterHub REST API를 활용한 HTTP 타입 커스텀 도구셋입니다. 사용자 세션 상태, 서버 목록, 프록시 정보를 조회합니다.

## 도구셋 타입

HTTP(API-based) 방식의 커스텀 도구셋입니다. JupyterHub가 제공하는 REST API에 직접 HTTP 요청을 보내는 방식으로 동작하며, 엔드포인트 화이트리스트로 접근 범위를 제한합니다.

동작 흐름은 다음과 같습니다.

1. HolmesGPT가 Bearer token으로 JupyterHub API에 인증
2. LLM 판단에 따라 적절한 API 엔드포인트를 호출
3. 응답 JSON을 LLM이 분석하여 진단 결과를 제시

YAML(Command-based) 도구셋과 달리 별도의 CLI 바이너리 설치가 필요 없습니다. HolmesGPT가 내장 HTTP 클라이언트로 API를 직접 호출합니다.

## 사전 준비

### API 토큰 생성

JupyterHub 관리자 계정으로 API 토큰을 생성합니다. 두 가지 방법이 있습니다.

**방법 1 -- 관리자 웹 페이지**

1. JupyterHub 웹 UI에 관리자 계정으로 로그인
2. Admin 페이지 접속
3. Token 섹션에서 "Request new API Token" 클릭
4. 생성된 토큰을 안전하게 보관

**방법 2 -- CLI**

```bash
jupyterhub token <admin-username>
```

생성된 토큰은 JupyterHub API의 모든 읽기 엔드포인트에 접근할 수 있어야 합니다. 읽기 전용 권한(read:users, read:servers 스코프)이면 충분합니다.

## 도구셋 YAML

다음 내용을 `jupyterhub-toolset.yaml` 파일로 저장합니다. 전체 예시 파일은 `docs2/examples/toolsets/jupyterhub-toolset.yaml`에 있습니다.

```yaml
toolsets:
  jupyterhub/api:
    type: http
    enabled: true
    config:
      endpoints:
        - hosts:
            - "jupyterhub.jupyterhub.svc.cluster.local"
          paths: ["/hub/api/*"]
          methods: ["GET"]
          auth:
            type: bearer
            token: "{{ env.JUPYTERHUB_API_TOKEN }}"
      verify_ssl: false
      timeout_seconds: 30
    llm_instructions: |
      JupyterHub REST API를 사용하여 사용자 세션과 서버 상태를 조회합니다.
      Base URL: http://jupyterhub.jupyterhub.svc.cluster.local:8081

      주요 엔드포인트:
      - GET /hub/api/users - 전체 사용자 목록 및 서버 상태
      - GET /hub/api/users/{username} - 특정 사용자 정보
      - GET /hub/api/users/{username}/server - 사용자 서버 상태
      - GET /hub/api/proxy - 프록시 라우팅 테이블
      - GET /hub/api/ - API 루트 (버전 정보)

      사용자 서버 상태 확인 시 서버가 ''(빈 문자열) 키로 있으면 기본 서버입니다.
      서버 상태: pending, ready, stopped
```

설정 항목별 설명은 다음과 같습니다.

**`type: http`** -- HTTP 도구셋임을 선언합니다. HolmesGPT가 내장 HTTP 클라이언트를 사용하여 API를 호출합니다.

**`hosts`** -- 접근을 허용할 호스트 목록입니다. Kubernetes 내부 DNS 주소를 사용합니다. 와일드카드 패턴(`*.jupyterhub.svc.cluster.local`)도 지원합니다.

**`paths`** -- 접근을 허용할 URL 경로 패턴입니다. `/hub/api/*`로 설정하면 JupyterHub API 엔드포인트만 허용됩니다.

**`methods`** -- 허용할 HTTP 메서드입니다. 읽기 전용 조사 목적이므로 `GET`만 허용합니다.

**`auth.type: bearer`** -- Bearer 토큰 인증 방식을 사용합니다. 요청 시 `Authorization: Bearer <token>` 헤더가 자동으로 추가됩니다.

**`verify_ssl: false`** -- 클러스터 내부 통신에서 자체 서명 인증서를 사용하는 경우 SSL 검증을 비활성화합니다. 외부 노출된 JupyterHub에 접근하는 경우 `true`로 설정합니다.

**`llm_instructions`** -- LLM에게 API 사용 방법을 안내하는 지시문입니다. Base URL, 주요 엔드포인트, 응답 구조의 특이사항 등을 포함합니다.

## CLI 환경 설정

`~/.holmes/config.yaml`에 도구셋 파일 경로를 추가합니다.

```yaml
custom_toolsets:
  - /path/to/jupyterhub-toolset.yaml
```

환경 변수를 설정합니다.

```bash
export JUPYTERHUB_API_TOKEN="your-jupyterhub-api-token"
```

도구셋이 정상 로드되었는지 확인합니다.

```bash
holmes toolset list
```

## Helm Chart 설정

Kubernetes에 배포된 HolmesGPT에 JupyterHub 도구셋을 연동하는 Helm values 설정입니다.

```yaml
holmes:
  additionalEnvVars:
    - name: JUPYTERHUB_API_TOKEN
      valueFrom:
        secretKeyRef:
          name: jupyterhub-credentials
          key: api-token

  toolsets:
    jupyterhub/api:
      type: http
      enabled: true
      config:
        endpoints:
          - hosts:
              - "jupyterhub.jupyterhub.svc.cluster.local"
            paths: ["/hub/api/*"]
            methods: ["GET"]
            auth:
              type: bearer
              token: "{{ env.JUPYTERHUB_API_TOKEN }}"
        verify_ssl: false
        timeout_seconds: 30
      llm_instructions: |
        JupyterHub REST API를 사용하여 사용자 세션과 서버 상태를 조회합니다.
        Base URL: http://jupyterhub.jupyterhub.svc.cluster.local:8081

        주요 엔드포인트:
        - GET /hub/api/users - 전체 사용자 목록 및 서버 상태
        - GET /hub/api/users/{username} - 특정 사용자 정보
        - GET /hub/api/proxy - 프록시 라우팅 테이블
        - GET /hub/api/ - API 루트 (버전 정보)
```

Secret을 먼저 생성합니다.

```bash
kubectl create secret generic jupyterhub-credentials \
  -n holmes \
  --from-literal=api-token="your-jupyterhub-api-token"
```

Helm 배포 또는 업그레이드를 실행합니다.

```bash
helm upgrade holmes robusta/holmes \
  -n holmes \
  -f values.yaml
```

## 사용 예시

```bash
holmes ask "JupyterHub에서 현재 활성화된 사용자 세션을 보여줘"
```

```bash
holmes ask "사용자 john의 JupyterHub 서버 상태를 확인해줘"
```

```bash
holmes ask "JupyterHub 프록시 라우팅 테이블을 조회해줘"
```

```bash
holmes ask "JupyterHub에 접속할 수 없다는 보고가 있습니다. API 상태를 점검해줘"
```

## 트러블슈팅

```bash
# API 토큰이 유효한지 직접 확인
curl -s -H "Authorization: Bearer $JUPYTERHUB_API_TOKEN" \
  http://jupyterhub.jupyterhub.svc.cluster.local:8081/hub/api/

# HolmesGPT 파드에서 JupyterHub 네트워크 연결 확인
kubectl exec -n holmes deployment/holmes -- \
  wget -q -O- http://jupyterhub.jupyterhub.svc.cluster.local:8081/hub/api/

# JUPYTERHUB_API_TOKEN 환경 변수가 주입되었는지 확인
kubectl exec -n holmes deployment/holmes -- env | grep JUPYTERHUB

# HolmesGPT 도구셋 로드 상태 확인
holmes toolset list | grep jupyterhub
```
