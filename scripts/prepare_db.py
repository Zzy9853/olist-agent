"""M1: 构建 Olist 问数 Agent 的 DuckDB 数据库。

从电商项目 CSV 加载 9 张原始表 + 用户宽表到 olist.db，
显式定义列类型，保证 Agent 生成的 SQL 拿到确定性的 schema。

数据路径从 .env 的 OLIST_DATA_DIR 读取（不硬编码，保证仓库可移植）。
"""
import os
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent


def _load_env() -> dict:
    env = {}
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


_ENV = _load_env()
OLIST_DATA_DIR = _ENV.get("OLIST_DATA_DIR") or os.environ.get("OLIST_DATA_DIR")
if not OLIST_DATA_DIR:
    raise RuntimeError(
        "缺少数据目录配置：请在项目 .env 中设置 OLIST_DATA_DIR（Olist 原始 CSV 目录），"
        "例如 OLIST_DATA_DIR=C:/path/to/olist_data；宽表与 AB 表默认从 {OLIST_DATA_DIR}/../olist_analysis/data/ 读取。")

OLIST_DATA = OLIST_DATA_DIR
WIDE_CSV = os.path.join(os.path.dirname(OLIST_DATA), "olist_analysis", "data", "olist_user_wide_table.csv")
AB_CSV = os.path.join(os.path.dirname(OLIST_DATA), "olist_analysis", "data", "ab_test_results.csv")
DB_PATH = ROOT / "data" / "olist.db"

def csv(name):
    return os.path.join(OLIST_DATA, name).replace("\\", "/")

TABLES = [
    # (表名, CSV 文件名, 列定义 SQL)
    ("orders", "olist_orders_dataset.csv", """
        order_id VARCHAR, customer_id VARCHAR, order_status VARCHAR,
        order_purchase_timestamp TIMESTAMP, order_approved_at TIMESTAMP,
        order_delivered_carrier_date TIMESTAMP, order_delivered_customer_date TIMESTAMP,
        order_estimated_delivery_date TIMESTAMP"""),
    ("customers", "olist_customers_dataset.csv", """
        customer_id VARCHAR, customer_unique_id VARCHAR, customer_zip_code_prefix VARCHAR,
        customer_city VARCHAR, customer_state VARCHAR"""),
    ("order_items", "olist_order_items_dataset.csv", """
        order_id VARCHAR, order_item_id INTEGER, product_id VARCHAR, seller_id VARCHAR,
        shipping_limit_date TIMESTAMP, price DOUBLE, freight_value DOUBLE"""),
    ("order_payments", "olist_order_payments_dataset.csv", """
        order_id VARCHAR, payment_sequential INTEGER, payment_type VARCHAR,
        payment_installments INTEGER, payment_value DOUBLE"""),
    ("order_reviews", "olist_order_reviews_dataset.csv", """
        review_id VARCHAR, order_id VARCHAR, review_score INTEGER,
        review_comment_title VARCHAR, review_comment_message VARCHAR,
        review_creation_date TIMESTAMP, review_answer_timestamp TIMESTAMP"""),
    ("products", "olist_products_dataset.csv", """
        product_id VARCHAR, product_category_name VARCHAR,
        product_name_lenght INTEGER, product_description_lenght INTEGER,
        product_photos_qty INTEGER, product_weight_g INTEGER,
        product_length_cm INTEGER, product_height_cm INTEGER, product_width_cm INTEGER"""),
    ("sellers", "olist_sellers_dataset.csv", """
        seller_id VARCHAR, seller_zip_code_prefix VARCHAR, seller_city VARCHAR,
        seller_state VARCHAR"""),
    # 注意：源 CSV 首列带 UTF-8 BOM，这里显式改名
    ("product_category_translation", "product_category_name_translation.csv", """
        product_category_name VARCHAR, product_category_name_english VARCHAR"""),
    ("geolocation", "olist_geolocation_dataset.csv", """
        geolocation_zip_code_prefix VARCHAR, geolocation_lat DOUBLE, geolocation_lng DOUBLE,
        geolocation_city VARCHAR, geolocation_state VARCHAR"""),
]

def main():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    con = duckdb.connect(DB_PATH)

    for table, fname, cols in TABLES:
        if table == "product_category_translation":
            # 源 CSV 首列带 UTF-8 BOM，用 names 参数绕开列名问题
            con.execute(f"""
                CREATE TABLE {table} AS
                SELECT * FROM read_csv_auto('{csv(fname)}',
                    header=false, skip=1,
                    names=['product_category_name', 'product_category_name_english'])
            """)
            continue
        cast_cols = ", ".join(
            f"CAST({name} AS {typ}) AS {name}"
            for part in cols.split(",")
            for name, typ in [part.strip().split(maxsplit=1)]
        )
        con.execute(f"""
            CREATE TABLE {table} AS
            SELECT {cast_cols} FROM read_csv_auto('{csv(fname)}')
        """)

    # 用户宽表（含 XGBoost 预测概率 churn_prob，预测类问题直接查它）
    # 去重：源宽表含 122 个"同用户多地址"行（customer_unique_id 重复，
    # 行为特征相同、地址列不同，评测发现于 2026-08-03）——每用户保留首行
    con.execute(f"""
        CREATE TABLE user_wide AS
        SELECT * EXCLUDE (rn) FROM (
            SELECT *, ROW_NUMBER() OVER (PARTITION BY customer_unique_id ORDER BY 1) AS rn
            FROM read_csv_auto('{WIDE_CSV.replace(chr(92), '/')}')
        ) WHERE rn = 1
    """)

    # AB 实验敏感性分析结果（R$15/25/50 券 × 6 档留存提升率）
    con.execute(f"""
        CREATE TABLE ab_test_results AS
        SELECT * FROM read_csv_auto('{AB_CSV.replace(chr(92), '/')}')
    """)

    # 常用视图：口径统一的"有效订单"
    con.execute("""
        CREATE VIEW valid_orders AS
        SELECT * FROM orders
        WHERE order_status NOT IN ('canceled', 'unavailable')
    """)

    # 验证
    print("=== 表清单 ===")
    for row in con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='main' ORDER BY table_name").fetchall():
        name = row[0]
        n = con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        print(f"  {name}: {n:,} rows")

    print("\n=== 类型抽查（orders / user_wide）===")
    for t in ("orders", "user_wide"):
        print(f"  -- {t} --")
        for row in con.execute(f"DESCRIBE {t}").fetchall():
            print(f"    {row[0]}: {row[1]}")

    print("\n=== 只读模式验证 ===")
    con.close()
    ro = duckdb.connect(DB_PATH, read_only=True)
    print("  max order date:", ro.execute("SELECT MAX(order_purchase_timestamp) FROM orders").fetchone()[0])
    print("  流失率:", ro.execute("SELECT ROUND(AVG(is_churned),4) FROM user_wide").fetchone()[0])
    ro.close()
    print(f"\n✅ olist.db 构建完成: {DB_PATH} ({os.path.getsize(DB_PATH)/1024/1024:.1f} MB)")

if __name__ == "__main__":
    main()
