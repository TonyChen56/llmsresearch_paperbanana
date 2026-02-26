# PaperBanana HTTP API

Base URL:
- 本地：`http://localhost:8000`
- 线上：`https://<your-domain>`

交互文档：
- `GET /docs`
- `GET /redoc`
- 静态文档：`GET /static/docs.html`

## 鉴权

除 `/`、`/health`、`/docs`、`/redoc`、`/openapi.json`、`/static/*` 外，均需：

```http
Authorization: Bearer <PAPERBANANA_API_TOKEN>
```

## 端点

1. `POST /api/v1/tasks/generate`
- 提交方法图生成任务（异步）

2. `POST /api/v1/tasks/plot`
- 提交统计图生成任务（异步）

3. `POST /api/v1/tasks/continue`
- 提交续跑任务（异步）

4. `POST /api/v1/tasks/evaluate`（multipart）
- 上传 `generated_image`、`reference_image` 执行评测（异步）

5. `GET /api/v1/tasks/{task_id}`
- 查询任务状态

6. `GET /api/v1/tasks/{task_id}/artifact`
- 下载结果文件（图片或 JSON）

## 通用流程

```text
POST /api/v1/tasks/*
  -> 返回 task_id
GET /api/v1/tasks/{task_id}
  -> 轮询直到 completed/failed
GET /api/v1/tasks/{task_id}/artifact
  -> 下载结果
```

