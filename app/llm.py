# app/llm.py
"""LLM 客户端：阿里云百炼 OpenAI 兼容接口。"""
from openai import OpenAI

from app.config import BASE_URL, CHAT_MODEL, EMBED_MODEL, load_api_key

_client = None

def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=BASE_URL, api_key=load_api_key())
    return _client

def chat(messages: list[dict], temperature: float = 0.2) -> str:
    """对话补全，返回文本。"""
    resp = get_client().chat.completions.create(
        model=CHAT_MODEL, messages=messages, temperature=temperature)
    return resp.choices[0].message.content

def chat_json(messages: list[dict], temperature: float = 0.0) -> dict:
    """对话补全，要求 JSON 对象输出，返回解析后的 dict。"""
    resp = get_client().chat.completions.create(
        model=CHAT_MODEL, messages=messages, temperature=temperature,
        response_format={"type": "json_object"})
    text = resp.choices[0].message.content
    import json
    return json.loads(text)

def embed_texts(texts: list[str]) -> list[list[float]]:
    """批量文本嵌入（RAG 用，Task 8 起使用）。"""
    resp = get_client().embeddings.create(model=EMBED_MODEL, input=texts)
    return [item.embedding for item in resp.data]
