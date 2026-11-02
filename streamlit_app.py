import os
import analytics
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="E-Presso BI Dashboard", page_icon="☕", layout="wide"
)

st.title("☕ E-Presso Executive Intelligence Dashboard")
st.caption("Checkpoint 2: Revenue Reconciliation & Core Analytics")

DATA_DIR = "data"


# ---------------------------------------------------------
# Dynamic File Ingestion (Tied to byte buffers for caching)
# ---------------------------------------------------------
@st.cache_data
def load_all_tables(sales_bytes, products_bytes, stores_bytes):
  sales_df = analytics.load_table(sales_bytes, "sales.csv")
  products_df = analytics.load_table(products_bytes, "products.csv")
  stores_df = analytics.load_table(stores_bytes, "stores.csv")
  return analytics.prepare_epresso_data(sales_df, products_df, stores_df)


# Sidebar Uploader (Supports $1,000 modified-data test)
st.sidebar.header("📁 Data Source Management")
sales_upload = st.sidebar.file_uploader(
    "Upload Sales (CSV)", type=["csv", "txt"]
)
products_upload = st.sidebar.file_uploader(
    "Upload Products (CSV)", type=["csv", "txt"]
)
stores_upload = st.sidebar.file_uploader(
    "Upload Stores (CSV)", type=["csv", "txt"]
)

# Resolve file sources (uploaded files take precedence over default files in data/)
sales_bytes = (
    sales_upload.getvalue()
    if sales_upload
    else open(os.path.join(DATA_DIR, "sales.csv"), "rb").read()
)
products_bytes = (
    products_upload.getvalue()
    if products_upload
    else open(os.path.join(DATA_DIR, "products.csv"), "rb").read()
)
stores_bytes = (
    stores_upload.getvalue()
    if stores_upload
    else open(os.path.join(DATA_DIR, "stores.csv"), "rb").read()
)

try:
  df, merge_audits = load_all_tables(sales_bytes, products_bytes, stores_bytes)
except Exception as e:
  st.error(f"Error loading or preparing datasets: {e}")
  st.stop()

# ---------------------------------------------------------
# Calculate Total Revenue using analytics.get_total()
# ---------------------------------------------------------
rev_col = next((c for c in df.columns if c.lower() == "revenue"), "Revenue")
total_result = analytics.get_total(df, value_col=rev_col)

# ---------------------------------------------------------
# Executive KPI Display
# ---------------------------------------------------------
if total_result.error:
  st.error(f"Calculation Error: {total_result.error}")
else:
  col1, col2, col3 = st.columns(3)
  col1.metric("Calculated Total Revenue", f"${total_result.value:,.2f}")
  col2.metric("Total Line Items Analyzed", f"{total_result.rows_used:,}")
  col3.metric("Duplicate Rows", f"{df.duplicated().sum():,}")

  if total_result.caveats:
    for caveat in total_result.caveats:
      st.caption(f"⚠️ {caveat}")

st.divider()

# ---------------------------------------------------------
# Merge Audit Trail (Course Requirement)
# ---------------------------------------------------------
st.subheader("🔍 Merge Integrity Audit")
audit_df = pd.DataFrame(merge_audits)
st.dataframe(audit_df, use_container_width=True)

# Visual alert if fan-out occurred
if any(a.get("changed", False) for a in merge_audits):
  st.error(
      "⚠️ Warning: A join changed row counts or revenue totals! Investigate"
      " keys and grain."
  )
else:
  st.success("✅ Clean joins confirmed: No row duplication or dropped revenue.")
