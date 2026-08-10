# app/test_ui_multisession.py
"""多会话 AppTest 验证：创建/切换/消息写入/懒创建/删除跳默认（monkeypatch ask_stream 避免真实 API）。

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
    assert at.session_state["current_id"] is None, "初始应为草稿态"

    # 发一条消息（chat_input 是 sidebar 之外的元素）；草稿态提问会创建会话
    at.chat_input[0].set_value("整体用户流失率是多少？").run()
    cid = at.session_state["current_id"]
    assert cid is not None, "草稿态提问应创建会话"
    msgs = at.session_state["conversations"][cid]["messages"]
    print("消息后消息数:", len(msgs))
    assert len(msgs) >= 2, "应写入 user+assistant 消息"
    n1 = len(at.session_state["conversations"])
    print("创建后会话总数:", n1)
    assert n1 == n0 + 1, "草稿态提问应创建会话"

    # 新对话（sidebar 第一个按钮"＋ 新对话"）：懒创建——只进草稿态，不建会话
    at.sidebar.button[0].click().run()
    convs = at.session_state["conversations"]
    print("新对话后总数:", len(convs))
    assert len(convs) == n1, "点击新对话不应新建会话（懒创建：草稿态）"
    assert at.session_state["current_id"] is None, "点击新对话后应处于草稿态"

    # 草稿态提问 → 创建新会话并写入 user+assistant
    at.chat_input[0].set_value("再来一个问题").run()
    new_key = at.session_state["current_id"]
    print("草稿态提问后 current_id:", new_key)
    assert new_key is not None, "草稿态提问应创建会话"
    assert len(at.session_state["conversations"][new_key]["messages"]) == 2, "新会话应写入 user+assistant"

    # 会话按钮两行 label：第一行 = 问题（title 的"问题 · 时间"拆分），label 含换行
    convs = at.session_state["conversations"]
    old_key = list(convs.keys())[0]
    n_msgs_old = len(at.session_state["conversations"][old_key]["messages"])
    old_title = at.session_state["conversations"][old_key]["title"]
    old_question = old_title.split(" · ", 1)[0]
    old_idx = next(i for i, b in enumerate(at.sidebar.button)
                   if old_question == b.label.split("\n")[0].removeprefix("● "))
    print("旧会话按钮 label:", repr(at.sidebar.button[old_idx].label))
    assert "\n" in at.sidebar.button[old_idx].label, "会话按钮应为两行（问题\n时间）"

    # 删除当前会话 → current_id=None（欢迎页）+ 会话数减少
    n_before_del = len(at.session_state["conversations"])
    del_idx = next(i for i, b in enumerate(at.sidebar.button) if "删除当前会话" in b.label)
    at.sidebar.button[del_idx].click().run()
    n_after_del = len(at.session_state["conversations"])
    print("删除后会话总数:", n_after_del)
    assert n_after_del == n_before_del - 1, "删除当前会话后总数应减少 1"
    assert at.session_state["current_id"] is None, "删除当前会话后应回到草稿态（欢迎页）"
    assert any("试试这些问题" in m.value for m in at.markdown), "删除后应显示欢迎页"

    # 切回旧会话（按标题前缀定位 button，两行 label 已适配），验证消息保留
    old_idx = next(i for i, b in enumerate(at.sidebar.button)
                   if old_question == b.label.split("\n")[0].removeprefix("● "))
    print("切回旧会话 button:", old_idx, repr(at.sidebar.button[old_idx].label))
    at.sidebar.button[old_idx].click().run()
    assert at.session_state["current_id"] == old_key
    assert len(at.session_state["conversations"][old_key]["messages"]) == n_msgs_old, "旧会话消息应保留"

    print("✅ 多会话 AppTest 通过")


if __name__ == "__main__":
    run()
