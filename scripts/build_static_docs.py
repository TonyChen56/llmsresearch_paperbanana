"""Generate api/static/docs.html from FastAPI OpenAPI schema."""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from api.app import app

_ENDPOINT_META: dict[tuple[str, str], dict[str, str]] = {
    ("get", "/health"): {
        "nav_label": "心跳检测",
        "title": "心跳检测",
        "description": "用于检测服务是否存活。",
    },
    ("post", "/api/v1/tasks/generate"): {
        "nav_label": "提交生成任务",
        "title": "提交生成任务",
        "description": "提交方法图生成任务，返回 task_id 后异步执行。",
    },
    ("post", "/api/v1/tasks/plot"): {
        "nav_label": "提交统计图任务",
        "title": "提交统计图任务",
        "description": "提交统计图生成任务，支持自定义 JSON 数据。",
    },
    ("post", "/api/v1/tasks/continue"): {
        "nav_label": "提交续跑任务",
        "title": "提交续跑任务",
        "description": "继续已有 run 的迭代优化，支持用户反馈。",
    },
    ("post", "/api/v1/tasks/evaluate"): {
        "nav_label": "提交评测任务",
        "title": "提交评测任务",
        "description": "上传生成图与参考图，异步返回结构化评测结果。",
    },
    ("get", "/api/v1/tasks/{task_id}"): {
        "nav_label": "查询任务状态",
        "title": "查询任务状态",
        "description": "轮询任务状态，直到状态变为完成或失败。",
    },
    ("get", "/api/v1/tasks/{task_id}/artifact"): {
        "nav_label": "下载任务结果",
        "title": "下载任务结果",
        "description": "下载任务最终产物（图片或 JSON）。",
    },
}

_ENDPOINT_ORDER: dict[tuple[str, str], int] = {
    ("get", "/health"): 10,
    ("post", "/api/v1/tasks/generate"): 20,
    ("post", "/api/v1/tasks/plot"): 30,
    ("post", "/api/v1/tasks/continue"): 40,
    ("post", "/api/v1/tasks/evaluate"): 50,
    ("get", "/api/v1/tasks/{task_id}"): 60,
    ("get", "/api/v1/tasks/{task_id}/artifact"): 70,
}

_RESPONSE_DESC_MAP = {
    "Successful Response": "请求成功",
    "Validation Error": "参数校验错误",
}

_TAG_MAP = {
    "Tasks": "任务接口",
    "Health": "心跳检测",
}

_FIELD_DESC_MAP = {
    "task_id": "任务 ID",
    "source_context": "源文本上下文",
    "communicative_intent": "图表标题 / 要传达内容",
    "intent": "图表意图",
    "raw_data": "统计图原始数据（JSON）",
    "run_id": "已有运行 ID",
    "continue_latest": "是否续跑最新 run",
    "additional_iterations": "追加迭代次数",
    "user_feedback": "用户反馈",
    "refinement_iterations": "精化迭代次数",
    "optimize_inputs": "是否启用输入优化",
    "aspect_ratio": "目标长宽比（1:1/2:3/3:2/3:4/4:3/4:5/5:4/9:16/16:9/21:9/auto）",
    "auto_refine": "是否自动迭代到满意",
    "max_iterations": "最大迭代次数",
    "output_format": "输出图片格式（png/jpeg/webp）",
    "providers": "按任务覆盖供应商与模型配置（当前部署仅支持 KIE）",
    "providers.vlm_provider": "覆盖 VLM 供应商（当前仅支持 kie）",
    "providers.vlm_model": "覆盖 VLM 模型（建议 gemini-3-pro）",
    "providers.image_provider": (
        "覆盖图像供应商（当前仅支持 kie_nano_banana / kie_nano_banana_pro / kie）"
    ),
    "providers.image_model": "覆盖图像模型（建议 google/nano-banana 或 nano-banana-pro）",
    "generated_image": "待评测生成图文件",
    "reference_image": "参考图文件",
    "caption": "图表标题",
    "vlm_provider": "评测时覆盖 VLM 供应商（当前仅支持 kie）",
    "vlm_model": "评测时覆盖 VLM 模型（建议 gemini-3-pro）",
}


def _plain_text(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"\s+", " ", value).strip()
    return text


def _localized_response_description(value: str) -> str:
    return _RESPONSE_DESC_MAP.get(value, value)


