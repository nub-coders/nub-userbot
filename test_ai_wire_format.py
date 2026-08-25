"""Round-trip check for the Anthropic <-> OpenAI wire translation in ai_backend."""
import json

from ai_backend import _from_openai, _to_openai


def test_to_openai():
    body = _to_openai({
        "model": "m",
        "max_tokens": 10,
        "system": "sys",
        "tools": [{"name": "read_file", "description": "d",
                   "input_schema": {"type": "object"}}],
        "messages": [
            {"role": "user", "content": "hey"},
            {"role": "assistant", "content": [
                {"type": "text", "text": "looking"},
                {"type": "tool_use", "id": "t1", "name": "read_file",
                 "input": {"path": "x"}},
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": "file body"},
            ]},
        ],
    })

    assert body["messages"][0] == {"role": "system", "content": "sys"}
    assert body["messages"][1] == {"role": "user", "content": "hey"}

    assistant = body["messages"][2]
    assert assistant["content"] == "looking"
    call = assistant["tool_calls"][0]
    assert call["id"] == "t1" and call["type"] == "function"
    assert call["function"]["name"] == "read_file"
    assert json.loads(call["function"]["arguments"]) == {"path": "x"}

    assert body["messages"][3] == {"role": "tool", "tool_call_id": "t1",
                                  "content": "file body"}
    assert body["tools"][0]["function"]["parameters"] == {"type": "object"}


def test_to_openai_image_and_no_tools():
    body = _to_openai({
        "model": "m", "max_tokens": 10, "system": "sys", "tools": [],
        "messages": [{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64",
                                         "media_type": "image/png", "data": "AAA"}},
            {"type": "text", "text": "what is this"},
        ]}],
    })

    assert "tools" not in body
    parts = body["messages"][1]["content"]
    assert parts[0]["image_url"]["url"] == "data:image/png;base64,AAA"
    assert parts[1] == {"type": "text", "text": "what is this"}


def test_from_openai():
    text = _from_openai({"choices": [{"message": {"content": "hi"}}]})
    assert text == {"content": [{"type": "text", "text": "hi"}],
                    "stop_reason": "end_turn"}

    call = _from_openai({"choices": [{"message": {"content": None, "tool_calls": [
        {"id": "t1", "function": {"name": "list_dir", "arguments": '{"path": "."}'}},
    ]}}]})
    assert call["stop_reason"] == "tool_use"
    assert call["content"] == [{"type": "tool_use", "id": "t1",
                               "name": "list_dir", "input": {"path": "."}}]

    # Invalid argument JSON degrades to an empty input, not a crash.
    bad = _from_openai({"choices": [{"message": {"tool_calls": [
        {"id": "t2", "function": {"name": "list_dir", "arguments": "{oops"}},
    ]}}]})
    assert bad["content"][0]["input"] == {}

    # A refusal or empty gateway payload must not raise.
    assert _from_openai({}) == {"content": [], "stop_reason": "end_turn"}


def test_invalid_json_handling():
    from unittest.mock import patch, MagicMock
    import ai_backend
    from ai_backend import _post, AgentError

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = ""
    mock_resp.json.side_effect = json.JSONDecodeError("Expecting value", "", 0)

    with patch("requests.post", return_value=mock_resp):
        try:
            _post([{"role": "user", "content": "hi"}], [])
            assert False, "Should have raised AgentError"
        except AgentError as e:
            assert "invalid response" in str(e)


if __name__ == "__main__":
    test_to_openai()
    test_to_openai_image_and_no_tools()
    test_from_openai()
    test_invalid_json_handling()
    print("ok")
