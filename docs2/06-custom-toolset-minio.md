# MinIO 커스텀 도구셋

MinIO 오브젝트 스토리지 서버의 상태를 조사하기 위한 YAML 기반 커스텀 도구셋입니다. `mc` (MinIO Client) CLI를 사용하여 버킷 정보, 서버 상태, 디스크 사용량 등을 조회합니다.

## 도구셋 타입

YAML(Command-based) 방식의 커스텀 도구셋입니다. 내장 ArgoCD 도구셋(`argocd.yaml`)과 동일한 패턴으로, 각 도구가 `mc` CLI 명령을 실행하여 MinIO 서버에서 정보를 수집합니다.

동작 흐름은 다음과 같습니다.

1. `mc alias`로 MinIO 서버 연결 정보를 등록
2. HolmesGPT가 LLM 판단에 따라 적절한 `mc` 명령을 호출
3. 명령 실행 결과를 LLM이 분석하여 진단 결과를 제시

## 사전 준비

### mc CLI 설치

HolmesGPT 실행 환경에 `mc` 바이너리가 있어야 합니다. Kubernetes에서 HolmesGPT를 운영하는 경우, 커스텀 Docker 이미지를 빌드하여 `mc`를 포함시킵니다.

```dockerfile
FROM us-central1-docker.pkg.dev/genuine-flight-317411/devel/holmes:latest
RUN curl -O https://dl.min.io/client/mc/release/linux-amd64/mc && \
    chmod +x mc && mv mc /usr/local/bin/
```

빌드하고 레지스트리에 푸시합니다.

```bash
docker build -t your-registry/holmes-minio:latest .
docker push your-registry/holmes-minio:latest
```

### mc alias 설정

`mc alias`는 MinIO 서버의 접속 정보(엔드포인트, Access Key, Secret Key)를 로컬에 등록하는 명령입니다. 도구셋의 모든 명령이 이 alias를 참조합니다.

CLI 환경에서 직접 설정하는 경우:

```bash
mc alias set myminio http://minio.storage.svc.cluster.local:9000 ACCESS_KEY SECRET_KEY
```

Kubernetes 환경에서는 `MC_HOST_myminio` 환경 변수를 사용하면 `mc alias set` 명령 없이 alias가 자동 등록됩니다. 형식은 다음과 같습니다.

```
https://ACCESS_KEY:SECRET_KEY@minio.storage.svc.cluster.local:9000
```

## 도구셋 YAML

다음 내용을 `minio-toolset.yaml` 파일로 저장합니다. 전체 예시 파일은 `docs2/examples/toolsets/minio-toolset.yaml`에 있습니다.

```yaml
toolsets:
  minio/storage:
    description: "MinIO object storage management and status inspection tools"
    prerequisites:
      - command: "mc alias list myminio"
      - env:
          - MC_HOST_myminio
    llm_instructions: |
      You have access to MinIO object storage tools for investigating storage issues.
      Use minio_service_status and minio_disk_info first when server health problems are suspected.
      For bucket-level investigation, start with minio_list_buckets to identify targets,
      then use minio_bucket_info or minio_list_objects for details.
      For erasure-coded deployments, check minio_healing_status to detect data integrity issues.
    tools:
      - name: "minio_list_buckets"
        description: "List all buckets in MinIO server"
        command: "mc ls myminio"

      - name: "minio_bucket_info"
        description: "Get detailed information about a specific bucket including size and object count"
        command: "mc stat myminio/{{ bucket_name }}"

      - name: "minio_list_objects"
        description: "List objects in a bucket with optional prefix filter and summary"
        command: "mc ls myminio/{{ bucket_name }}{% if prefix %}/{{ prefix }}{% endif %} --summarize"

      - name: "minio_disk_info"
        description: "Show MinIO server information including disk usage and connected drives"
        command: "mc admin info myminio"

      - name: "minio_service_status"
        description: "Check MinIO server service status and health in JSON format"
        command: "mc admin info myminio --json"

      - name: "minio_healing_status"
        description: "Check healing status for MinIO erasure-coded setup (dry-run mode)"
        command: "mc admin heal myminio --dry-run"
```

각 도구의 역할은 다음과 같습니다.

| 도구 이름 | 설명 |
|-----------|------|
| minio_list_buckets | 서버의 전체 버킷 목록 조회 |
| minio_bucket_info | 특정 버킷의 크기, 오브젝트 수 등 상세 정보 조회 |
| minio_list_objects | 버킷 내 오브젝트 목록 조회 (prefix 필터 및 요약 지원) |
| minio_disk_info | 서버 정보 및 디스크 사용량 조회 |
| minio_service_status | 서버 상태를 JSON 형식으로 조회 |
| minio_healing_status | Erasure coding 환경의 데이터 복구 상태 확인 |

## CLI 환경 설정

`~/.holmes/config.yaml`에 도구셋 파일 경로를 추가합니다.

```yaml
custom_toolsets:
  - /path/to/minio-toolset.yaml
```

환경 변수를 설정합니다.

```bash
export MC_HOST_myminio="https://ACCESS_KEY:SECRET_KEY@minio.storage.svc.cluster.local:9000"
```

도구셋이 정상 로드되었는지 확인합니다.

```bash
holmes toolset list
```

## Helm Chart 설정

Kubernetes에 배포된 HolmesGPT에 MinIO 도구셋을 연동하는 Helm values 설정입니다.

```yaml
holmes:
  image:
    repository: your-registry/holmes-minio
    tag: latest
  toolsets:
    minio/storage:
      enabled: true
  additionalEnvVars:
    - name: MC_HOST_myminio
      valueFrom:
        secretKeyRef:
          name: minio-credentials
          key: mc-host-url
```

Secret을 먼저 생성합니다.

```bash
kubectl create secret generic minio-credentials \
  -n holmes \
  --from-literal=mc-host-url="https://ACCESS_KEY:SECRET_KEY@minio.storage.svc.cluster.local:9000"
```

Helm 배포 또는 업그레이드를 실행합니다.

```bash
helm upgrade holmes robusta/holmes \
  -n holmes \
  -f values.yaml
```

## 사용 예시

```bash
holmes ask "MinIO 서버 상태를 확인해줘"
```

```bash
holmes ask "myminio 버킷 목록과 각 버킷의 용량을 보여줘"
```

```bash
holmes ask "MinIO 디스크 상태에 문제가 있는지 확인해줘"
```

```bash
holmes ask "data-lake 버킷에서 2024/01 prefix 아래 오브젝트 목록을 보여줘"
```

```bash
holmes ask "MinIO erasure coding 힐링 상태를 점검해줘"
```

## 트러블슈팅

```bash
# mc alias 연결 확인
mc alias list myminio

# mc 명령이 직접 실행되는지 확인
mc admin info myminio

# HolmesGPT 파드에서 mc 바이너리 존재 확인
kubectl exec -n holmes deployment/holmes -- which mc

# MC_HOST_myminio 환경 변수가 주입되었는지 확인
kubectl exec -n holmes deployment/holmes -- env | grep MC_HOST
```