def _extract_request_example(operation: dict[str, Any]) -> str | None:
    request_body = operation.get("requestBody", {})
    content = request_body.get("content", {})
    for media_type in (
        "application/json",
        "multipart/form-data",
        "application/x-www-form-urlencoded",
    ):
        media = content.get(media_type)
        if not media:
            continue
        if "example" in media:
            return json.dumps(media["example"], ensure_ascii=False, indent=2)
        examples = media.get("examples", {})
        if isinstance(examples, dict) and examples:
            first = next(iter(examples.values()))
            value = first.get("value")
            if value is not None:
                return json.dumps(value, ensure_ascii=False, indent=2)
        schema = media.get("schema")
        if schema is not None:
            if isinstance(schema, dict) and "$ref" in schema:
                continue
            return json.dumps(schema, ensure_ascii=False, indent=2)
    return None


def _resolve_schema_ref(schema: dict[str, Any], components: dict[str, Any]) -> dict[str, Any]:
    """Resolve #/components/schemas/* references."""
    current = schema
    while isinstance(current, dict) and "$ref" in current:
        ref = str(current["$ref"])
        if not ref.startswith("#/components/schemas/"):
            break
        name = ref.split("/")[-1]
        target = components.get(name)
        if not isinstance(target, dict):
            break
        current = target
    return current


def _unwrap_anyof(schema: dict[str, Any], components: dict[str, Any]) -> dict[str, Any]:
    """Prefer the non-null branch from anyOf for docs rendering."""
    current = _resolve_schema_ref(schema, components)
    any_of = current.get("anyOf")
    if not isinstance(any_of, list):
        return current

    non_null = []
    nullable = False
    for item in any_of:
        if isinstance(item, dict) and item.get("type") == "null":
            nullable = True
        elif isinstance(item, dict):
            non_null.append(item)

    if len(non_null) == 1:
        chosen = _resolve_schema_ref(non_null[0], components)
        merged = dict(chosen)
        if nullable:
            merged["x-nullable"] = True
        return merged
    return current


def _schema_type(schema: dict[str, Any], components: dict[str, Any]) -> str:
    """Render a compact type label for schema."""
    current = _unwrap_anyof(schema, components)
    if current.get("contentMediaType") == "application/octet-stream":
        return "file"
    enum_vals = current.get("enum")
    if isinstance(enum_vals, list) and enum_vals:
        enum_joined = ", ".join(str(v) for v in enum_vals)
        return f"enum({enum_joined})"
    schema_type = current.get("type")
    if schema_type == "array":
        items = current.get("items")
        if isinstance(items, dict):
            return f"array[{_schema_type(items, components)}]"
        return "array"
    if schema_type:
        return str(schema_type)
    if current.get("properties"):
        return "object"
    return "any"


def _localize_field_desc(field_name: str, raw_desc: str) -> str:
    if field_name in _FIELD_DESC_MAP:
        return _FIELD_DESC_MAP[field_name]
    if "." in field_name:
        leaf = field_name.split(".")[-1]
        if leaf in _FIELD_DESC_MAP:
            return _FIELD_DESC_MAP[leaf]
    if raw_desc and raw_desc != "-":
        return raw_desc
    return "-"


def _extract_body_fields_from_schema(
    schema: dict[str, Any],
    components: dict[str, Any],
    prefix: str = "",
) -> list[dict[str, Any]]:
    """Extract request-body fields recursively from an object schema."""
    current = _unwrap_anyof(schema, components)
    props = current.get("properties")
    if not isinstance(props, dict) or not props:
        return []

    required_fields = set(current.get("required", []))
    rows: list[dict[str, Any]] = []
    for prop_name, prop_schema_raw in props.items():
        if not isinstance(prop_schema_raw, dict):
            continue
        field_name = f"{prefix}.{prop_name}" if prefix else prop_name
        prop_schema = _unwrap_anyof(prop_schema_raw, components)
        raw_desc = _plain_text(prop_schema.get("description")) or "-"
        desc = _localize_field_desc(field_name, raw_desc)
        rows.append(
            {
                "name": field_name,
                "in": "body",
                "type": _schema_type(prop_schema_raw, components),
                "required": prop_name in required_fields,
                "description": desc,
            }
        )
        rows.extend(
            _extract_body_fields_from_schema(
                schema=prop_schema_raw,
                components=components,
                prefix=field_name,
            )
        )
    return rows


def _extract_request_parameters(
    operation: dict[str, Any],
    components: dict[str, Any],
) -> list[dict[str, Any]]:
    """Extract path/query/body parameter docs for one endpoint."""
    rows: list[dict[str, Any]] = []

    for param in operation.get("parameters", []):
        if not isinstance(param, dict):
            continue
        name = str(param.get("name", "")).strip()
        if not name:
            continue
        if name.lower() == "authorization":
            continue
        location = str(param.get("in", "")).strip() or "query"
        schema = param.get("schema")
        schema_obj = schema if isinstance(schema, dict) else {"type": "string"}
        raw_desc = _plain_text(param.get("description")) or "-"
        rows.append(
            {
                "name": name,
                "in": location,
                "type": _schema_type(schema_obj, components),
                "required": bool(param.get("required", False)),
                "description": _localize_field_desc(name, raw_desc),
            }
        )

    request_body = operation.get("requestBody", {})
    content = request_body.get("content", {})
    for media_type in (
        "application/json",
        "multipart/form-data",
        "application/x-www-form-urlencoded",
    ):
        media = content.get(media_type)
        if not isinstance(media, dict):
            continue
        schema = media.get("schema")
        if not isinstance(schema, dict):
            continue
        rows.extend(_extract_body_fields_from_schema(schema=schema, components=components))
        break

    return rows


