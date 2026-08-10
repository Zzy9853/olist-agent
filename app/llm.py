# app/llm.py
"""LLM 客户端：阿里云百炼 OpenAI 兼容接口。"""
import json

from openai import OpenAI

from app.config import BASE_URL, CHAT_MODEL, EMBED_MODEL, load_api_key

_client = None

def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=BASE_URL, api_key=load_api_key(), timeout=60)
    return _client

def chat(messages: list[dict], temperature: float = 0.2) -> str:
    """对话补全，返回文本。"""
    resp = get_client().chat.completions.create(
        model=CHAT_MODEL, messages=messages, temperature=temperature)
    return resp.choices[0].message.content or ""

def chat_json(messages: list[dict], temperature: float = 0.0) -> dict:
    """对话补全，要求 JSON 对象输出，返回解析后的 dict。
    容错：剥离 Markdown 围栏与首尾非 JSON 文本，解析失败抛 ValueError。
    """
    resp = get_client().chat.completions.create(
        model=CHAT_MODEL, messages=messages, temperature=temperature,
        response_format={"type": "json_object"})
    text = (resp.choices[0].message.content or "").strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM 返回非 JSON: {text[:200]}") from e

def embed_texts(texts: list[str]) -> list[list[float]]:
    """批量文本嵌入（RAG 用，Task 8 起使用）。"""
    resp = get_client().embeddings.create(model=EMBED_MODEL, input=texts)
    return [item.embedding for item in resp.data]

def stream_chat(messages: list[dict], temperature: float = 0.2):
    """对话补全（流式）。逐 token yield；结束 chunk（choices 为空或 delta 为 None）自动跳过。"""
    resp = get_client().chat.completions.create(
        model=CHAT_MODEL, messages=messages, temperature=temperature, stream=True)
    for chunk in resp:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta
