# LangChain 커뮤니티 도구 통합 가이드

이 문서는 HolmesGPT의 기존 단일 에이전트 아키텍처를 유지하면서, LangChain 커뮤니티 도구를 선택적으로 도입하는 경량 통합 방안을 제시합니다.

---

## 1. 개요 및 동기

### 현재 아키텍처의 강점

HolmesGPT는 하나의 `ToolCallingLLM` 인스턴스가 `ToolExecutor`를 통해 모든 도구를 관리하는 단일 에이전트 구조입니다. 이 구조는 다음과 같은 강점을 가지고 있습니다.

- **단순한 실행 모델**: 하나의 에이전트 루프가 도구 선택과 실행을 담당하므로 디버깅이 용이합니다.
- **낮은 LLM 비용**: Supervisor/Specialist 간 다중 호출이 없어 API 비용이 예측 가능합니다.
- **검증된 안정성**: 프로덕션 환경에서 운영 중인 구조이므로 추가 위험이 없습니다.
- **기존 도구셋 생태계**: 30개 이상의 내장 도구셋(Kubernetes, Prometheus, Grafana 등)이 이미 안정적으로 작동합니다.

### LangChain 도구 생태계 활용 목적

모든 데이터 소스를 직접 구현하는 것은 비용이 큽니다. LangChain 커뮤니티는 SQL Database, Document Loader, Vector Store 등 수백 개의 검증된 도구를 제공합니다. 이를 활용하면 다음과 같은 이점을 얻을 수 있습니다.

- **구현 비용 절감**: 사내 DB 조회, 문서 시스템 연동 등을 직접 구현하지 않고 커뮤니티 도구를 재사용합니다.
- **빠른 데이터 소스 확장**: 새로운 데이터 소스가 필요할 때 LangChain 커뮤니티 도구를 래핑하여 즉시 도입할 수 있습니다.
- **커뮤니티 유지보수 활용**: 도구의 버그 수정과 기능 개선을 커뮤니티가 담당합니다.

### 핵심 원칙

이 통합 방안의 핵심 원칙은 다음과 같습니다.

1. **아키텍처 변경 최소화**: `ToolCallingLLM`, `ToolExecutor`, `ToolsetManager`의 기존 코드를 수정하지 않습니다.
2. **LangChain은 도구 공급자 역할만**: 에이전트 루프, 오케스트레이션, 상태 관리는 Holmes 고유 엔진을 유지합니다.
3. **선택적 의존성**: LangChain이 설치되지 않은 환경에서도 기존 기능이 정상 작동합니다.

---

## 2. 통합 아키텍처

### 통합 전: 현재 구조

```mermaid
graph TD
    User[사용자 질문 / 알림] --> TCL[ToolCallingLLM]
    TCL --> LLM[LLM Provider\nLiteLLM]
    TCL --> TE[ToolExecutor]
    TE --> T1[kubernetes/core]
    TE --> T2[prometheus/metrics]
    TE --> T3[grafana/dashboards]
    TE --> TN[... 내장 도구셋]

    LLM -.->|function calling| TCL
    TCL -.->|도구 호출 결과| LLM

    style TCL fill:#e1f5fe
    style TE fill:#fff3e0
```

### 통합 후: LangChain 도구 추가

```mermaid
graph TD
    User[사용자 질문 / 알림] --> TCL[ToolCallingLLM\n변경 없음]
    TCL --> LLM[LLM Provider\nLiteLLM]
    TCL --> TE[ToolExecutor\n변경 없음]

    TE --> T1[kubernetes/core]
    TE --> T2[prometheus/metrics]
    TE --> T3[grafana/dashboards]
    TE --> TN[... 내장 도구셋]

    TE --> LCToolset[langchain/tools\nLangChainToolset]

    LCToolset --> Adapter[LangChainToHolmesAdapter]
    Adapter --> LC_SQL[SQL Database Tool]
    Adapter --> LC_Web[Web/URL Tool]
    Adapter --> LC_Doc[Document Loader]
    Adapter --> LC_VS[Vector Store Tool]
    Adapter --> LC_FS[File System Tool]

    LLM -.->|function calling| TCL
    TCL -.->|도구 호출 결과| LLM

    style TCL fill:#e1f5fe
    style TE fill:#fff3e0
    style LCToolset fill:#e8f5e9
    style Adapter fill:#e8f5e9
```

