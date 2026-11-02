import os
import analytics
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(
    page_title="E-Presso BI Dashboard", page_icon="☕", layout="wide"
)

st.title("☕ E-Presso Executive Intelligence Dashboard")
st.caption("Checkpoint 2: Validated Analytics & Interactive Visualizations")

DATA_DIR = "data"


# ---------------------------------------------------------
# Dynamic File Ingestion
# ---------------------------------------------------------
@st.cache_data
def load_all_tables(sales_bytes, products_bytes, stores_bytes):
  sales_df = analytics.load_table(sales_bytes, "sales.csv")
  products_df = analytics.load_table(products_bytes, "products.csv")
  stores_df = analytics.load_table(stores_bytes, "stores.csv")
  return analytics.prepare_epresso_data(sales_df, products_df, stores_df)


# Sidebar: Data Source Management
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
  df_raw, merge_audits = load_all_tables(
      sales_bytes, products_bytes, stores_bytes
  )
except Exception as e:
  st.error(f"Error loading datasets: {e}")
  st.stop()

# ---------------------------------------------------------
# Sidebar: Dynamic Interactive Filters (Built from data)
# ---------------------------------------------------------
st.sidebar.header("🎯 Dashboard Filters")

# 1. Year Filter
year_col = "Year" if "Year" in df_raw.columns else None
years = (
    ["All"] + sorted(df_raw[year_col].dropna().unique().tolist())
    if year_col
    else ["All"]
)
selected_year = st.sidebar.selectbox("Filter by Year", years)

# 2. Sales Channel Filter
channel_col = next(
    (
        c
        for c in df_raw.columns
        if c.lower() in ["channel", "storetype", "location"]
    ),
    None,
)
channels = (
    ["All"] + sorted(df_raw[channel_col].dropna().unique().tolist())
    if channel_col
    else ["All"]
)
selected_channel = st.sidebar.selectbox("Filter by Sales Channel", channels)

# 3. Store / City Filter
city_col = next(
    (c for c in df_raw.columns if c.lower() in ["city", "store", "store_name"]),
    None,
)
cities = (
    ["All"] + sorted(df_raw[city_col].dropna().unique().tolist())
    if city_col
    else ["All"]
)
selected_city = st.sidebar.selectbox("Filter by Store Location", cities)

# Apply filters dynamically
active_filters = {}
if selected_year != "All" and year_col:
  active_filters[year_col] = selected_year
if selected_channel != "All" and channel_col:
  active_filters[channel_col] = selected_channel
if selected_city != "All" and city_col:
  active_filters[city_col] = selected_city

filtered_df, filter_err = analytics._apply_filters(df_raw, active_filters)
if filter_err:
  st.error(filter_err)
  st.stop()

# ---------------------------------------------------------
# Dynamic KPI Display
# ---------------------------------------------------------
rev_col = next(
    (c for c in filtered_df.columns if c.lower() == "revenue"), "Revenue"
)
kpi_total = analytics.get_total(
    df_raw, value_col=rev_col, filters=active_filters
)

col1, col2, col3 = st.columns(3)
col1.metric("Selected Revenue", f"${kpi_total.value:,.2f}")
col2.metric("Line Items in Scope", f"{kpi_total.rows_used:,}")
col3.metric(
    "Share of Total Revenue",
    f"{(kpi_total.value / df_raw[rev_col].sum() * 100):.2f}%",
)

if kpi_total.caveats:
  for caveat in kpi_total.caveats:
    st.caption(f"⚠️ {caveat}")

st.divider()

# ---------------------------------------------------------
# Required Visualizations (3 Charts)
# ---------------------------------------------------------
chart_row1_col1, chart_row1_col2 = st.columns(2)

# Chart 1: Revenue by Sales Channel
with chart_row1_col1:
  st.subheader("1. Revenue by Channel")
  if channel_col:
    channel_summary = (
        filtered_df.groupby(channel_col, as_index=False)[rev_col]
        .sum()
        .sort_values(by=rev_col, ascending=False)
    )
    fig_channel = px.pie(
        channel_summary,
        names=channel_col,
        values=rev_col,
        hole=0.4,
        color_discrete_sequence=px.colors.qualitative.Safe,
    )
    fig_channel.update_traces(textposition="inside", textinfo="percent+label")
    st.plotly_chart(fig_channel, use_container_width=True)
  else:
    st.info("Channel column not found.")

# Chart 2: Revenue Trend by Year
with chart_row1_col2:
  st.subheader("2. Annual Revenue Progression")
  if year_col:
    year_summary = (
        filtered_df.groupby(year_col, as_index=False)[rev_col]
        .sum()
        .sort_values(by=year_col)
    )
    fig_year = px.line(
        year_summary,
        x=year_col,
        y=rev_col,
        markers=True,
        labels={rev_col: "Revenue ($)", year_col: "Year"},
    )
    fig_year.update_layout(xaxis=dict(tickmode="linear"))
    st.plotly_chart(fig_year, use_container_width=True)
  else:
    st.info("Year column not found.")

