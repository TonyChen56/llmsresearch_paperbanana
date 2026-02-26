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
        "nav_label": "健康检查",
        "title": "健康检查",
        "description": "检查 API 服务是否正常运行。",
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
    "Health": "健康检查",
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