### 핵심 설계 포인트

- **ToolCallingLLM은 변경하지 않습니다.** LangChain 도구는 어댑터를 통해 Holmes `Tool` 인터페이스로 래핑되므로, 기존 에이전트 루프는 LangChain 도구를 일반 Holmes 도구와 동일하게 취급합니다.
- **ToolExecutor도 변경하지 않습니다.** LangChain 도구셋은 `Toolset`을 상속한 `LangChainToolset`으로 등록되므로, 기존 도구셋 로딩 경로를 그대로 사용합니다.
- **ToolsetManager에 LangChain 도구셋 로딩 로직을 추가합니다.** `config.yaml`의 `langchain_tools` 섹션을 읽어 LangChain 도구를 래핑하고, 기존 도구셋 목록에 병합합니다.

---

## 3. 어댑터 설계

### 참조 패턴: MCP 어댑터

MCP 도구셋(`toolset_mcp.py`)은 외부 도구를 Holmes 인터페이스로 래핑하는 검증된 패턴을 제공합니다. LangChain 어댑터는 이 패턴을 따릅니다.

| 항목 | MCP 어댑터 | LangChain 어댑터 |
|------|-----------|-----------------|
| 외부 도구 인터페이스 | `mcp.types.Tool` | `langchain_core.tools.BaseTool` |
| Holmes 도구 클래스 | `RemoteMCPTool(Tool)` | `LangChainToolAdapter(Tool)` |
| Holmes 도구셋 클래스 | `RemoteMCPToolset(Toolset)` | `LangChainToolset(Toolset)` |
| 파라미터 변환 | `MCP_Tool.inputSchema` → `ToolParameter` | `BaseTool.args_schema` → `ToolParameter` |
| 결과 변환 | MCP `CallToolResult` → `StructuredToolResult` | `str` → `StructuredToolResult` |
| 도구 검색 | MCP 서버 `list_tools()` | config.yaml에서 도구 목록 로드 |

### LangChainToHolmesAdapter: LangChain BaseTool → Holmes Tool

LangChain 커뮤니티 도구를 Holmes 도구 인터페이스로 래핑하여, 기존 `ToolExecutor`에 등록합니다.

```python
# 의사 코드 - LangChainToolAdapter
# 실제 구현 위치: holmes/plugins/toolsets/langchain/langchain_adapter.py

from holmes.core.tools import (
    Tool,
    ToolParameter,
    ToolInvokeContext,
    StructuredToolResult,
    StructuredToolResultStatus,
)

class LangChainToolAdapter(Tool):
    """LangChain BaseTool을 Holmes Tool로 래핑합니다.

    MCP 어댑터(RemoteMCPTool)와 동일한 패턴을 따릅니다.
    - 파라미터: BaseTool.args_schema → Dict[str, ToolParameter]
    - 실행: BaseTool.run() → StructuredToolResult
    - 에러 처리: Exception → StructuredToolResult(status=ERROR)
    """

    name: str
    description: str
    _lc_tool: Any = None  # langchain_core.tools.BaseTool 인스턴스

    @classmethod
    def create(cls, lc_tool: "BaseTool") -> "LangChainToolAdapter":
        """LangChain BaseTool로부터 Holmes Tool을 생성합니다."""
        parameters: Dict[str, ToolParameter] = {}
        if hasattr(lc_tool, "args_schema") and lc_tool.args_schema:
            for field_name, field_info in lc_tool.args_schema.model_fields.items():
                parameters[field_name] = ToolParameter(
                    description=field_info.description or "",
                    type=cls._map_type(field_info.annotation),
                    required=field_info.is_required(),
                )

        adapter = cls(
            name=f"lc_{lc_tool.name}",
            description=lc_tool.description or "",
            parameters=parameters,
        )
        adapter._lc_tool = lc_tool
        return adapter

    @staticmethod
    def _map_type(annotation) -> str:
        """Python 타입을 JSON Schema 타입 문자열로 변환합니다."""
        type_map = {int: "integer", float: "number", bool: "boolean", list: "array"}
        return type_map.get(annotation, "string")

    def _invoke(
        self,
        params: dict,
        context: ToolInvokeContext,
    ) -> StructuredToolResult:
        try:
            result = self._lc_tool.run(params)
            if not result or result.strip() == "":
                return StructuredToolResult(
                    status=StructuredToolResultStatus.NO_DATA,
                    data="",
                    params=params,
                    invocation=self.get_parameterized_one_liner(params),
                )
            return StructuredToolResult(
                status=StructuredToolResultStatus.SUCCESS,
                data=str(result),
                params=params,
                invocation=self.get_parameterized_one_liner(params),
            )
        except Exception as e:
            return StructuredToolResult(
                status=StructuredToolResultStatus.ERROR,
                error=f"LangChain tool '{self._lc_tool.name}' failed: {str(e)}",
                params=params,
                invocation=self.get_parameterized_one_liner(params),
            )

    def get_parameterized_one_liner(self, params: Dict) -> str:
        return f"langchain:{self._lc_tool.name}({params})"
```

