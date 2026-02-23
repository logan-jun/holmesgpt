# Spark Operator 커스텀 도구셋

Kubernetes에서 실행되는 Spark Operator (SparkApplication CRD) 작업을 조사하기 위한 YAML 기반 커스텀 도구셋입니다.

## 도구셋 타입: YAML (kubectl CRD 기반)

Spark Operator는 SparkApplication 및 ScheduledSparkApplication CRD를 통해 Spark 작업을 관리합니다. 이 도구셋은 kubectl을 사용하여 CRD를 조회하므로 추가 바이너리가 필요하지 않습니다.

- SparkApplication, ScheduledSparkApplication CRD 조회
- 드라이버 및 익스큐터 파드 상태 확인
- 작업 실패 시 드라이버 로그 수집

RBAC 설정에서 `sparkoperator.k8s.io` API 그룹에 대한 읽기 권한이 필요합니다.

## RBAC 설정

HolmesGPT가 SparkApplication CRD를 조회하려면 ServiceAccount에 해당 API 그룹 권한을 부여해야 합니다. Helm 차트를 사용하는 경우 `customClusterRoleRules`에 다음을 추가합니다.

```yaml
# Helm values.yaml
customClusterRoleRules:
  - apiGroups: ["sparkoperator.k8s.io"]
    resources: ["sparkapplications", "scheduledsparkapplications"]
    verbs: ["get", "list", "watch"]
```

직접 ClusterRole을 관리하는 경우 동일한 규칙을 추가합니다.

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: holmes-spark-operator
rules:
  - apiGroups: ["sparkoperator.k8s.io"]
    resources: ["sparkapplications", "scheduledsparkapplications"]
    verbs: ["get", "list", "watch"]
```

## 도구셋 YAML

아래 YAML 파일을 생성하고 `config.yaml`의 `custom_toolsets`에 경로를 추가합니다.

```yaml
# ~/.holmes/config.yaml
custom_toolsets:
  - /etc/holmes/toolsets/spark-operator-toolset.yaml
```

**spark-operator-toolset.yaml:**

```yaml
toolsets:
  spark/operator:
    description: "Spark Operator (SparkApplication CRD) 작업 조사 도구"
    prerequisites:
      - command: "kubectl api-resources | grep sparkapplications"
    llm_instructions: |
      Spark Operator로 관리되는 SparkApplication을 조사하는 도구입니다.
      SparkApplication의 상태는 spec.status.applicationState.state 필드에 있으며,
      주요 상태값: SUBMITTED, RUNNING, COMPLETED, FAILED, UNKNOWN
      작업 실패 시 드라이버 로그를 먼저 확인하세요.
      일반적인 실패 원인: OOM (메모리 부족), Driver crash, Executor timeout, 의존성 문제
    tools:
      - name: "spark_list_apps"
        description: "List all SparkApplications across namespaces with their status"
        command: "kubectl get sparkapplications -A -o wide"

      - name: "spark_get_app"
        description: "Get detailed information about a specific SparkApplication"
        command: "kubectl describe sparkapplication {{ app_name }} -n {{ namespace }}"

      - name: "spark_app_status"
        description: "Get the status and state of a SparkApplication in JSON format"
        command: "kubectl get sparkapplication {{ app_name }} -n {{ namespace }} -o jsonpath='{.status}' | jq ."

      - name: "spark_driver_logs"
        description: "Get logs from a Spark driver pod for a specific application"
        command: "kubectl logs {{ app_name }}-driver -n {{ namespace }} --tail=200"

      - name: "spark_list_scheduled"
        description: "List all ScheduledSparkApplications with their schedule and status"
        command: "kubectl get scheduledsparkapplications -A -o wide"

      - name: "spark_executor_status"
        description: "Get status of executor pods for a Spark application"
        command: "kubectl get pods -n {{ namespace }} -l sparkoperator.k8s.io/app-name={{ app_name }},spark-role=executor -o wide"
```

## 변수 설명

도구 명령에서 사용되는 변수는 LLM이 사용자 질문의 맥락에서 자동으로 추론합니다.

| 변수 | 설명 | 예시 |
|------|------|------|
| `{{ app_name }}` | SparkApplication 이름 | `spark-etl-job` |
| `{{ namespace }}` | Kubernetes 네임스페이스 | `spark-jobs` |

## SparkApplication 상태 필드

SparkApplication CRD의 `.status.applicationState.state` 필드에서 작업 상태를 확인할 수 있습니다.

| 상태 | 설명 |
|------|------|
| SUBMITTED | 작업이 제출됨, 드라이버 파드 생성 대기 |
| RUNNING | 드라이버 및 익스큐터 실행 중 |
| COMPLETED | 정상 완료 |
| FAILED | 실패 (드라이버 로그 확인 필요) |
| UNKNOWN | 상태 확인 불가 |

## 일반적인 실패 패턴

**OOM (Out of Memory)**

드라이버 또는 익스큐터의 메모리가 부족한 경우입니다. 드라이버 로그에 `java.lang.OutOfMemoryError`가 나타나며, SparkApplication spec에서 `spark.driver.memory` 또는 `spark.executor.memory` 값을 조정해야 합니다.

**Driver Crash**

드라이버 파드가 비정상 종료된 경우입니다. 코드 에러, 의존성 누락, 잘못된 설정 등이 원인이며, `spark_driver_logs` 도구로 드라이버 로그를 먼저 확인합니다.

**Executor Timeout**

익스큐터가 드라이버와의 통신에 실패하거나 태스크 처리 시간이 초과된 경우입니다. `spark_executor_status` 도구로 익스큐터 파드 상태와 노드 배치를 확인하고, 네트워크 또는 리소스 문제를 조사합니다.

## 사용 예시

```bash
holmes ask "FAILED 상태인 SparkApplication이 있는지 확인해줘"
```

```bash
holmes ask "spark-etl-job의 실패 원인을 분석해줘"
```

```bash
holmes ask "최근 스케줄된 Spark 작업 목록을 보여줘"
```

```bash
holmes ask "spark-jobs 네임스페이스에서 실행 중인 SparkApplication의 익스큐터 상태를 확인해줘"
```