# Chart 3: Revenue by Store City / Location
st.subheader("3. Revenue by Location")
if city_col:
  city_summary = (
      filtered_df.groupby(city_col, as_index=False)[rev_col]
      .sum()
      .sort_values(by=rev_col, ascending=True)
  )
  fig_city = px.bar(
      city_summary,
      x=rev_col,
      y=city_col,
      orientation="h",
      labels={rev_col: "Revenue ($)", city_col: "Location"},
      color=rev_col,
      color_continuous_scale="Teal",
  )
  st.plotly_chart(fig_city, use_container_width=True)
else:
  st.info("Location/City column not found.")

st.divider()
# ---------------------------------------------------------
# Monthly Revenue Pattern Validation Matrix
# ---------------------------------------------------------
with st.expander("📅 Monthly Revenue Pattern & Seasonality Matrix"):
  st.markdown(
      "Reconciliation grid verifying the 12-month by 5-year pattern against"
      " Power BI."
  )

  # Ensure date column exists and extract numerical month and month name
  date_col = next((c for c in df_raw.columns if c.lower() == "date"), "Date")
  df_matrix = df_raw.copy()
  df_matrix[date_col] = pd.to_datetime(df_matrix[date_col])

  df_matrix["Month_Num"] = df_matrix[date_col].dt.month
  df_matrix["Month_Name"] = df_matrix[date_col].dt.strftime("%B")
  df_matrix["Year_Val"] = df_matrix[date_col].dt.year

  # Create pivot matrix: Months on rows, Years on columns
  pivot_monthly = df_matrix.pivot_table(
      index=["Month_Num", "Month_Name"],
      columns="Year_Val",
      values="Revenue",
      aggfunc="sum",
  ).fillna(0)

  # Add Total Column across all 5 years
  pivot_monthly["5-Year Total"] = pivot_monthly.sum(axis=1)

  # Reset index and drop numerical sort column for clean display
  display_matrix = pivot_monthly.reset_index()
  display_matrix = display_matrix.drop(columns=["Month_Num"]).rename(
      columns={"Month_Name": "Month"}
  )

  # Format numbers as currency
  formatted_matrix = display_matrix.copy()
  for col in formatted_matrix.columns:
    if col != "Month":
      formatted_matrix[col] = formatted_matrix[col].apply(
          lambda x: f"${x:,.2f}"
      )

  # Render interactive table
  st.dataframe(formatted_matrix, use_container_width=True, hide_index=True)

  # Anchor Metric Verification Cards
  december_total = pivot_monthly.loc[
      (12, slice(None)), "5-Year Total"
  ].values[0]
  february_total = pivot_monthly.loc[(2, slice(None)), "5-Year Total"].values[0]

  v_col1, v_col2 = st.columns(2)
  v_col1.metric("December 5-Year Peak", f"${december_total:,.2f}")
  v_col2.metric("February 5-Year Trough", f"${february_total:,.2f}")

# ---------------------------------------------------------
# Additional Measure Validation: Top Selling Product
# ---------------------------------------------------------
with st.expander("🏆 Additional Measure: Top Selling Product Audit"):
  st.markdown(
      "Validation of product-level revenue rankings against Power BI."
  )

  # Identify Product column
  prod_col = next(
      (c for c in df_raw.columns if c.lower() in ["product", "product_name"]),
      "Product",
  )

  # Calculate revenue grouped by product using analytics.group_total
  prod_tool_res = analytics.group_total(
      df_raw, value_col="Revenue", group_col=prod_col
  )

  if prod_tool_res.error:
    st.error(f"Product grouping error: {prod_tool_res.error}")
  else:
    # Sort dictionary descending by revenue
    sorted_prods = sorted(
        prod_tool_res.value.items(), key=lambda item: item[1], reverse=True
    )
    df_top_prods = pd.DataFrame(sorted_prods, columns=["Product", "Revenue"])
    df_top_prods["Share"] = (
        (df_top_prods["Revenue"] / df_raw["Revenue"].sum() * 100).round(2)
    )

    top_name = df_top_prods.iloc[0]["Product"]
    top_rev = df_top_prods.iloc[0]["Revenue"]
    top_share = df_top_prods.iloc[0]["Share"]

    col1, col2 = st.columns(2)
    col1.metric("Top Selling Product", top_name)
    col2.metric("5-Year Revenue", f"${top_rev:,.2f}", delta=f"{top_share}% of total")

    # Format table for inspection
    df_display = df_top_prods.copy()
    df_display["Revenue"] = df_display["Revenue"].apply(lambda x: f"${x:,.2f}")
    df_display["Share"] = df_display["Share"].apply(lambda x: f"{x:.2f}%")

    st.markdown("##### Full Product Revenue Breakdown")
    st.dataframe(df_display, use_container_width=True, hide_index=True)
# ---------------------------------------------------------
# Merge Audit Trail
# ---------------------------------------------------------
with st.expander("🔍 View Data Ingestion & Merge Audit"):
  st.dataframe(pd.DataFrame(merge_audits), use_container_width=True)