### LangChainToolset: Holmes Toolset으로 등록

```python
# 의사 코드 - LangChainToolset
# 실제 구현 위치: holmes/plugins/toolsets/langchain/langchain_toolset.py

from holmes.core.tools import (
    CallablePrerequisite,
    Toolset,
    ToolsetType,
)

class LangChainToolset(Toolset):
    """LangChain 커뮤니티 도구를 Holmes 도구셋으로 래핑합니다.

    MCP 어댑터(RemoteMCPToolset)와 동일한 패턴을 따릅니다.
    - prerequisites_callable()에서 LangChain 도구 인스턴스를 생성하고 health check
    - 생성된 도구를 LangChainToolAdapter로 래핑하여 self.tools에 등록
    """

    def model_post_init(self, __context):
        self.type = ToolsetType.CUSTOMIZED
        self.prerequisites = [
            CallablePrerequisite(callable=self.prerequisites_callable)
        ]

    def prerequisites_callable(self, config) -> tuple[bool, str]:
        try:
            # 1. LangChain 설치 여부 확인
            try:
                from langchain_core.tools import BaseTool
            except ImportError:
                return (False, "langchain-core가 설치되지 않았습니다.")

            # 2. config에서 도구 설정 로드
            tools_config = config.get("tools", [])
            if not tools_config:
                return (False, "langchain_tools.tools 설정이 비어 있습니다.")

            # 3. 각 LangChain 도구 인스턴스 생성 및 래핑
            self.tools = []
            for tool_config in tools_config:
                lc_tool = self._create_lc_tool(tool_config)
                adapter = LangChainToolAdapter.create(lc_tool)
                self.tools.append(adapter)

            return (True, "")
        except Exception as e:
            return (False, f"LangChain 도구 로드 실패: {str(e)}")

    def _create_lc_tool(self, tool_config: dict) -> "BaseTool":
        """config.yaml 설정으로부터 LangChain 도구 인스턴스를 생성합니다."""
        import importlib

        module = importlib.import_module(tool_config["package"])
        tool_class = getattr(module, tool_config["class"])
        init_kwargs = tool_config.get("config", {})
        return tool_class(**init_kwargs)
```

### HolmesToLangChainAdapter: Holmes Tool → LangChain BaseTool (양방향 호환)

Holmes 도구를 LangChain 에이전트나 LangGraph 워크플로우에서 사용해야 하는 경우를 위한 역방향 어댑터입니다.

```python
# 의사 코드 - HolmesToLangChainAdapter
# 실제 구현 위치: holmes/plugins/toolsets/langchain/holmes_to_langchain.py

class HolmesToLangChainAdapter:
    """Holmes Tool을 LangChain BaseTool로 변환합니다."""

    @staticmethod
    def adapt(holmes_tool: Tool, llm: "LLM") -> "BaseTool":
        from langchain_core.tools import BaseTool as LCBaseTool
        from pydantic import BaseModel, Field

        # Holmes ToolParameter → Pydantic 모델 (LangChain args_schema)
        fields = {}
        annotations = {}
        for param_name, param in holmes_tool.parameters.items():
            annotations[param_name] = str
            fields[param_name] = Field(description=param.description or "")

        ArgsSchema = type(
            f"{holmes_tool.name}_args",
            (BaseModel,),
            {"__annotations__": annotations, **fields},
        )

        _holmes_tool = holmes_tool
        _llm = llm

        class WrappedTool(LCBaseTool):
            name: str = _holmes_tool.name
            description: str = _holmes_tool.description
            args_schema: type = ArgsSchema

            def _run(self, **kwargs) -> str:
                context = ToolInvokeContext(
                    llm=_llm,
                    max_token_count=_llm.get_max_token_count_for_single_tool(),
                    tool_call_id="langchain_call",
                    tool_name=_holmes_tool.name,
                )
                result = _holmes_tool.invoke(kwargs, context)
                return result.get_stringified_data()

        return WrappedTool()
```

