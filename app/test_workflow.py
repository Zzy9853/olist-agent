# app/test_workflow.py
"""诊断工作流自检：流失 / 履约四步报告结构 + 真实数据。"""
from app.workflow import run_churn_diagnosis, run_funnel_diagnosis


def run():
    result = run_churn_diagnosis()
    names = [s["name"] for s in result["steps"]]
    print("步骤:", names)
    for s in result["steps"]:
        print(f"  {s['name']}: {s['detail'][:80]}")
    assert names == ["概览", "对比", "归因", "建议"], f"步骤缺失: {names}"
    assert result["summary"], "缺少 summary"
    print("流失诊断工作流自检通过")


def run_funnel():
    result = run_funnel_diagnosis()
    names = [s["name"] for s in result["steps"]]
    print("步骤:", names)
    for s in result["steps"]:
        print(f"  {s['name']}: {s['detail'][:80]}")
    assert names == ["概览", "对比", "归因", "建议"], f"步骤缺失: {names}"
    assert "承运→签收" in result["steps"][2]["detail"], "归因应指出瓶颈环节"
    assert result["summary"], "缺少 summary"
    print("履约诊断工作流自检通过")


if __name__ == "__main__":
    run()
    run_funnel()
