"""Tests for VisualizerAgent code extraction edge cases."""

from __future__ import annotations

from pathlib import Path

import pytest

from paperbanana.agents.visualizer import VisualizerAgent


class _DummyImageGen:
    async def generate(self, *args, **kwargs):
        return None


class _DummyVLM:
    def __init__(self, responses=None):
        self._responses = list(responses or [""])
        self._idx = 0

    async def generate(self, *args, **kwargs):
        idx = min(self._idx, len(self._responses) - 1)
        self._idx += 1
        return self._responses[idx]


def _make_agent(tmp_path):
    prompt_file = Path(tmp_path) / "plot" / "visualizer.txt"
    prompt_file.parent.mkdir(parents=True, exist_ok=True)
    prompt_file.write_text("{description}", encoding="utf-8")
    return VisualizerAgent(
        image_gen=_DummyImageGen(),
        vlm_provider=_DummyVLM(),
        prompt_dir=str(tmp_path),
        output_dir=str(tmp_path),
    )


def test_extract_code_handles_truncated_python_block(tmp_path):
    agent = _make_agent(tmp_path)
    response = "```python\nimport matplotlib.pyplot as plt\nplt.figure()\n"
    code = agent._extract_code(response)
    assert code == "import matplotlib.pyplot as plt\nplt.figure()"


def test_extract_code_handles_truncated_generic_block(tmp_path):
    agent = _make_agent(tmp_path)
    response = "```\nprint('hello')\n"
    code = agent._extract_code(response)
    assert code == "print('hello')"


def test_extract_code_handles_complete_python_block(tmp_path):
    agent = _make_agent(tmp_path)
    response = "```python\nprint('ok')\n```\nextra"
    code = agent._extract_code(response)
    assert code == "print('ok')"


def test_extract_code_handles_plain_code_response(tmp_path):
    agent = _make_agent(tmp_path)
    response = "import matplotlib.pyplot as plt\nplt.figure()"
    code = agent._extract_code(response)
    assert code == response


@pytest.mark.asyncio
async def test_generate_plot_retries_then_succeeds(tmp_path):
    prompt_file = Path(tmp_path) / "plot" / "visualizer.txt"
    prompt_file.parent.mkdir(parents=True, exist_ok=True)
    prompt_file.write_text("{description}", encoding="utf-8")

    vlm = _DummyVLM(
        responses=[
            "```python\nprint('first')\n```",
            "```python\nprint('fixed')\n```",
        ]
    )
    agent = VisualizerAgent(
        image_gen=_DummyImageGen(),
        vlm_provider=vlm,
        prompt_dir=str(tmp_path),
        output_dir=str(tmp_path),
    )

    calls = {"count": 0}

    def _fake_execute(code: str, output_path: str):
        calls["count"] += 1
        if calls["count"] == 1:
            return False, "SyntaxError: bad code"
        Path(output_path).write_bytes(b"ok")
        return True, None

    agent._execute_plot_code = _fake_execute  # type: ignore[method-assign]
    output_path = str(Path(tmp_path) / "plot.png")

    result = await agent._generate_plot(
        description="desc",
        raw_data={"x": [1]},
        output_path=output_path,
        iteration=1,
    )

    assert result == output_path
    assert calls["count"] == 2
    assert Path(output_path).exists()


@pytest.mark.asyncio
async def test_generate_plot_raises_after_max_attempts(tmp_path):
    prompt_file = Path(tmp_path) / "plot" / "visualizer.txt"
    prompt_file.parent.mkdir(parents=True, exist_ok=True)
    prompt_file.write_text("{description}", encoding="utf-8")

    vlm = _DummyVLM(
        responses=[
            "```python\nprint('first')\n```",
            "```python\nprint('second')\n```",
            "```python\nprint('third')\n```",
        ]
    )
    agent = VisualizerAgent(
        image_gen=_DummyImageGen(),
        vlm_provider=vlm,
        prompt_dir=str(tmp_path),
        output_dir=str(tmp_path),
    )

    def _always_fail(code: str, output_path: str):
        return False, "TypeError: still failing"

    agent._execute_plot_code = _always_fail  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="after 3 attempts"):
        await agent._generate_plot(
            description="desc",
            raw_data={"x": [1]},
            output_path=str(Path(tmp_path) / "plot.png"),
            iteration=1,
        )
