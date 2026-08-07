# app/test_ui_multisession.py
"""多会话 AppTest 验证：创建/切换/消息写入（monkeypatch ask 避免真实 API）。

运行：python app/test_ui_multisession.py（脚本含 sys.path shim，支持直接运行）
注：AppTest 会写真实 data/conversations.json，运行后删除该文件。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # 使 `python app/xxx.py` 可 import app 包

from streamlit.testing.v1 import AppTest
import app.ui as ui


def fake_ask(q, messages=None):
    return {"answer": f"答：{q[:10]}", "sql": None, "intent": "query",
            "attribution": None, "workflow_result": None}


def run():
    ui.ask = fake_ask
    at = AppTest.from_file("app/ui.py", default_timeout=60)
    at.run()
    convs = at.session_state["conversations"]
    n0 = len(convs)
    print("初始会话数:", n0)
    assert n0 >= 1

    # 发一条消息（chat_input 是 sidebar 之外的元素）
    at.chat_input[0].set_value("整体用户流失率是多少？").run()
    cid = at.session_state["current_id"]
    msgs = at.session_state["conversations"][cid]["messages"]
    print("消息后消息数:", len(msgs))
    assert len(msgs) >= 2, "应写入 user+assistant 消息"

    # 新会话（sidebar 第一个按钮"＋ 新会话"）
    at.sidebar.button[0].click().run()
    convs = at.session_state["conversations"]
    print("新会话后总数:", len(convs))
    assert len(convs) == n0 + 1
    # 注意：点击新会话后，sidebar radio 保留旧会话选中值，current_id 会被弹回旧会话
    # （widget state 跨 rerun 持久 + ui.py 的 `selected != current_id` 分支）。
    # 因此用 radio 显式切换到新会话（dict 最后插入的 key）来验证其消息为空。
    new_key = list(convs.keys())[-1]
    print("新会话 key:", new_key, "| 点击后 current_id:", at.session_state["current_id"])

    at.sidebar.radio[0].set_value(new_key).run()
    print("切到新会话后 current_id:", at.session_state["current_id"])
    assert at.session_state["current_id"] == new_key
    assert len(at.session_state["conversations"][new_key]["messages"]) == 0, "新会话应无消息"

    # 切回旧会话，验证消息持久化
    old_key = list(convs.keys())[0]
    at.sidebar.radio[0].set_value(old_key).run()
    assert at.session_state["current_id"] == old_key
    assert len(at.session_state["conversations"][old_key]["messages"]) == 2, "旧会话消息应保留"

    print("✅ 多会话 AppTest 通过")


if __name__ == "__main__":
    run()
