# app/__main__.py
"""CLI 冒烟测试：python -m app "问题" 返回生成 SQL 并执行结果。"""
import sys

from app.llm import chat


def main():
    if len(sys.argv) < 2:
        print("用法: python -m app '你的问题'")
        return
    print(chat([{"role": "user", "content": sys.argv[1]}], temperature=0.2))


if __name__ == "__main__":
    main()
