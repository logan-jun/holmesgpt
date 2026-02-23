import json
import logging
import httpx
import boto3
from fastapi import APIRouter, Request

router = APIRouter()

HOLMES_URL = "http://holmesgpt-holmes.agents.svc.cluster.local/api/investigate"
LAMBDA_FUNCTION_NAME = "your-lambda-function-name"

lambda_client = boto3.client("lambda")

INVESTIGATE_INSTRUCTION = (
    "한국어로 분석 결과를 작성해줘. "
    "섹션별로 간결하게 정리하고, 즉시 조치 가능한 항목을 우선 제시해줘. "
    "각 alert 별로 구분하여 분석해줘."
)


def build_investigate_request(body: dict) -> dict:
    """AlertManager webhook body 전체를 하나의 InvestigateRequest로 변환"""
    alerts = body.get("alerts", [])
    common_labels = body.get("commonLabels", {})
    alert_name = common_labels.get("alertname", "Multiple Alerts")

    # 모든 alert 정보를 description에 통합
    alert_descriptions = []
    for i, alert in enumerate(alerts, 1):
        labels = alert.get("labels", {})
        annotations = alert.get("annotations", {})
        desc = annotations.get("description", annotations.get("summary", ""))
        status = alert.get("status", "")
        starts_at = alert.get("startsAt", "")

        alert_descriptions.append(
            f"[Alert {i}] status={status}, startsAt={starts_at}\n"
            f"  labels: {json.dumps(labels, ensure_ascii=False)}\n"
            f"  description: {desc}"
        )

    description = (
        f"총 {len(alerts)}건의 alert가 발생했습니다.\n\n"
        + "\n\n".join(alert_descriptions)
        + f'\n\n"""\n{INVESTIGATE_INSTRUCTION}\n"""'
    )

    # subject: commonLabels 사용 (그룹 공통 정보)
    # context: 개별 alert 전체 포함
    return {
        "source": "prometheus",
        "title": f"{alert_name} ({len(alerts)}건)",
        "description": description,
        "subject": common_labels,
        "context": {
            "status": body.get("status", ""),
            "groupLabels": body.get("groupLabels", {}),
            "commonLabels": common_labels,
            "commonAnnotations": body.get("commonAnnotations", {}),
            "alerts": alerts,
        },
        "include_tool_calls": False,
        "prompt_template": "/etc/holmes/prompts/custom_investigation.jinja2",
    }


async def call_investigate(payload: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(HOLMES_URL, json=payload)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logging.error(f"HolmesGPT investigate failed: {e}")
        return {"analysis": f"조사 실패: {str(e)}", "sections": {}, "tool_calls": []}


@router.post("/alert")
async def alert(request: Request):
    body = await request.json()

    # 하나의 investigate 요청으로 모든 alert 통합 조사
    investigate_req = build_investigate_request(body)
    investigation = await call_investigate(investigate_req)

    lambda_payload = {
        "alert": body,
        "investigation": {
            "analysis": investigation.get("analysis", ""),
            "sections": investigation.get("sections", {}),
        },
    }

    lambda_client.invoke(
        FunctionName=LAMBDA_FUNCTION_NAME,
        InvocationType="Event",
        Payload=bytes(json.dumps(lambda_payload, ensure_ascii=False), encoding="utf-8"),
    )
