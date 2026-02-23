"""
HDSP-Agent Interactive Chat Widget for JupyterLab

Usage (single cell):
    from chat_client import hdsp_agent_chat
    hdsp_agent_chat("http://hdsp-agent-holmes.agents.svc.cluster.local:5050")
"""

import base64
import html as html_module
import io
import json
import re
import http.client
import urllib.parse
from datetime import datetime

import ipywidgets as widgets
from IPython.display import display, HTML
from markdown_it import MarkdownIt

_md = MarkdownIt().enable("table")

_CHAT_CSS = """
<style>
.hdsp-agent-msg pre { background:#f5f5f5; padding:8px; border-radius:4px; overflow-x:auto; }
.hdsp-agent-msg code { background:#f0f0f0; padding:1px 4px; border-radius:3px; font-size:0.9em; }
.hdsp-agent-msg pre code { background:none; padding:0; }
.hdsp-agent-msg table { border-collapse:collapse; margin:8px 0; }
.hdsp-agent-msg th, .hdsp-agent-msg td { border:1px solid #ddd; padding:4px 8px; }
.hdsp-agent-msg blockquote { border-left:3px solid #ddd; margin:8px 0; padding:4px 12px; color:#666; }
.hdsp-agent-msg img { max-width:100%; height:auto; margin:8px 0; border:1px solid #eee; border-radius:4px; }
.hdsp-agent-progress { margin-left:16px; font-size:0.85em; line-height:1.6; }
.hdsp-agent-progress .tool-pending { color:#999; font-style:italic; }
.hdsp-agent-progress .tool-ok { color:#4CAF50; }
.hdsp-agent-progress .tool-err { color:red; }
.hdsp-agent-progress .tool-nodata { color:#FF9800; }
</style>
"""

_EMBED_TAG_RE = re.compile(r"<<\s*(\{.*?\})\s*>>", re.DOTALL)

# Sentinel used to mark where the progress section lives in the chat log
_PROGRESS_MARKER = "<!--HDSP_AGENT_PROGRESS-->"


