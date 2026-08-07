# app/test_workflow.py
"""流失诊断工作流自检：四步报告结构 + 真实数据。"""
from app.workflow import run_churn_diagnosis


def run():
    result = run_churn_diagnosis()
    names = [s["name"] for s in result["steps"]]
    print("步骤:", names)
    for s in result["steps"]:
        print(f"  {s['name']}: {s['detail'][:80]}")
    assert names == ["概览", "对比", "归因", "建议"], f"步骤缺失: {names}"
    assert result["summary"], "缺少 summary"
    print("工作流自检通过")


if __name__ == "__main__":
    run()
