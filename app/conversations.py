# app/conversations.py
"""会话持久化：conversations.json 的加载/保存/增删/标题生成。无 Streamlit 依赖，可单测。"""
import json
import time
from pathlib import Path

from app.config import ROOT

CONV_PATH = ROOT / "data" / "conversations.json"


def _now() -> str:
    return time.strftime("%m-%d %H:%M")


def load_conversations(path: Path | None = None) -> dict:
    """加载全部会话 {conv_id: {title, created_at, messages}}；文件缺失/损坏返回空 dict。
    normalize：缺 created_ts/last_ts 的旧会话补默认 now（兼容历史数据）。"""
    p = path or CONV_PATH
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        if not isinstance(data, dict):
            return {}
        now = time.time()
        for conv in data.values():
            if not isinstance(conv, dict):
                continue
            conv.setdefault("created_ts", now)
            conv.setdefault("last_ts", now)
        return data
    return {}


def save_conversations(convs: dict, path: Path | None = None) -> None:
    """整体写回（会话数少，全量写可接受）。"""
    p = path or CONV_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(convs, ensure_ascii=False, indent=2), encoding="utf-8")


def new_conversation(convs: dict) -> tuple[str, dict]:
    """创建新会话并加入 convs。返回 (conv_id, conv)。
    写入 created_ts/last_ts（数值时间戳，分组排序用）；created_at 字符串保留（展示用）。"""
    conv_id = f"conv_{int(time.time() * 1000)}"
    ts = time.time()
    conv = {"title": "新会话", "created_at": _now(), "created_ts": ts, "last_ts": ts, "messages": []}
    convs[conv_id] = conv
    return conv_id, conv


def set_title(conv: dict, first_user_msg: str) -> None:
    """会话标题 = 首条用户消息前 12 字 + 创建时间。"""
    text = first_user_msg.strip()
    title = text[:12] + ("…" if len(text) > 12 else "")
    conv["title"] = f"{title} · {conv.get('created_at', '')}"


def delete_conversation(convs: dict, conv_id: str) -> None:
    """删除会话（不存在则忽略）。"""
    convs.pop(conv_id, None)
