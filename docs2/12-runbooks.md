# 커스텀 런북 작성 가이드

런북(Runbook)은 특정 장애나 이슈에 대한 조사 절차를 마크다운으로 코드화한 것입니다. HolmesGPT는 알림 조사 시 관련 런북을 `fetch_runbook` 도구를 통해 on-demand로 가져와서 참조하며, 런북에 기술된 단계에 따라 체계적으로 조사를 수행합니다.

---

## 런북 시스템 개요

런북 시스템은 두 가지 핵심 요소로 구성됩니다.

**catalog.json**

런북 메타데이터를 관리하는 카탈로그 파일입니다. 각 런북의 ID, 설명, 파일 경로를 포함하며, HolmesGPT는 이 카탈로그를 참조하여 사용 가능한 런북 목록을 LLM에 제공합니다. LLM은 조사 중인 알림과 관련된 런북을 판단하여 필요한 런북만 선택적으로 로드합니다.

**런북 마크다운 파일**

실제 조사 절차가 기술된 `.md` 파일입니다. HolmesGPT는 런북의 내용을 지시서로 받아들이고, 각 단계에 따라 도구를 호출하여 조사를 수행합니다.

런북의 동작 흐름은 다음과 같습니다.

1. HolmesGPT가 카탈로그에서 사용 가능한 런북 목록을 확인
2. LLM이 현재 조사 중인 이슈와 관련된 런북을 판단
3. `fetch_runbook` 도구로 해당 런북 마크다운을 로드
4. 런북에 기술된 조사 단계를 순서대로 실행 (도구 호출)
5. 조사 결과를 종합하여 근본 원인과 해결 방안을 제시

---

## catalog.json 작성법

카탈로그 파일은 `catalog` 배열 안에 런북 항목을 나열하는 JSON 파일입니다. 각 항목은 다음 필드를 포함합니다.

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | string | 런북의 고유 식별자 |
| `update_date` | string | 마지막 업데이트 날짜 (ISO 8601 형식, 예: `2025-06-15`) |
| `description` | string | 런북의 목적과 대상 장애를 설명하는 텍스트. LLM이 런북 선택 시 참조 |
| `link` | string | 런북 마크다운 파일의 상대 경로 (catalog.json 기준) |

```json
{
  "catalog": [
    {
      "id": "spark-job-failure",
      "update_date": "2025-06-15",
      "description": "SparkApplication FAILED 상태 원인 분석. Spark Operator가 관리하는 SparkApplication이 실패했을 때 드라이버 로그, Executor 로그, Kubernetes 이벤트를 종합하여 원인을 진단합니다.",
      "link": "spark-job-failure.md"
    },
    {
      "id": "fastapi-pod-health",
      "update_date": "2025-06-15",
      "description": "FastAPI 서비스 파드의 헬스체크 실패 또는 CrashLoopBackOff 원인 조사. 파드 상태, 로그, 리소스 사용량, Readiness/Liveness Probe 설정을 확인합니다.",
      "link": "fastapi-pod-health.md"
    },
    {
      "id": "jupyterhub-session",
      "update_date": "2025-06-15",
      "description": "JupyterHub 사용자 서버 시작 실패 또는 세션 문제 조사. 사용자별 노트북 서버 파드 상태, PVC 바인딩, 리소스 할당을 점검합니다.",
      "link": "jupyterhub-session.md"
    }
  ]
}
```

`description` 필드는 LLM이 런북 선택 시 참조하는 핵심 정보입니다. 런북이 다루는 장애 유형, 관련 컴포넌트, 조사 범위를 구체적으로 기술하면 LLM이 적절한 런북을 선택할 확률이 높아집니다.

---

## 런북 마크다운 구조

런북 마크다운은 다음 네 가지 섹션으로 구성합니다. HolmesGPT는 이 런북을 지시서로 받아들이고, Workflow 섹션의 단계에 따라 도구를 호출하여 조사를 수행합니다.

