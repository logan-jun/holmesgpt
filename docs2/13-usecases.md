# 사용 사례 및 예시 프롬프트

사내 인프라 환경에서 HolmesGPT를 활용하는 실전 예시 프롬프트 모음입니다. 각 프롬프트는 `holmes ask` 명령으로 바로 실행할 수 있습니다.

---

## Kubernetes 일반

```bash
holmes ask "CrashLoopBackOff 상태인 파드가 있는지 확인해줘"
```

```bash
holmes ask "default 네임스페이스에서 CPU/메모리 사용량이 높은 파드를 찾아줘"
```

```bash
holmes ask "최근 실패한 Job이 있으면 원인을 분석해줘"
```

```bash
holmes ask "Pending 상태인 PVC가 있는지 확인하고 원인을 알려줘"
```

```bash
holmes ask "kube-system 네임스페이스에서 재시작 횟수가 높은 파드를 찾아줘"
```

---

## ArgoCD

```bash
holmes ask "OutOfSync 상태인 ArgoCD 애플리케이션이 있는지 확인해줘"
```

```bash
holmes ask "payment-service 앱의 배포 이력과 현재 상태를 보여줘"
```

```bash
holmes ask "ArgoCD 앱 중 Degraded 상태인 것의 원인을 분석해줘"
```

```bash
holmes ask "ArgoCD에서 Sync 실패한 앱이 있으면 desired state와 live state의 차이를 확인해줘"
```

---

## Prometheus / Grafana

```bash
holmes ask "최근 1시간 동안 CPU 사용률이 80%를 넘은 노드가 있는지 확인해줘"
```

```bash
holmes ask "현재 firing 상태인 알림 규칙을 보여줘"
```

```bash
holmes ask "메모리 관련 Grafana 대시보드를 찾아줘"
```

```bash
holmes ask "노드별 디스크 사용률을 확인해줘"
```

---

## Spark 작업

```bash
holmes ask "FAILED 상태인 SparkApplication이 있는지 확인하고 원인을 분석해줘"
```

```bash
holmes ask "spark-etl-daily 작업의 드라이버 로그에서 에러를 찾아줘"
```

```bash
holmes ask "오늘 스케줄된 Spark 작업 중 아직 완료되지 않은 것을 보여줘"
```

```bash
holmes ask "spark-jobs 네임스페이스에서 OOMKilled된 Executor 파드가 있는지 확인해줘"
```

---

## MinIO

```bash
holmes ask "MinIO 서버 상태와 디스크 사용량을 확인해줘"
```

```bash
holmes ask "data-lake 버킷의 오브젝트 목록과 총 용량을 보여줘"
```

```bash
holmes ask "MinIO에서 에러가 발생한 버킷이 있는지 확인해줘"
```

---

## JupyterHub

```bash
holmes ask "JupyterHub에서 현재 활성 세션이 있는 사용자 목록을 보여줘"
```

```bash
holmes ask "사용자 kim의 JupyterHub 서버가 시작되지 않는 원인을 조사해줘"
```

```bash
holmes ask "jhub 네임스페이스에서 Pending 상태인 jupyter 파드를 찾아서 원인을 알려줘"
```

---

## FastAPI 서비스

```bash
holmes ask "user-service의 헬스체크 상태를 확인해줘"
```

```bash
holmes ask "order-service 파드가 재시작되고 있는 원인을 분석해줘"
```

```bash
holmes ask "api-gateway 서비스의 파드 상태와 최근 로그를 확인해줘"
```

---

## 복합 시나리오

여러 컴포넌트를 동시에 조사해야 하는 경우, 하나의 프롬프트로 전체적인 상태 점검을 요청할 수 있습니다.

```bash
holmes ask "data-pipeline 네임스페이스의 전반적인 상태를 확인해줘. Spark 작업, MinIO 스토리지, 관련 파드 상태를 모두 살펴봐줘"
```

```bash
holmes ask "production 네임스페이스에서 비정상인 리소스를 전부 찾아서 원인을 분석해줘"
```

```bash
holmes ask "최근 1시간 내에 재시작된 파드가 있으면, 해당 파드의 로그와 이벤트를 함께 확인해줘"
```

---

## 대화형 모드 활용

`--interactive` 플래그를 사용하면 이전 대화 컨텍스트를 유지하면서 연속으로 질문할 수 있습니다. 복잡한 문제를 단계적으로 조사할 때 유용합니다.

```bash
holmes ask --interactive
```

대화형 모드에서 사용할 수 있는 슬래시 커맨드입니다.

| 커맨드 | 설명 |
|--------|------|
| `/help` | 사용 가능한 커맨드 목록 표시 |
| `/tools` | 활성화된 도구셋과 상태 확인 |
| `/clear` | 대화 기록 초기화 |
| `/context` | 토큰 사용량과 컨텍스트 크기 확인 |
| `/auto` | 도구 출력 자동 표시 토글 |
| `/last` | 마지막 응답의 도구 출력 다시 보기 |
| `/show [번호\|이름]` | 특정 도구 출력을 스크롤 가능한 모달로 보기 |
| `/run <명령>` | 셸 명령 실행 후 결과를 AI와 공유 |
| `/shell` | 대화형 셸 세션 시작 |
| `/exit` | 대화형 모드 종료 |

대화형 모드 사용 예시:

```
> spark-etl-daily 작업이 실패했어. 원인을 찾아줘

(HolmesGPT가 SparkApplication 상태, 드라이버 로그 등을 조사하여 응답)

> 드라이버 로그에서 OOM이 보이는데, 현재 메모리 설정이 어떻게 되어 있어?

(이전 컨텍스트를 유지한 상태로 추가 조사 수행)

> 같은 네임스페이스의 다른 Spark 작업들은 정상인지 확인해줘

(연속 조사를 통해 문제 범위를 파악)
```

---

## AlertManager 알림 자동 조사

`investigate` 서브커맨드로 AlertManager에서 현재 firing 상태인 알림을 자동으로 조사합니다.

```bash
holmes investigate alertmanager \
  --alertmanager-url http://alertmanager.monitoring.svc:9093
```

특정 알림만 필터링하여 조사할 수 있습니다.

```bash
holmes investigate alertmanager \
  --alertmanager-url http://alertmanager.monitoring.svc:9093 \
  --alertmanager-alertname "SparkJobFailed"
```

커스텀 런북이 설정되어 있는 경우, HolmesGPT는 알림과 관련된 런북을 자동으로 참조하여 조사합니다. 런북 작성 방법은 [12-runbooks.md](12-runbooks.md)를 참조하시기 바랍니다.