def _post_json(endpoint: str, payload: dict, timeout: int = 600):
    parsed = urllib.parse.urlparse(endpoint)
    body = json.dumps(payload).encode("utf-8")
    conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=timeout)
    try:
        conn.request("POST", parsed.path, body=body, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        data = resp.read().decode("utf-8")
        return resp.status, json.loads(data)
    finally:
        conn.close()


def _post_stream(endpoint: str, payload: dict, timeout: int = 600):
    """Send a streaming POST request and yield (event_type, data_dict) tuples.

    The server returns SSE format:
        event: <type>
        data: <json>
        <blank line>
    """
    payload = {**payload, "stream": True}
    parsed = urllib.parse.urlparse(endpoint)
    body = json.dumps(payload).encode("utf-8")
    conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=timeout)
    try:
        conn.request("POST", parsed.path, body=body, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        if resp.status != 200:
            error_body = resp.read().decode("utf-8")
            try:
                error_data = json.loads(error_body)
            except (json.JSONDecodeError, TypeError):
                error_data = {"detail": error_body}
            yield ("_http_error", {"status": resp.status, "data": error_data})
            return

        current_event = None
        current_data_lines = []

        while True:
            raw_line = resp.readline()
            if not raw_line:
                break
            line = raw_line.decode("utf-8").rstrip("\r\n")

            if line.startswith("event: "):
                current_event = line[7:]
            elif line.startswith("data: "):
                current_data_lines.append(line[6:])
            elif line == "":
                if current_event and current_data_lines:
                    data_str = "\n".join(current_data_lines)
                    try:
                        data = json.loads(data_str)
                    except (json.JSONDecodeError, TypeError):
                        data = {"raw": data_str}
                    yield (current_event, data)
                current_event = None
                current_data_lines = []
    finally:
        conn.close()


def _metric_label(metric: dict) -> str:
    """Build a readable legend label from Prometheus metric labels."""
    filtered = {k: v for k, v in metric.items() if k != "__name__"}
    if not filtered:
        return metric.get("__name__", "value")
    if len(filtered) == 1:
        return next(iter(filtered.values()))
    return ", ".join(f"{k}={v}" for k, v in filtered.items())


def _render_prometheus_chart(prom_data: dict, description: str, query: str) -> str:
    """Render Prometheus data as a base64-encoded <img> tag using matplotlib.

    Supports:
      - resultType "matrix" -> line chart (multiple series)
      - resultType "vector" -> horizontal bar chart
    Returns an HTML string (<img> or fallback text).
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
    except ImportError:
        return f'<p style="color:#999">[Graph: {description} — matplotlib not installed]</p>'

    result_type = prom_data.get("resultType", "")
    results = prom_data.get("result", [])
    if not results:
        return f'<p style="color:#999">[Graph: {description} — no data]</p>'

    fig, ax = plt.subplots(figsize=(10, 4))

    if result_type == "matrix":
        for series in results:
            label = _metric_label(series.get("metric", {}))
            values = series.get("values", [])
            if not values:
                continue
            timestamps = [datetime.fromtimestamp(float(v[0])) for v in values]
            nums = [float(v[1]) for v in values]
            ax.plot(timestamps, nums, label=label, linewidth=1.5)

        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        fig.autofmt_xdate(rotation=30)

    elif result_type == "vector":
        labels = []
        values = []
        for entry in results:
            labels.append(_metric_label(entry.get("metric", {})))
            values.append(float(entry.get("value", [0, 0])[1]))
        y_pos = range(len(labels))
        ax.barh(y_pos, values)
        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels, fontsize=8)

    else:
        plt.close(fig)
        return f'<p style="color:#999">[Graph: {description} — unsupported resultType: {result_type}]</p>'

    ax.set_title(description, fontsize=11, pad=8)
    ax.grid(True, alpha=0.3)
    if result_type == "matrix" and len(results) > 1:
        ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.15), ncol=2)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("ascii")
    return (
        f'<div style="margin:8px 0">'
        f'<img src="data:image/png;base64,{b64}" alt="{description}">'
        f'<p style="color:#999;font-size:0.8em;margin:2px 0">query: <code>{query}</code></p>'
        f'</div>'
    )


def _find_tool_call(tool_calls: list, tool_call_id: str) -> dict:
    """Find a tool_call entry by its tool_call_id."""
    for tc in tool_calls:
        tc_id = tc.get("tool_call_id", "") if isinstance(tc, dict) else ""
        if tc_id == tool_call_id:
            return tc
    return {}


def _extract_prom_data(tool_call: dict) -> tuple:
    """Extract (prom_data_dict, description, query) from a tool_call result.

    The result.data field is a serialized MetricsBasedResponse which contains:
      - data: the raw Prometheus JSON (resultType + result)
      - description, query
    """
    result = tool_call.get("result", {})
    data_field = result.get("data", "")

    # data_field can be a JSON string (serialized MetricsBasedResponse) or a dict
    if isinstance(data_field, str):
        try:
            data_field = json.loads(data_field)
        except (json.JSONDecodeError, TypeError):
            return None, "", ""

    if not isinstance(data_field, dict):
        return None, "", ""

    description = data_field.get("description", result.get("description", ""))
    query = data_field.get("query", "")

    # The actual Prometheus data is in data_field["data"]
    prom_data = data_field.get("data", {})
    if isinstance(prom_data, str):
        try:
            prom_data = json.loads(prom_data)
        except (json.JSONDecodeError, TypeError):
            return None, description, query

    return prom_data, description, query


def _process_embed_tags(analysis: str, tool_calls: list) -> str:
    """Replace << {"type": "promql", ...} >> embed tags with rendered chart images."""
    def replace_tag(match):
        try:
            tag = json.loads(match.group(1))
        except (json.JSONDecodeError, TypeError):
            return match.group(0)

        tag_type = tag.get("type", "")
        if tag_type != "promql":
            return match.group(0)

        tool_call_id = tag.get("tool_call_id", "")
        if not tool_call_id:
            return '<p style="color:#999">[Graph: missing tool_call_id]</p>'

        tc = _find_tool_call(tool_calls, tool_call_id)
        if not tc:
            return '<p style="color:#999">[Graph: data not found]</p>'

        prom_data, description, query = _extract_prom_data(tc)
        if not prom_data or not prom_data.get("result"):
            return f'<p style="color:#999">[Graph: {description or "no data"}]</p>'

        return _render_prometheus_chart(prom_data, description, query)

    return _EMBED_TAG_RE.sub(replace_tag, analysis)


def _render_tool_table(tool_calls: list) -> str:
    """Render the collapsible tool calls summary table."""
    if not tool_calls:
        return ""
    tc_rows = ""
    for tc in tool_calls:
        if not isinstance(tc, dict):
            continue
        name = html_module.escape(tc.get("tool_name", tc.get("name", "unknown")))
        desc = html_module.escape(tc.get("description", ""))
        result = tc.get("result", {})
        tc_status = result.get("status", "") if isinstance(result, dict) else ""
        status_color = {"success": "#4CAF50", "error": "red", "no_data": "#FF9800"}.get(tc_status, "#999")
        tc_rows += (
            f'<tr>'
            f'<td style="font-family:monospace;font-size:0.85em">{name}</td>'
            f'<td>{desc}</td>'
            f'<td style="color:{status_color};font-weight:bold">{tc_status}</td>'
            f'</tr>'
        )
    return (
        f'<details style="margin:4px 0">'
        f'<summary style="color:#999;cursor:pointer">[{len(tool_calls)} tool calls]</summary>'
        f'<table style="width:100%;font-size:0.85em;margin:4px 0">'
        f'<tr style="background:#f5f5f5"><th>Tool</th><th>Description</th><th>Status</th></tr>'
        f'{tc_rows}</table></details>'
    )


def _render_progress(tool_statuses: list) -> str:
    """Build HTML for the streaming progress section.

    tool_statuses: list of (tool_name, status) where status is
        "pending" | "success" | "error" | "no_data"
    """
    if not tool_statuses:
        return (
            f'{_PROGRESS_MARKER}'
            '<p><b>HDSP-Agent &gt;</b> <i style="color:#999">processing...</i></p>'
            f'{_PROGRESS_MARKER}'
        )

    lines = []
    for name, status in tool_statuses:
        escaped = html_module.escape(name)
        if status == "pending":
            lines.append(f'<div class="tool-pending">&#9203; {escaped}...</div>')
        elif status == "success":
            lines.append(f'<div class="tool-ok">&#10003; {escaped}</div>')
        elif status == "error":
            lines.append(f'<div class="tool-err">&#10007; {escaped}</div>')
        elif status == "no_data":
            lines.append(f'<div class="tool-nodata">&#10003; {escaped} (no data)</div>')
        else:
            lines.append(f'<div class="tool-ok">&#10003; {escaped}</div>')

    progress_body = "\n".join(lines)
    return (
        f'{_PROGRESS_MARKER}'
        f'<p><b>HDSP-Agent &gt;</b> <i style="color:#999">processing...</i></p>'
        f'<div class="hdsp-agent-progress">{progress_body}</div>'
        f'{_PROGRESS_MARKER}'
    )


def _strip_progress(chat_log: str) -> str:
    """Remove the progress section from the chat log."""
    parts = chat_log.split(_PROGRESS_MARKER)
    if len(parts) >= 3:
        return parts[0] + "".join(parts[2:])
    return chat_log


def hdsp_agent_chat(url: str, timeout: int = 600, system_prompt: str = "", stream: bool = True):
    endpoint = f"{url.rstrip('/')}/api/chat"
    state = {"conversation_history": None, "chat_log": ""}

    input_box = widgets.Text(
        placeholder="질문을 입력하세요...",
        layout=widgets.Layout(width="85%"),
    )
    send_btn = widgets.Button(
        description="Send",
        button_style="primary",
        layout=widgets.Layout(width="15%"),
    )
    clear_btn = widgets.Button(
        description="Clear Context",
        button_style="warning",
        layout=widgets.Layout(width="120px"),
    )

    # Layout properties on widgets.HTML are unreliable (inner .widget-html-content
    # ignores height/overflow).  Instead, put the scrollable div *inside* the HTML
    # content itself so the browser honours it directly.
    _SCROLL_OPEN = (
        '<div class="hdsp-agent-msg" style="height:590px;overflow-y:auto;'
        'border:1px solid #ddd;padding:10px">'
    )
    _SCROLL_CLOSE = "</div>"

    chat_html = widgets.HTML(
        value=_CHAT_CSS + _SCROLL_OPEN
        + '<span style="color:#999;font-style:italic">Ready.</span>'
        + _SCROLL_CLOSE,
    )

    # Invisible broken image whose onerror scrolls the container to the bottom.
    # JupyterLab strips <script> tags from HTML widgets, but onerror fires reliably.
    _SCROLL_TRIGGER = (
        '<img src="x" onerror="var c=this.closest(\'.hdsp-agent-msg\');'
        'if(c)c.scrollTop=c.scrollHeight;this.remove();" '
        'style="display:none">'
    )

    def _set_html(html_str: str):
        state["chat_log"] = html_str
        chat_html.value = (
            _CHAT_CSS + _SCROLL_OPEN + html_str
            + _SCROLL_TRIGGER + _SCROLL_CLOSE
        )

    def _append(html_str: str):
        _set_html(state["chat_log"] + html_str)

    def _update_progress(tool_statuses: list):
        """Replace the progress section in the chat log with updated status."""
        base = _strip_progress(state["chat_log"])
        _set_html(base + _render_progress(tool_statuses))

    def _render_final(analysis: str, tool_calls: list):
        """Render the final answer with tool table, markdown, and graphs."""
        analysis = _process_embed_tags(analysis, tool_calls)
        parts = _render_tool_table(tool_calls)
        try:
            rendered = _md.render(analysis)
        except Exception:
            rendered = f"<pre>{analysis}</pre>"
        parts += f"<div><b>HDSP-Agent &gt;</b>{rendered}</div><hr>"
        return parts

    def send_streaming(question: str):
        """Send question via SSE streaming with real-time progress."""
        payload = {"ask": question}
        if system_prompt:
            payload["additional_system_prompt"] = system_prompt
        if state["conversation_history"]:
            payload["conversation_history"] = state["conversation_history"]

        _append(f'<p><b style="color:#2196F3">You &gt;</b> {html_module.escape(question)}</p>')

        # tool_statuses: [(name, status)] for progress display
        # tool_calls: full tool result dicts for final rendering
        tool_statuses = []
        tool_calls = []
        # Map tool_call_id -> index in tool_statuses for updating
        id_to_idx = {}

        _update_progress(tool_statuses)

        try:
            for event_type, data in _post_stream(endpoint, payload, timeout):
                if event_type == "_http_error":
                    base = _strip_progress(state["chat_log"])
                    _set_html(base)
                    status_code = data.get("status", "?")
                    err_data = data.get("data", {})
                    detail = err_data.get("detail", err_data) if isinstance(err_data, dict) else err_data
                    _append(f'<p><b style="color:red">[ERROR {status_code}]</b> {detail}</p>')
                    return

                elif event_type == "start_tool_calling":
                    tool_name = data.get("tool_name", "unknown")
                    tool_id = data.get("id", "")
                    idx = len(tool_statuses)
                    tool_statuses.append((tool_name, "pending"))
                    if tool_id:
                        id_to_idx[tool_id] = idx
                    _update_progress(tool_statuses)

                elif event_type == "tool_calling_result":
                    tool_call_id = data.get("tool_call_id", "")
                    tool_name = data.get("name", "unknown")
                    result = data.get("result", {})
                    tc_status = result.get("status", "success") if isinstance(result, dict) else "success"

                    # Update progress status
                    idx = id_to_idx.get(tool_call_id)
                    if idx is not None and idx < len(tool_statuses):
                        tool_statuses[idx] = (tool_name, tc_status)
                    else:
                        tool_statuses.append((tool_name, tc_status))

                    # Accumulate for final rendering
                    tool_calls.append({
                        "tool_call_id": tool_call_id,
                        "tool_name": tool_name,
                        "description": data.get("description", ""),
                        "result": result,
                    })
                    _update_progress(tool_statuses)

                elif event_type == "ai_message":
                    # Intermediate LLM message between tool calls — ignored
                    # (shown only in final analysis)
                    pass

                elif event_type == "ai_answer_end":
                    base = _strip_progress(state["chat_log"])
                    _set_html(base)

                    state["conversation_history"] = data.get("conversation_history")
                    analysis = data.get("analysis", "")
                    # The ai_answer_end SSE event does NOT include tool_calls.
                    # Tool results are sent individually via tool_calling_result
                    # events which include full result.data (stringified).
                    _append(_render_final(analysis, tool_calls))
                    return

                elif event_type == "error":
                    base = _strip_progress(state["chat_log"])
                    _set_html(base)
                    desc = data.get("description", data.get("msg", "Unknown error"))
                    _append(f'<p><b style="color:red">[ERROR]</b> {desc}</p>')
                    return

                # token_count, conversation_history_compacted — silently ignored

            # Stream ended without ai_answer_end (unexpected)
            if tool_calls or tool_statuses:
                base = _strip_progress(state["chat_log"])
                _set_html(base)
                _append('<p><b style="color:#FF9800">[WARN]</b> Stream ended unexpectedly.</p>')

        except Exception:
            # SSE failed — raise to caller for fallback
            raise

    def send_sync(question: str):
        """Send question via synchronous POST (non-streaming fallback)."""
        payload = {"ask": question}
        if system_prompt:
            payload["additional_system_prompt"] = system_prompt
        if state["conversation_history"]:
            payload["conversation_history"] = state["conversation_history"]

        _append(f'<p><b style="color:#2196F3">You &gt;</b> {html_module.escape(question)}</p>')
        thinking = '<p class="hdsp-agent-thinking"><i style="color:#999">thinking...</i></p>'
        _append(thinking)

        try:
            resp_status, data = _post_json(endpoint, payload, timeout)
        except Exception as e:
            _set_html(state["chat_log"].replace(thinking, ""))
            _append(f'<p><b style="color:red">[ERROR]</b> {e}</p>')
            return

        _set_html(state["chat_log"].replace(thinking, ""))

        if resp_status != 200:
            detail = data.get("detail", data) if isinstance(data, dict) else data
            _append(f'<p><b style="color:red">[ERROR {resp_status}]</b> {detail}</p>')
            return

        state["conversation_history"] = data.get("conversation_history")
        analysis = data.get("analysis", "")
        tool_calls = data.get("tool_calls", [])
        _append(_render_final(analysis, tool_calls))

    def send(question: str):
        if not question.strip():
            return

        if not stream:
            send_sync(question)
            return

        # Save chat_log before streaming attempt so we can restore on failure
        saved_log = state["chat_log"]

        try:
            send_streaming(question)
        except Exception:
            # Streaming failed — restore chat log and fall back to sync
            _set_html(saved_log)
            send_sync(question)

    def on_send(_):
        question = input_box.value
        input_box.value = ""
        send(question)

    def on_clear(_):
        state["conversation_history"] = None
        _set_html('<div style="color:#4CAF50;font-style:italic">Context cleared.</div>')

    send_btn.on_click(on_send)
    clear_btn.on_click(on_clear)
    input_box.on_submit(lambda _: on_send(None))

    header = widgets.HTML("<h3 style='margin:0;padding:5px 0'>HDSP-Agent Chat</h3>")
    input_row = widgets.HBox([input_box, send_btn], layout=widgets.Layout(width="100%"))
    toolbar = widgets.HBox([clear_btn], layout=widgets.Layout(width="100%"))

    container = widgets.VBox(
        [header, chat_html, input_row, toolbar],
        layout=widgets.Layout(
            width="100%",
            border="1px solid #ccc",
            padding="6px",
        ),
    )

    display(container)