---

## 4. 도입 대상 LangChain 커뮤니티 도구

### SQL Database 도구

사내 운영 DB(MySQL, PostgreSQL)를 직접 조회하여 애플리케이션 상태를 확인합니다.

**사용 시나리오**: "주문 처리 지연 알림 발생 시, orders 테이블에서 pending 상태 건수와 평균 처리 시간을 조회"

```yaml
# config.yaml
langchain_tools:
  enabled: true
  tools:
    - name: "sql_database"
      package: "langchain_community.utilities"
      class: "SQLDatabase"
      config:
        database_uri: "{{ env.HOLMES_SQL_DATABASE_URI }}"
```

### Web/URL 도구

외부 API 문서, 릴리스 노트, 장애 공지 페이지를 조회합니다.

**사용 시나리오**: "외부 서비스 연동 오류 발생 시, 해당 서비스의 상태 페이지를 확인"

```yaml
    - name: "web_search"
      package: "langchain_community.tools"
      class: "WebSearchTool"
      config:
        allowed_domains:
          - "status.aws.amazon.com"
          - "status.cloud.google.com"
```

### Document Loaders (Confluence, Notion)

사내 문서 시스템에서 운영 매뉴얼, 아키텍처 문서, 장애 대응 가이드를 조회합니다.

**사용 시나리오**: "장애 조사 시, Confluence에서 관련 서비스의 아키텍처 문서와 이전 장애 보고서를 참조"

```yaml
    - name: "confluence_loader"
      package: "langchain_community.document_loaders"
      class: "ConfluenceLoader"
      config:
        url: "{{ env.CONFLUENCE_URL }}"
        username: "{{ env.CONFLUENCE_USERNAME }}"
        api_key: "{{ env.CONFLUENCE_API_KEY }}"
        space_key: "OPS"
```

### Vector Store 도구

로그, 이벤트, 과거 장애 보고서를 시맨틱 검색으로 조회합니다.

**사용 시나리오**: "현재 증상과 유사한 과거 장애 사례를 벡터 검색으로 찾아 대응 방법을 참조"

```yaml
    - name: "vector_search"
      package: "langchain_community.vectorstores"
      class: "OpenSearchVectorSearch"
      config:
        opensearch_url: "{{ env.OPENSEARCH_URL }}"
        index_name: "incident-reports"
```

### File System 도구

로컬 또는 마운트된 파일 시스템에서 설정 파일, 로그 파일을 탐색합니다.

**사용 시나리오**: "애플리케이션 설정 파일의 내용을 확인하여 잘못된 설정을 진단"

```yaml
    - name: "filesystem"
      package: "langchain_community.tools.file_management"
      class: "ReadFileTool"
      config:
        root_dir: "/etc/holmes/shared-configs"
```

---

## 5. config.yaml 통합

### langchain_tools 섹션 설계

```yaml
# config.yaml - LangChain 커뮤니티 도구 설정
langchain_tools:
  enabled: true                    # 전체 활성화/비활성화
  description: "LangChain 커뮤니티 도구를 통한 추가 데이터 소스"
  icon_url: "https://cdn.simpleicons.org/langchain/1C3C3C"

  tools:
    # SQL Database 조회
    - name: "sql_database"
      package: "langchain_community.utilities"
      class: "SQLDatabase"
      enabled: true                # 개별 도구 활성화/비활성화
      config:
        database_uri: "{{ env.HOLMES_SQL_DATABASE_URI }}"

    # Confluence 문서 조회
    - name: "confluence_search"
      package: "langchain_community.document_loaders"
      class: "ConfluenceLoader"
      enabled: true
      config:
        url: "{{ env.CONFLUENCE_URL }}"
        username: "{{ env.CONFLUENCE_USERNAME }}"
        api_key: "{{ env.CONFLUENCE_API_KEY }}"
        space_key: "OPS"

    # 파일 시스템 탐색
    - name: "file_reader"
      package: "langchain_community.tools.file_management"
      class: "ReadFileTool"
      enabled: false               # 비활성화
      config:
        root_dir: "/etc/holmes/shared-configs"
```

