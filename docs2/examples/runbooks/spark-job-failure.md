# Spark 작업 실패 조사 런북

## Goal
SparkApplication이 FAILED 상태인 경우, 실패 원인을 체계적으로 분석하고 해결 방안을 제시합니다.

## Workflow

1. **SparkApplication 상태 확인**
   - SparkApplication 리소스의 현재 상태를 조회합니다.
   - status.applicationState.state가 FAILED인지 확인합니다.
   - status.applicationState.errorMessage에서 에러 메시지를 확인합니다.

2. **드라이버 파드 로그 확인**
   - 드라이버 파드({app_name}-driver)의 로그를 조회합니다.
   - Exception, Error, OOM, OutOfMemoryError 키워드를 검색합니다.
   - 스택 트레이스에서 실패 원인을 파악합니다.

3. **익스큐터 상태 확인**
   - 익스큐터 파드 목록과 상태를 조회합니다.
   - OOMKilled, Error, CrashLoopBackOff 상태인 익스큐터가 있는지 확인합니다.
   - 익스큐터 파드의 이벤트를 확인합니다.

4. **리소스 사용량 확인**
   - 드라이버와 익스큐터의 메모리/CPU 요청량과 제한을 확인합니다.
   - 노드의 리소스 여유 상황을 확인합니다.
   - Pending 상태의 파드가 있다면 스케줄링 실패 원인을 조사합니다.

5. **의존성 확인**
   - 외부 데이터 소스 (S3/MinIO, HDFS, 데이터베이스) 접근 가능 여부를 확인합니다.
   - 네트워크 정책으로 차단된 연결이 있는지 확인합니다.

## Synthesis
- 드라이버 로그의 에러 메시지와 익스큐터 상태를 종합하여 근본 원인을 파악합니다.
- OOM인 경우 어떤 단계에서 메모리 부족이 발생했는지 특정합니다.
- 의존성 문제인 경우 어떤 외부 시스템과의 연결이 실패했는지 명시합니다.

## Remediation
- **OOM (메모리 부족)**: spark.driver.memory 또는 spark.executor.memory 증가, 데이터 파티션 수 조정
- **드라이버 크래시**: 코드 에러 수정, 의존성 라이브러리 버전 확인
- **익스큐터 타임아웃**: spark.network.timeout 증가, 노드 리소스 확인
- **스케줄링 실패**: 노드 리소스 여유 확인, nodeSelector/toleration 설정 검토
- **외부 의존성 문제**: 연결 정보 확인, 네트워크 정책 검토
