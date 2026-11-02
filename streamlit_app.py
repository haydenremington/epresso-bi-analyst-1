import os
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="E-Presso BI Dashboard", page_icon="☕", layout="wide"
)

st.title("☕ E-Presso Data Profile & Grain Audit")
st.caption("Checkpoint 1: Verifying Source Tables, Types, and Grains")

DATA_DIR = "data"


# Ensure file contents are tied to caching
@st.cache_data
def load_csv(path):
  return pd.read_csv(path)


@st.cache_data
def load_excel(path):
  return pd.read_excel(path)


# Safe data loader
datasets = {}
if os.path.exists(f"{DATA_DIR}/sales.csv"):
  datasets["Sales Fact"] = load_csv(f"{DATA_DIR}/sales.csv")
if os.path.exists(f"{DATA_DIR}/products.csv"):
  datasets["Products Dim"] = load_csv(f"{DATA_DIR}/products.csv")
if os.path.exists(f"{DATA_DIR}/stores.csv"):
  datasets["Stores Dim"] = load_csv(f"{DATA_DIR}/stores.csv")
if os.path.exists(f"{DATA_DIR}/survey.xlsx"):
  datasets["Survey Fact"] = load_excel(f"{DATA_DIR}/survey.xlsx")

if not datasets:
  st.warning(
      "No datasets found in data/ folder. Please push files to GitHub or check"
      " file names."
  )
  st.stop()

# Tabs for scannable data inspection
tabs = st.tabs(list(datasets.keys()))

for tab, (name, df) in zip(tabs, datasets.items()):
  with tab:
    st.subheader(f"Table Profile: {name}")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Row Count", f"{len(df):,}")
    col2.metric("Column Count", df.shape[1])
    col3.metric("Duplicate Rows", f"{df.duplicated().sum():,}")
    col4.metric(
        "Memory Usage", f"{df.memory_usage().sum() / 1024**2:.2f} MB"
    )

    st.markdown("##### Column Types and Null Counts")
    profile_df = pd.DataFrame(
        {
            "Data Type": df.dtypes.astype(str),
            "Non-Null Count": df.notnull().sum(),
            "Null Count": df.isnull().sum(),
            "Null %": (df.isnull().mean() * 100).round(2),
            "Unique Values": df.nunique(),
        }
    )
    st.dataframe(profile_df, use_container_width=True)

    with st.expander("Preview Top 20 Rows"):
      st.dataframe(df.head(20), use_container_width=True)