### 설정 로딩 흐름

```mermaid
flowchart TD
    A[config.yaml 로드] --> B{langchain_tools\n섹션 존재?}
    B -- 아니오 --> C[기존 도구셋만 사용]
    B -- 예 --> D{enabled: true?}
    D -- 아니오 --> C
    D -- 예 --> E{langchain-core\n설치 여부?}
    E -- 아니오 --> F[경고 로그 출력\n기존 도구셋만 사용]
    E -- 예 --> G[LangChainToolset 생성]
    G --> H[개별 도구 enabled 확인]
    H --> I[LangChainToolAdapter로 래핑]
    I --> J[기존 도구셋 목록에 병합]
    J --> K[ToolExecutor 생성]

    style G fill:#e8f5e9
    style I fill:#e8f5e9
```

### Config 클래스 변경

`Config` 클래스에 `langchain_tools` 필드를 추가합니다. 기존 `toolsets`와 동일한 방식으로 `dict`로 관리합니다.

```python
# 의사 코드 - Config 변경 (최소한의 추가)
# 위치: holmes/config.py

class Config(RobustaBaseConfig):
    # ... 기존 필드 유지 ...
    langchain_tools: Optional[dict[str, Any]] = None  # 새로 추가
```

### ToolsetManager 변경

`ToolsetManager._list_all_toolsets()`에서 `langchain_tools` 설정이 있으면 `LangChainToolset`을 생성하여 기존 도구셋 목록에 추가합니다.

```python
# 의사 코드 - ToolsetManager 변경 (최소한의 추가)
# 위치: holmes/core/toolset_manager.py

class ToolsetManager:
    def __init__(self, ..., langchain_tools=None):
        # ... 기존 초기화 유지 ...
        self.langchain_tools = langchain_tools

    def _list_all_toolsets(self, ...):
        # ... 기존 로직 유지 ...

        # LangChain 도구셋 추가 (기존 코드 뒤에 삽입)
        if self.langchain_tools and self.langchain_tools.get("enabled"):
            langchain_toolset = self._load_langchain_toolset()
            if langchain_toolset:
                toolsets_by_name[langchain_toolset.name] = langchain_toolset

        # ... 기존 후속 로직 유지 ...
```

---

## 6. 선택적 의존성 전략

### pyproject.toml extras 그룹

LangChain 관련 패키지를 선택적 의존성(extras)으로 분리하여, 필요한 도구만 설치할 수 있도록 합니다.

```toml
# pyproject.toml
[tool.poetry.extras]
# 개별 도구별 선택적 의존성
langchain-core = ["langchain-core"]                        # 어댑터 계층만
langchain-sql = ["langchain-core", "langchain-community"]  # SQL Database 도구
langchain-web = ["langchain-core", "langchain-community"]  # Web/URL 도구
langchain-docs = ["langchain-core", "langchain-community"] # Document Loader
langchain-all = [                                          # 전체 LangChain 도구
    "langchain-core",
    "langchain-community",
    "langchain-openai",
]
```

설치 예시:

```bash
# SQL Database 도구만 필요한 경우
pip install holmesgpt[langchain-sql]

# 전체 LangChain 도구
pip install holmesgpt[langchain-all]

# 기존 설치 (LangChain 없이)
pip install holmesgpt
```

### 지연 로딩(lazy import) 패턴

LangChain 관련 import는 실제 사용 시점에 수행하여, 미설치 환경에서 에러가 발생하지 않도록 합니다.

```python
# 의사 코드 - 지연 로딩 패턴
# 위치: holmes/plugins/toolsets/langchain/__init__.py

import logging

logger = logging.getLogger(__name__)

LANGCHAIN_AVAILABLE = False
try:
    import langchain_core  # noqa: F401
    LANGCHAIN_AVAILABLE = True
except ImportError:
    pass


def create_langchain_toolset(config: dict) -> "LangChainToolset | None":
    """LangChain 도구셋을 생성합니다. LangChain 미설치 시 None을 반환합니다."""
    if not LANGCHAIN_AVAILABLE:
        logger.info(
            "langchain-core가 설치되지 않았습니다. "
            "LangChain 도구를 사용하려면: pip install holmesgpt[langchain-core]"
        )
        return None

    from holmes.plugins.toolsets.langchain.langchain_toolset import LangChainToolset

    return LangChainToolset(
        name="langchain/tools",
        description=config.get("description", "LangChain 커뮤니티 도구"),
        enabled=True,
        config=config,
        tools=[],
    )
```

