# app/test_conversations.py
"""会话存储层自检：加载/保存/创建/标题/删除（用临时目录，不污染真实数据）。"""
import json
import tempfile
from pathlib import Path

from app.conversations import (
    load_conversations, save_conversations, new_conversation,
    set_title, delete_conversation)


def run():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "convs.json"

        # 空文件 → 空 dict
        assert load_conversations(p) == {}, "空文件应返回空 dict"

        # 创建 + 标题 + 保存 + 加载
        convs = {}
        cid, conv = new_conversation(convs)
        set_title(conv, "整体用户流失率是多少？")
        assert conv["title"].startswith("整体用户流失率是多少"), conv["title"]
        save_conversations(convs, p)
        loaded = load_conversations(p)
        assert cid in loaded and loaded[cid]["title"] == conv["title"], "保存/加载不一致"

        # ts 字段：created_ts/last_ts 存在、创建时相等、数值类型
        assert "created_ts" in conv and "last_ts" in conv, "新会话应有 created_ts/last_ts"
        assert conv["created_ts"] == conv["last_ts"], "创建时 last_ts 应等于 created_ts"
        assert isinstance(conv["created_ts"], (int, float)), "ts 应为数值"

        # normalize：旧数据（无 ts）加载后补齐 now，created_at 字符串保留
        legacy = {"conv_old": {"title": "旧会话", "created_at": "08-01 10:00", "messages": []}}
        lp = Path(d) / "legacy.json"
        lp.write_text(json.dumps(legacy), encoding="utf-8")
        old = load_conversations(lp)["conv_old"]
        assert old["created_at"] == "08-01 10:00", "created_at 字符串应保留"
        assert old["created_ts"] == old["last_ts"], "旧会话补齐的 ts 应一致"
        assert isinstance(old["created_ts"], (int, float)), "补齐 ts 应为数值"

        # 消息写入
        conv["messages"].append({"role": "user", "content": "hi"})
        save_conversations(convs, p)
        assert len(load_conversations(p)[cid]["messages"]) == 1, "消息未持久化"

        # 标题截断（>12 字）
        cid2, conv2 = new_conversation(convs)
        set_title(conv2, "物流延迟率最高的五个品类分别是什么？")
        assert "…" in conv2["title"], "长标题未截断"
        assert len(conv2["title"].split("·")[0].strip()) <= 13, "截断后超长"

        # 删除
        delete_conversation(convs, cid)
        assert cid not in convs, "删除失败"
        delete_conversation(convs, "not_exist")  # 不存在不报错

    print("会话存储层自检通过")


if __name__ == "__main__":
    run()