```markdown
# Spark 작업 실패 진단

## Goal
SparkApplication이 FAILED 상태일 때 근본 원인을 파악합니다.
Spark Operator 환경에서 드라이버 또는 Executor 수준의 실패 원인을 체계적으로 조사합니다.

## Workflow
1. 실패한 SparkApplication 리소스의 상세 상태를 확인합니다.
   - status.applicationState, status.terminationTime 등 핵심 필드를 확인합니다.
2. SparkApplication에 연결된 드라이버 파드를 찾고 상태를 확인합니다.
   - 파드가 OOMKilled, Error 등 비정상 종료되었는지 확인합니다.
3. 드라이버 파드의 로그에서 에러 메시지와 스택 트레이스를 확인합니다.
   - OutOfMemoryError, ClassNotFoundException 등 주요 에러 패턴을 찾습니다.
4. Executor 파드들의 상태와 로그를 확인합니다.
   - Executor가 비정상 종료된 경우 해당 로그를 확인합니다.
5. 관련 Kubernetes 이벤트를 확인합니다.
   - 리소스 부족(Insufficient cpu/memory), 스케줄링 실패 등 클러스터 수준 이슈를 확인합니다.
6. 드라이버와 Executor의 리소스 요청량(requests)과 제한량(limits)을 확인합니다.

## Synthesis
수집한 데이터에서 다음을 종합하여 근본 원인을 파악합니다:
- 드라이버 로그의 에러가 코드 문제인지 리소스 문제인지 분류
- Executor 장애가 데이터 스큐나 메모리 부족에 의한 것인지 판단
- Kubernetes 이벤트에서 클러스터 수준 제약(노드 리소스 부족, PVC 미바인딩 등) 확인

## Remediation
일반적인 해결 방법:
- OOMKilled: 드라이버/Executor 메모리 limits 증가 또는 spark.executor.memoryOverhead 조정
- ClassNotFoundException: JAR 의존성 확인 및 spark.jars, spark.packages 설정 점검
- 스케줄링 실패: 노드 리소스 확인 및 리소스 requests/limits 조정
- 에스컬레이션 기준: 동일 작업이 3회 이상 연속 실패하면 데이터 엔지니어링 팀에 알림
```

---

## 런북 디렉토리 구성

커스텀 런북은 하나의 디렉토리에 `catalog.json`과 `.md` 파일을 함께 배치합니다. HolmesGPT는 `catalog.json`이 위치한 디렉토리를 런북 검색 경로에 자동으로 추가합니다.

```
/etc/holmes/runbooks/
  catalog.json
  spark-job-failure.md
  fastapi-pod-health.md
  jupyterhub-session.md
```

카테고리별로 하위 디렉토리를 구성하는 경우 `link` 필드에 상대 경로를 지정합니다.

```
/etc/holmes/runbooks/
  catalog.json
  data-engineering/
    spark-job-failure.md
    spark-connect-issues.md
  platform/
    jupyterhub-session.md
    fastapi-pod-health.md
```

이 경우 catalog.json의 `link` 필드를 다음과 같이 작성합니다.

```json
{
  "catalog": [
    {
      "id": "spark-job-failure",
      "update_date": "2025-06-15",
      "description": "SparkApplication FAILED 상태 원인 분석",
      "link": "data-engineering/spark-job-failure.md"
    },
    {
      "id": "jupyterhub-session",
      "update_date": "2025-06-15",
      "description": "JupyterHub 사용자 서버 시작 실패 조사",
      "link": "platform/jupyterhub-session.md"
    }
  ]
}
```

---

## config.yaml 통합

`~/.holmes/config.yaml`에 `custom_runbook_catalogs` 필드로 카탈로그 파일 경로를 지정합니다.

```yaml
custom_runbook_catalogs:
  - /etc/holmes/runbooks/catalog.json
```

여러 카탈로그를 동시에 사용할 수 있습니다. 팀별로 런북을 분리 관리하는 경우에 유용합니다.

```yaml
custom_runbook_catalogs:
  - /etc/holmes/runbooks/data-engineering/catalog.json
  - /etc/holmes/runbooks/platform/catalog.json
  - /etc/holmes/runbooks/sre/catalog.json
```

`custom_runbooks` 필드는 더 이상 사용하지 않습니다. 기존에 이 필드를 사용하고 있다면 `custom_runbook_catalogs`로 마이그레이션하시기 바랍니다. 카탈로그 기반 시스템은 LLM이 관련 런북만 선택적으로 로드하므로 토큰을 효율적으로 사용합니다.

