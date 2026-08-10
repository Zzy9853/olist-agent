# app/test_ui_multisession.py
"""多会话 AppTest 验证：创建/切换/消息写入（monkeypatch ask_stream 避免真实 API）。

运行：python app/test_ui_multisession.py（脚本含 sys.path shim，支持直接运行）
注：AppTest 会写真实 data/conversations.json，运行后删除该文件。
注意：AppTest 以独立 __main__ 模块 exec 脚本，脚本内 `from app.agent import ask_stream`
在 exec 时绑定——因此必须 patch app.agent.ask_stream（patch app.ui.xxx 不生效）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # 使 `python app/xxx.py` 可 import app 包

from streamlit.testing.v1 import AppTest

from app import agent as agent_mod


async def fake_ask_stream(q, messages=None):
    yield {"type": "stage", "label": "生成 SQL"}
    yield {"type": "token", "content": f"答：{q[:10]}"}
    yield {"type": "done", "answer": f"答：{q[:10]}", "sql": None,
           "attribution": None, "workflow_result": None}


def run():
    agent_mod.ask_stream = fake_ask_stream
    at = AppTest.from_file("app/ui.py", default_timeout=60)
    at.run()
    convs = at.session_state["conversations"]
    n0 = len(convs)
    print("初始会话数:", n0)
    assert n0 >= 1

    # 发一条消息（chat_input 是 sidebar 之外的元素）；草稿态提问会创建会话
    at.chat_input[0].set_value("整体用户流失率是多少？").run()
    cid = at.session_state["current_id"]
    msgs = at.session_state["conversations"][cid]["messages"]
    print("消息后消息数:", len(msgs))
    assert len(msgs) >= 2, "应写入 user+assistant 消息"
    n1 = len(at.session_state["conversations"])
    assert n1 == n0 + 1, "草稿态提问应创建会话"

    # 新会话（sidebar 第一个按钮"＋ 新会话"）：懒创建——只进草稿态，不建会话
    at.sidebar.button[0].click().run()
    convs = at.session_state["conversations"]
    print("新会话后总数:", len(convs))
    assert len(convs) == n1, "点击新会话不应新建会话（懒创建：草稿态）"
    assert at.session_state["current_id"] is None, "点击新会话后应处于草稿态"

    # 草稿态提问 → 创建新会话并写入 user+assistant
    at.chat_input[0].set_value("再来一个问题").run()
    new_key = at.session_state["current_id"]
    print("草稿态提问后 current_id:", new_key)
    assert new_key is not None, "草稿态提问应创建会话"
    assert len(at.session_state["conversations"][new_key]["messages"]) == 2, "新会话应写入 user+assistant"

    # 切回旧会话，验证消息持久化（消息数应与初始一致）
    old_key = list(convs.keys())[0]
    n_msgs_old = len(at.session_state["conversations"][old_key]["messages"])
    at.sidebar.radio[0].set_value(old_key).run()
    assert at.session_state["current_id"] == old_key
    assert len(at.session_state["conversations"][old_key]["messages"]) == n_msgs_old, "旧会话消息应保留"

    print("✅ 多会话 AppTest 通过")


if __name__ == "__main__":
    run()