def _build_curl_example(
    method: str,
    path: str,
    operation: dict[str, Any],
    example: str | None,
) -> str:
    base = "https://api.paperbanana.me"
    auth = '-H "Authorization: Bearer <PAPERBANANA_API_TOKEN>"'
    requires_auth = path.startswith("/api/v1/")
    auth_clause = f" {auth}" if requires_auth else ""
    method_upper = method.upper()
    request_body = operation.get("requestBody", {})
    content = request_body.get("content", {})

    if method_upper in {"GET", "DELETE"}:
        return f'curl -X {method_upper} "{base}{path}"{auth_clause}'

    if "multipart/form-data" in content:
        return (
            f'curl -X {method_upper} "{base}{path}"{auth_clause} \\\n'
            '  -F "generated_image=@generated.png" \\\n'
            '  -F "reference_image=@reference.png" \\\n'
            '  -F "source_context=..." \\\n'
            '  -F "caption=..."'
        )

    body = example or "{}"
    return (
        f'curl -X {method_upper} "{base}{path}"{auth_clause} \\\n'
        '  -H "Content-Type: application/json" \\\n'
        f"  -d '{body}'"
    )


def _collect_endpoints(openapi_schema: dict[str, Any]) -> list[dict[str, Any]]:
    components = openapi_schema.get("components", {}).get("schemas", {})
    endpoints: list[dict[str, Any]] = []
    for path, methods in openapi_schema.get("paths", {}).items():
        for method, operation in methods.items():
            method_lower = method.lower()
            if method_lower not in {"get", "post", "put", "patch", "delete"}:
                continue
            endpoint_key = (method_lower, path)
            localized = _ENDPOINT_META.get(endpoint_key, {})
            anchor = (
                f"{method_lower}-"
                f"{path.strip('/').replace('/', '-').replace('{', '').replace('}', '')}"
            )
            request_example = _extract_request_example(operation)
            request_parameters = _extract_request_parameters(operation, components)
            responses = []
            for code, resp in operation.get("responses", {}).items():
                desc = _plain_text(resp.get("description")) or "-"
                responses.append(
                    {
                        "code": code,
                        "description": _localized_response_description(desc),
                    }
                )

            summary = _plain_text(operation.get("summary"))
            description = _plain_text(operation.get("description"))
            title = localized.get("title") or summary or f"{method_lower.upper()} {path}"
            nav_label = localized.get("nav_label") or title
            description = localized.get("description") or description
            endpoints.append(
                {
                    "anchor": anchor,
                    "path": path,
                    "method_upper": method_lower.upper(),
                    "method_class": method_lower,
                    "title": title,
                    "nav_label": nav_label,
                    "description": description,
                    "tags": [_TAG_MAP.get(tag, tag) for tag in operation.get("tags", [])],
                    "request_content_types": list(
                        operation.get("requestBody", {}).get("content", {}).keys()
                    ),
                    "request_example": request_example,
                    "request_parameters": request_parameters,
                    "responses": responses,
                    "curl_example": _build_curl_example(
                        method_lower,
                        path,
                        operation,
                        request_example,
                    ),
                    "requires_auth": path.startswith("/api/v1/"),
                    "order": _ENDPOINT_ORDER.get(endpoint_key, 999),
                }
            )
    endpoints.sort(key=lambda x: (x["order"], x["path"], x["method_upper"]))
    return endpoints


def build_static_docs() -> Path:
    root = Path(__file__).resolve().parent.parent
    template_path = root / "scripts" / "templates"
    output_path = root / "api" / "static" / "docs.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    env = Environment(
        loader=FileSystemLoader(str(template_path)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("static_docs_template.html.j2")

    schema = app.openapi()
    endpoints = _collect_endpoints(schema)
    rendered = template.render(
        title=schema.get("info", {}).get("title", "PaperBanana API"),
        version=schema.get("info", {}).get("version", "unknown"),
        summary=_plain_text(schema.get("info", {}).get("description")),
        generated_at=dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        endpoints=endpoints,
    )
    output_path.write_text(rendered, encoding="utf-8")
    return output_path


def main() -> None:
    path = build_static_docs()
    print(f"Generated static docs: {path}")


if __name__ == "__main__":
    main()