---

## Helm values 통합

Kubernetes에 배포하는 경우 런북 파일을 ConfigMap으로 마운트합니다.

**ConfigMap 생성:**

```bash
kubectl create configmap holmes-runbooks \
  --from-file=catalog.json=/path/to/runbooks/catalog.json \
  --from-file=spark-job-failure.md=/path/to/runbooks/spark-job-failure.md \
  --from-file=fastapi-pod-health.md=/path/to/runbooks/fastapi-pod-health.md \
  --from-file=jupyterhub-session.md=/path/to/runbooks/jupyterhub-session.md \
  -n holmes
```

**Helm values.yaml:**

```yaml
additionalVolumes:
  - name: custom-runbooks
    configMap:
      name: holmes-runbooks

additionalVolumeMounts:
  - name: custom-runbooks
    mountPath: /etc/holmes/runbooks
    readOnly: true

config:
  custom_runbook_catalogs:
    - /etc/holmes/runbooks/catalog.json
```

ConfigMap의 크기 제한(1MB)에 주의하시기 바랍니다. 런북 파일이 많은 경우 여러 ConfigMap으로 분리하거나 PVC를 사용합니다.

---

## 런북 작성 팁

**Goal 섹션**

- 런북이 다루는 장애 상황을 명확하고 구체적으로 기술합니다.
- 대상 시스템과 조사 범위를 명시합니다.

**Workflow 섹션**

- HolmesGPT가 도구를 호출할 수 있는 구체적인 조사 단계로 작성합니다.
- 특정 CLI 명령을 직접 기술하기보다 조사 의도를 기술합니다. HolmesGPT가 적절한 도구를 선택합니다.
- 조건부 분기가 필요한 경우 "만약 ~인 경우 ~를 추가로 확인합니다" 형태로 기술합니다.

```markdown
# 조사 의도를 기술하는 방식 (권장)
1. 파드의 상세 상태와 이벤트를 확인합니다.
2. 파드의 최근 로그에서 에러 패턴을 확인합니다.
3. OOMKilled가 확인되면 컨테이너의 리소스 limits를 확인합니다.

# 특정 명령을 나열하는 방식 (비권장)
1. kubectl describe pod <pod-name> 실행
2. kubectl logs <pod-name> --tail=100 실행
```

**Synthesis 섹션**

- 수집한 데이터를 종합하는 기준을 제시합니다.
- 어떤 데이터 조합이 어떤 근본 원인을 시사하는지 가이드합니다.

**Remediation 섹션**

- 원인별 권장 조치를 기술합니다.
- 에스컬레이션 기준이 있다면 명시합니다.
- HolmesGPT는 읽기 전용 도구만 사용하므로 수정 작업 자체를 수행하지 않습니다. 이 섹션은 운영자에게 전달할 권고사항입니다.

---

## 런북 출력 형식

HolmesGPT가 런북을 사용하여 조사를 완료하면, 다음과 같은 형식으로 결과를 보고합니다.

```
I found a runbook named **Spark 작업 실패 진단** and used it to troubleshoot:

1. ✅ *SparkApplication 상태 확인* - status.applicationState: FAILED, terminationTime: 2025-06-15T03:22:00Z
2. ✅ *드라이버 파드 상태 확인* - spark-etl-daily-driver OOMKilled (exit code 137)
3. ✅ *드라이버 로그 에러 확인* - java.lang.OutOfMemoryError: Java heap space
4. ✅ *Executor 파드 확인* - 3개 Executor 중 2개 정상 완료, 1개 OOMKilled
5. ✅ *Kubernetes 이벤트 확인* - 별도 스케줄링 이슈 없음
6. ✅ *리소스 설정 확인* - 드라이버 memory limit 2Gi, Executor memory limit 4Gi

**Root cause:** 드라이버 파드의 Java heap 메모리 부족 (2Gi limit에서 OOMKilled)

**Fix:** 드라이버 메모리 limits를 4Gi 이상으로 증가하거나, spark.driver.memoryOverhead 설정을 추가
```

각 조사 단계의 완료 여부가 체크리스트 형태로 표시되며, 도구가 없어서 수행하지 못한 단계는 그 이유와 함께 표시됩니다.
