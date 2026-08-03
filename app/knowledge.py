# app/knowledge.py
"""知识库加载：schema.md + metrics.md → system prompt 上下文。"""
from pathlib import Path

from app.config import KNOWLEDGE_DIR

SYSTEM_HEADER = """你是 Olist 电商平台的数据分析 Agent。用户会用中文提问业务问题，你的任务：
1. 把问题转成准确、可执行的 DuckDB SQL（只允许 SELECT）
2. 执行结果给出简洁的业务解读（引用基线数字做对比）

铁律（违反任一即失败）：
- 只写 SELECT 语句；禁止 DDL/DML（CREATE/DROP/INSERT/UPDATE/DELETE/ALTER）
- 表名只能用白名单表
- 指标定义必须与下方"口径字典"完全一致，禁止自行发明
- 用户级分析必须用 customer_unique_id，绝不用 customer_id
- 订单金额聚合必须先在 order_id 级去重再汇总
- 订单量/订单趋势类统计默认使用 valid_orders 视图（已排除 canceled/unavailable 无效订单）
- 不要对数值做 ROUND，保留原始精度；比例/率类指标返回 0-1 小数（如 0.81），不要乘 100
- 时间字段直接用 TIMESTAMP 比较，不转字符串
"""


def load_knowledge() -> dict:
    """读取两份知识库文档，返回 {'schema': str, 'metrics': str}。"""
    schema = (KNOWLEDGE_DIR / "schema.md").read_text(encoding="utf-8")
    metrics = (KNOWLEDGE_DIR / "metrics.md").read_text(encoding="utf-8")
    return {"schema": schema, "metrics": metrics}


def build_system_prompt(knowledge: dict | None = None) -> str:
    """组装 system prompt：头部规则 + schema 字典 + 口径字典。"""
    k = knowledge or load_knowledge()
    return "\n\n".join([
        SYSTEM_HEADER,
        "## 数据字典（表结构）\n" + k["schema"],
        "## 口径字典（指标定义与 SQL 规则，最高优先级）\n" + k["metrics"],
    ])