### 의존성 충돌 방지

LangChain은 Pydantic v2를 사용하며, HolmesGPT도 Pydantic v2를 사용하므로 기본적으로 호환됩니다. 추가 주의사항은 다음과 같습니다.

- **langchain-core 버전 고정**: `langchain-core>=0.2,<1.0` 범위로 지정하여 메이저 버전 변경을 방지합니다.
- **langchain-community 버전 매칭**: `langchain-core`와 동일한 마이너 버전을 사용합니다.
- **개별 도구 패키지**: 특정 도구에 추가 패키지가 필요한 경우(예: `pymysql`), 해당 extras 그룹에 포함합니다.

---

## 7. 보안 고려사항

### 읽기 전용 원칙 유지

HolmesGPT의 모든 도구는 읽기 전용(read-only)으로 설계되어 있습니다. LangChain 도구도 이 원칙을 따릅니다.

| 도구 | 허용 | 차단 |
|------|------|------|
| SQL Database | `SELECT` 쿼리만 허용 | `INSERT`, `UPDATE`, `DELETE`, `DROP` 차단 |
| File System | 읽기(Read)만 허용 | 쓰기, 삭제, 실행 차단 |
| Web/URL | GET 요청만 허용 | POST, PUT, DELETE 차단 |
| Document Loader | 문서 조회만 허용 | 문서 수정, 삭제 차단 |

SQL Database 도구의 경우 `SQLDatabase` 생성 시 읽기 전용 모드를 강제합니다.

```python
# 의사 코드 - SQL 도구 읽기 전용 강제
from langchain_community.utilities import SQLDatabase

db = SQLDatabase.from_uri(
    database_uri,
    # 허용 테이블 화이트리스트
    include_tables=["orders", "users", "deployments"],
    # 읽기 전용 쿼리만 허용
    custom_table_info=None,
)
# SQLDatabaseToolkit에서 쿼리 검증 래퍼 추가
```

### 화이트리스트 기반 접근 제어

- **테이블 화이트리스트**: SQL 도구가 접근할 수 있는 테이블을 명시적으로 제한합니다.
- **도메인 화이트리스트**: Web 도구가 접근할 수 있는 도메인을 제한합니다.
- **경로 화이트리스트**: File System 도구가 접근할 수 있는 디렉토리를 제한합니다.
- **공간 화이트리스트**: Confluence 도구가 접근할 수 있는 Space를 제한합니다.

### 민감 정보 환경변수 관리

모든 인증 정보는 `{{ env.VAR_NAME }}` 형식으로 환경변수에서 참조합니다. config.yaml에 직접 기록하지 않습니다.

```yaml
# 올바른 예시
config:
  database_uri: "{{ env.HOLMES_SQL_DATABASE_URI }}"
  api_key: "{{ env.CONFLUENCE_API_KEY }}"

# 잘못된 예시 - 절대 사용하지 않음
config:
  database_uri: "postgresql://user:password@host:5432/db"
  api_key: "sk-abc123..."
```

---

## 8. 구현 로드맵

### Phase 1: 어댑터 계층 + SQL Database 도구 (3-4주)

- `LangChainToolAdapter` 구현 (LangChain BaseTool → Holmes Tool 변환)
- `LangChainToolset` 구현 (Holmes Toolset으로 등록)
- `Config`에 `langchain_tools` 필드 추가
- `ToolsetManager`에 LangChain 도구셋 로딩 로직 추가
- SQL Database 도구 통합 및 읽기 전용 쿼리 검증
- `pyproject.toml` extras 그룹 설정
- 단위 테스트 및 통합 테스트

### Phase 2: Web/Document 도구 + Vector Store (3-4주)

- Web/URL 도구 통합 (도메인 화이트리스트)
- Confluence Document Loader 통합
- Vector Store 시맨틱 검색 도구 통합
- LLM 평가 테스트 (LangChain 도구 활용 시나리오)
- `HolmesToLangChainAdapter` 구현 (역방향 호환)

### Phase 3: File System 도구 + 안정화 (2-3주)

