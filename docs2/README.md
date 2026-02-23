# HolmesGPT 사내 도입 가이드

본 문서는 HolmesGPT를 사내 인프라 환경에 도입하기 위한 종합 가이드입니다.
On-prem Kubernetes 및 Amazon EKS 환경에서의 배포, 내장 도구셋 활용, 커스텀 도구셋 개발, 그리고 실무 사용 사례를 다룹니다.

## 문서 목록

| 파일명 | 설명 | 대상 독자 |
|--------|------|-----------|
| [01-overview.md](01-overview.md) | HolmesGPT 개요 및 도입 가치 | 전체 |
| [02-architecture.md](02-architecture.md) | 에이전틱 조사 루프 아키텍처 | 아키텍트 / SRE |
| [03-deployment-onprem.md](03-deployment-onprem.md) | 온프레미스 K8s 배포 가이드 | DevOps |
| [04-deployment-eks.md](04-deployment-eks.md) | Amazon EKS 배포 가이드 | DevOps |
| [05-builtin-toolsets.md](05-builtin-toolsets.md) | 내장 도구셋 활용 | SRE / 운영 |
| [06-custom-toolset-minio.md](06-custom-toolset-minio.md) | MinIO 커스텀 도구셋 | SRE |
| [07-custom-toolset-spark-operator.md](07-custom-toolset-spark-operator.md) | Spark Operator 도구셋 | 데이터 엔지니어 |
| [08-custom-toolset-spark-connect.md](08-custom-toolset-spark-connect.md) | Spark Connect 도구셋 | 데이터 엔지니어 |
| [09-custom-toolset-jupyterhub.md](09-custom-toolset-jupyterhub.md) | JupyterHub 도구셋 | 플랫폼 / ML 엔지니어 |
| [10-custom-toolset-fastapi.md](10-custom-toolset-fastapi.md) | FastAPI 도구셋 | 백엔드 개발자 |
| [11-config-reference.md](11-config-reference.md) | 통합 config.yaml 참조 | 전체 |
| [12-runbooks.md](12-runbooks.md) | 커스텀 런북 작성 | SRE |
| [13-usecases.md](13-usecases.md) | 사용 사례 및 예시 프롬프트 | 전체 |
| [14-deep-agent-architecture.md](14-deep-agent-architecture.md) | 딥 에이전트 아키텍처 개선 계획 | 아키텍트 / SRE |
| [15-langchain-integration.md](15-langchain-integration.md) | LangChain 도구 통합 가이드 | 아키텍트 / SRE |

## 환경 컴포넌트별 문서 매핑

사내 환경에서 사용 중인 컴포넌트에 따라 참고해야 할 문서를 안내합니다.

| 환경 컴포넌트 | 관련 문서 |
|---------------|-----------|
| On-prem Kubernetes | 01, 02, 03, 05, 11 |
| Amazon EKS | 01, 02, 04, 05, 11 |
| Grafana | 05, 11, 13 |
| Prometheus | 05, 11, 13 |
| ArgoCD | 05, 11, 13 |
| MinIO | 06, 11 |
| Spark Operator | 07, 11 |
| Spark Connect | 08, 11 |
| JupyterHub | 09, 11 |
| FastAPI | 10, 11 |
| 런북 운영 | 12, 13 |
| 아키텍처 개선 | 02, 14, 15 |

## Quick Start

처음 도입하는 경우 아래 순서를 따릅니다.

**1단계 -- 설치**

배포 환경에 맞는 문서를 선택하여 HolmesGPT를 설치합니다.

- On-prem Kubernetes: [03-deployment-onprem.md](03-deployment-onprem.md)
- Amazon EKS: [04-deployment-eks.md](04-deployment-eks.md)

**2단계 -- 설정**

통합 설정 파일을 구성합니다.

- [11-config-reference.md](11-config-reference.md)

**3단계 -- 내장 도구셋 확인**

Kubernetes, Prometheus, Grafana, ArgoCD 등 내장 도구셋의 활성화 상태를 확인하고 필요한 도구셋을 설정합니다.

- [05-builtin-toolsets.md](05-builtin-toolsets.md)

**4단계 -- 사용**

자연어 질문과 알림 자동 조사 기능을 활용하여 인프라 문제를 진단합니다.

- [13-usecases.md](13-usecases.md)

## 사전 요구 사항

- Kubernetes 클러스터 (On-prem 또는 EKS)
- Helm 3.x
- `kubectl` 접근 권한 (ClusterRole 바인딩 필요)
- LLM 엔드포인트 (vLLM 자체 호스팅 `gpt-oss-120b` 또는 외부 API)
- Python 3.11 이상 (CLI 직접 설치 시)
