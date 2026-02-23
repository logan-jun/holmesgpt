# JupyterHub 사용자 세션 문제 런북

## Goal
JupyterHub 사용자의 노트북 서버가 시작되지 않거나 세션 관련 문제가 발생할 때 원인을 분석합니다.

## Workflow

1. **사용자 서버 상태 확인**
   - JupyterHub API로 사용자 정보를 조회합니다.
   - 서버가 pending, ready, stopped 중 어떤 상태인지 확인합니다.
   - 최근 활동 시간과 서버 시작 시간을 확인합니다.

2. **사용자 노트북 파드 확인**
   - JupyterHub 네임스페이스에서 사용자의 파드를 찾습니다 (jupyter-{username}).
   - 파드 상태, 이벤트, Restart 횟수를 확인합니다.
   - Pending 상태라면 스케줄링 실패 원인을 조사합니다.

3. **JupyterHub Hub 파드 상태 확인**
   - Hub 파드 자체의 상태와 로그를 확인합니다.
   - Spawner 관련 에러 로그를 검색합니다.

4. **리소스 확인**
   - 노드의 리소스 여유 상황을 확인합니다.
   - PVC(영구 볼륨) 바인딩 상태를 확인합니다.
   - StorageClass 설정이 올바른지 확인합니다.

5. **프록시 상태 확인**
   - JupyterHub 프록시 라우팅 테이블을 조회합니다.
   - 사용자 서버로의 라우팅이 올바르게 설정되어 있는지 확인합니다.

## Synthesis
- 사용자 서버 파드 상태와 Hub 로그를 종합하여 문제 원인을 파악합니다.
- 스케줄링 문제, 스토리지 문제, 네트워크 문제 중 해당하는 것을 특정합니다.

## Remediation
- **스케줄링 실패**: 노드 리소스 확인, resource guarantee/limit 조정
- **PVC 바인딩 실패**: StorageClass 확인, PV 용량 확인
- **Spawner 타임아웃**: spawn_timeout 설정 증가
- **프록시 문제**: Hub 파드 재시작, 프록시 라우팅 테이블 리셋