- File System 도구 통합 (경로 화이트리스트)
- 전체 도구 보안 감사
- 성능 최적화 (도구 인스턴스 캐싱, 연결 풀링)
- 문서화 및 사용 가이드 작성

### Gantt 차트

```mermaid
gantt
    title LangChain 도구 통합 로드맵
    dateFormat  YYYY-MM-DD
    axisFormat  %m월

    section Phase 1 - 어댑터 + SQL
    LangChainToolAdapter 구현        :p1_1, 2025-09-01, 1w
    LangChainToolset 구현            :p1_2, after p1_1, 1w
    Config/ToolsetManager 연동       :p1_3, after p1_1, 1w
    SQL Database 도구 통합            :p1_4, after p1_2, 1w
    선택적 의존성 설정                :p1_5, 2025-09-01, 3d
    Phase 1 테스트                   :p1_6, after p1_4, 1w

    section Phase 2 - Web/Doc/Vector
    Web/URL 도구 통합                :p2_1, after p1_6, 1w
    Confluence Loader 통합           :p2_2, after p1_6, 1w
    Vector Store 도구 통합            :p2_3, after p2_1, 1w
    HolmesToLangChainAdapter         :p2_4, after p2_1, 1w
    LLM 평가 테스트                  :p2_5, after p2_3, 1w

    section Phase 3 - File System + 안정화
    File System 도구 통합             :p3_1, after p2_5, 1w
    보안 감사                        :p3_2, after p3_1, 3d
    성능 최적화                      :p3_3, after p3_1, 1w
    문서화                           :p3_4, after p3_2, 3d
```

---

## 9. 14번 vs 15번 접근법 비교

[14-deep-agent-architecture.md](14-deep-agent-architecture.md)는 멀티 에이전트 전환 + LangChain + 런북 고도화를 포함하는 대규모 개선안입니다. 본 문서(15번)는 기존 단일 에이전트 아키텍처를 유지하면서 LangChain 커뮤니티 도구만 선택적으로 도입하는 경량 통합 방안입니다.

### 비교 테이블

| 항목 | 14번 (Deep Agent) | 15번 (LangChain-only) |
|------|-------------------|----------------------|
| **아키텍처 변경 범위** | 대규모 (Supervisor/Specialist 도입) | 최소 (어댑터 계층만 추가) |
| **구현 기간** | 24-30주 (3 Phase) | 8-11주 (3 Phase) |
| **위험도** | 높음 (에이전트 루프 변경) | 낮음 (기존 루프 유지) |
| **LLM 비용 영향** | 증가 (멀티 에이전트 다중 호출) | 변동 없음 (단일 에이전트 유지) |
| **도구 생태계 활용** | LangChain + LangGraph 전체 | LangChain 커뮤니티 도구만 |
| **에이전트 오케스트레이션** | LangGraph StateGraph 지원 | 미지원 (기존 루프 유지) |
| **도메인 전문화** | Specialist별 도메인 프롬프트 | 미지원 (단일 프롬프트) |
| **런북 개선** | 구조화된 YAML 런북, RunbookExecutor | 미포함 |
| **컨텍스트 윈도우 효율** | Specialist별 도구 분리로 개선 | 도구 수 증가로 소폭 악화 가능 |
| **디버깅 복잡도** | 높음 (에이전트 간 상태 추적) | 낮음 (기존과 동일) |
| **롤백 용이성** | 복잡 (구조 변경 되돌리기) | 용이 (어댑터 제거만) |
| **팀 학습 비용** | 높음 (LangGraph, 멀티 에이전트 패턴) | 낮음 (기존 패턴 확장) |

### 14번 (Deep Agent) 장점 / 단점

**장점**

- **도메인 전문화**: 각 Specialist가 도메인 특화 프롬프트와 도구만 사용하여 정확도가 향상될 수 있습니다.
- **컨텍스트 윈도우 효율**: Specialist별로 필요한 도구만 전달하므로 토큰 사용이 최적화됩니다.
- **확장 가능한 아키텍처**: 새로운 도메인 추가 시 Specialist를 등록하기만 하면 됩니다.
- **런북 고도화**: 구조화된 YAML 런북과 실행 추적으로 운영 품질이 향상됩니다.
- **LangGraph 활용**: 선언적 에이전트 오케스트레이션으로 복잡한 워크플로우를 표현할 수 있습니다.

