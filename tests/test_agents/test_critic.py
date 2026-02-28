"""Tests for CriticAgent response parsing behavior."""

from __future__ import annotations

from paperbanana.agents.critic import CriticAgent


class _DummyVLM:
    async def generate(self, *args, **kwargs):
        return ""


def _make_agent(tmp_path):
    return CriticAgent(vlm_provider=_DummyVLM(), prompt_dir=str(tmp_path))


def test_parse_response_invalid_json_requests_revision(tmp_path):
    agent = _make_agent(tmp_path)
    result = agent._parse_response("not a valid json payload")
    assert result.needs_revision is True
    assert result.revised_description is None
    assert "valid JSON" in result.critic_suggestions[0]


def test_parse_response_handles_markdown_json_block(tmp_path):
    agent = _make_agent(tmp_path)
    response = """```json
{
  "critic_suggestions": ["Fix x-axis label"],
  "revised_description": "Use clearer x-axis labels."
}
```"""
    result = agent._parse_response(response)
    assert result.needs_revision is True
    assert result.critic_suggestions == ["Fix x-axis label"]
    assert result.revised_description == "Use clearer x-axis labels."
