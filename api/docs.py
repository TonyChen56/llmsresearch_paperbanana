"""OpenAPI docs metadata for PaperBanana HTTP API."""

from __future__ import annotations

tags_metadata = [
    {"name": "Health", "description": "服务健康检查与文档入口"},
    {"name": "Tasks", "description": "异步任务提交、查询与结果下载"},
]

description = """
PaperBanana HTTP API：将生成、续跑、评测能力统一封装为异步任务接口。

通用流程：
1. 提交任务（POST）
2. 轮询状态（GET /api/v1/tasks/{task_id}）
3. 下载结果（GET /api/v1/tasks/{task_id}/artifact）
"""

request_examples = {
    "generate": {
        "summary": "生成方法图",
        "value": {
            "source_context": "我们的方法分为检索、规划、迭代精化三个阶段。",
            "communicative_intent": "方法整体流程图",
            "refinement_iterations": 3,
            "optimize_inputs": True,
        },
    },
    "plot": {
        "summary": "生成统计图",
        "value": {
            "intent": "比较不同模型在三个基准上的准确率",
            "raw_data": {
                "models": ["A", "B", "C"],
                "mmlu": [85.2, 88.1, 90.3],
                "arc": [78.0, 80.5, 82.9],
            },
            "refinement_iterations": 2,
        },
    },
    "continue": {
        "summary": "续跑已有任务",
        "value": {
            "run_id": "run_20260226_120000_ab12cd",
            "additional_iterations": 2,
            "user_feedback": "把箭头更粗一些，阶段颜色区分更明显。",
        },
    },
}