**단점**

- **높은 구현 비용**: 24-30주의 개발 기간과 아키텍처 전환 위험이 있습니다.
- **LLM 비용 증가**: Supervisor + Specialist 다중 호출로 API 비용이 증가합니다.
- **디버깅 복잡도**: 에이전트 간 상태 전파 추적이 어려워질 수 있습니다.
- **기존 호환성 위험**: 에이전트 루프 변경으로 기존 동작이 영향받을 수 있습니다.
- **LangChain 의존성**: LangGraph에 대한 구조적 의존이 생기므로, LangChain 생태계 변화에 영향을 받습니다.

### 15번 (LangChain-only) 장점 / 단점

**장점**

- **낮은 위험**: 기존 에이전트 루프와 도구 시스템을 변경하지 않으므로 프로덕션 안정성이 유지됩니다.
- **빠른 도입**: 8-11주로 도입 가능하며, Phase 1(4주)만으로도 실질적인 가치를 얻을 수 있습니다.
- **쉬운 롤백**: 문제 발생 시 어댑터 계층만 제거하면 원상 복구됩니다.
- **낮은 학습 비용**: 기존 Holmes 패턴(MCP 어댑터)을 따르므로 팀 적응이 빠릅니다.
- **LLM 비용 유지**: 단일 에이전트 구조를 유지하므로 추가 비용이 없습니다.

**단점**

- **도메인 전문화 부재**: 단일 LLM이 모든 도구를 관리하므로, 도구 수 증가 시 선택 정확도가 저하될 수 있습니다.
- **컨텍스트 윈도우 비효율**: LangChain 도구 추가로 전체 도구 스키마가 증가합니다.
- **런북 개선 미포함**: 기존 마크다운 런북 방식을 그대로 사용합니다.
- **오케스트레이션 한계**: 복잡한 멀티 스텝 워크플로우를 선언적으로 정의할 수 없습니다.
- **확장성 한계**: 도구 수가 크게 증가하면 단일 에이전트 구조의 한계에 도달할 수 있습니다.

### 권장 시나리오

| 상황 | 권장 접근법 |
|------|-----------|
| LangChain 도구 생태계를 빠르게 활용하고 싶은 경우 | **15번** (경량 통합) |
| 도구 수가 50개 이하이고 현재 구조에 만족하는 경우 | **15번** (경량 통합) |
| 도메인 전문화가 필요하고 도구 수가 50개를 초과하는 경우 | **14번** (Deep Agent) |
| 런북 실행 추적과 A/B 테스트가 필요한 경우 | **14번** (Deep Agent) |
| 충분한 개발 리소스와 시간이 있는 경우 | **14번** (Deep Agent) |
| 점진적으로 시작하고 싶은 경우 | **15번 → 14번** (점진적 전환) |

### 점진적 전환 전략: 15번 먼저 → 14번으로 확장

가장 안전한 접근법은 15번을 먼저 도입한 후, 필요에 따라 14번으로 확장하는 것입니다.

```mermaid
flowchart LR
    A[현재 상태\n단일 에이전트\n내장 도구셋만] --> B[15번 도입\n단일 에이전트\n+ LangChain 도구]
    B --> C{도구 수 50개 초과\n또는 도메인 전문화 필요?}
    C -- 예 --> D[14번 확장\n멀티 에이전트\n+ 런북 고도화]
    C -- 아니오 --> E[15번 유지\n필요한 도구만 추가]

    style A fill:#fff3e0
    style B fill:#e8f5e9
    style D fill:#e1f5fe
    style E fill:#e8f5e9
```

**전환 시 15번의 자산이 재사용되는 부분**:

- `LangChainToolAdapter`: 멀티 에이전트에서도 LangChain 도구를 래핑하는 데 그대로 사용됩니다.
- `LangChainToolset`: Specialist에게 할당하는 도구셋으로 그대로 사용됩니다.
- `HolmesToLangChainAdapter`: LangGraph 기반 오케스트레이션에서 Holmes 도구를 사용하는 데 활용됩니다.
- `config.yaml` 설정: `langchain_tools` 섹션이 그대로 유지됩니다.
- 선택적 의존성 구조: `pyproject.toml` extras 그룹이 확장됩니다.

즉, 15번의 구현물은 14번으로 전환 시 폐기되지 않고 기반 구성요소로 활용됩니다.
