"""Business logic. Keep Streamlit code OUT of this file so every function can be
tested on its own and reused by the assistant."""
from __future__ import annotations

import io
from dataclasses import asdict, dataclass, field

import pandas as pd

EXCEL_EXT = ('.xlsx', '.xlsm', '.xls')
TEXT_EXT = ('.csv', '.txt', '.tsv')


# ---------------------------------------------------------------- loading
def excel_sheet_names(file_bytes: bytes) -> list[str]:
    return pd.ExcelFile(io.BytesIO(file_bytes)).sheet_names


def load_table(file_bytes: bytes, filename: str, sheet_name=0) -> pd.DataFrame:
    """Read an uploaded CSV / TXT / TSV / Excel file into a DataFrame."""
    name = filename.lower()
    buffer = io.BytesIO(file_bytes)
    if name.endswith(EXCEL_EXT):
        return pd.read_excel(buffer, sheet_name=sheet_name)
    if name.endswith(TEXT_EXT):
        return pd.read_csv(buffer, sep=None, engine='python')  # sniffs the delimiter
    raise ValueError(f'Unsupported file type: {filename}')


def profile_table(df: pd.DataFrame) -> dict:
    """Basic profile: size, duplicates, missing values, data types."""
    missing = df.isna().sum()
    return {
        'rows': len(df),
        'columns': df.shape[1],
        'duplicate_rows': int(df.duplicated().sum()),
        'missing': pd.DataFrame({
            'column': missing.index,
            'missing': missing.values,
            'pct_missing': (missing.values / max(len(df), 1) * 100).round(2),
        }),
        'dtypes': pd.DataFrame({'column': df.columns, 'dtype': df.dtypes.astype(str).values}),
    }


# ---------------------------------------------------------- tool contract
@dataclass
class ToolResult:
    """Every analytical function returns this. The assistant may only narrate it.
    Keep `value` to plain Python types (numbers, strings, dicts, lists)."""
    tool: str
    value: object
    definition: str
    scope: dict
    rows_used: int
    caveats: list = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _error(tool: str, message: str, scope: dict | None = None) -> ToolResult:
    return ToolResult(tool=tool, value=None, definition='', scope=scope or {},
                      rows_used=0, caveats=[], error=message)


def _apply_filters(df: pd.DataFrame, filters: dict | None):
    """Validate filters against the LOADED data, then apply them."""
    for col, wanted in (filters or {}).items():
        if col not in df.columns:
            return df, f'Unknown column: {col}'
        wanted_list = list(wanted) if isinstance(wanted, (list, tuple, set)) else [wanted]
        valid = set(df[col].dropna().unique())
        bad = [w for w in wanted_list if w not in valid]
        if bad:
            examples = sorted(map(str, valid))[:20]
            return df, f'{bad} not found in column {col}. Valid values include: {examples}'
        df = df[df[col].isin(wanted_list)]
    return df, None


# ------------------------------------------------------ analytical tools
def get_total(df: pd.DataFrame, value_col: str, filters: dict | None = None) -> ToolResult:
    """Sum of one numeric column, optionally filtered. EXAMPLE tool: replace the
    generic column names with your own definition of revenue."""
    name = 'get_total'
    if value_col not in df.columns:
        return _error(name, f'Unknown column: {value_col}')
    subset, err = _apply_filters(df, filters)
    if err:
        return _error(name, err, {'filters': filters})
    values = pd.to_numeric(subset[value_col], errors='coerce')
    n_bad = int(values.isna().sum())
    caveats = ['This is a sum of the chosen column. Revenue is not profit.']
    if n_bad:
        caveats.append(f'{n_bad} row(s) had a missing or non-numeric {value_col} and were excluded.')
    return ToolResult(tool=name, value=float(values.sum()), definition=f'Sum of {value_col}',
                      scope={'filters': filters or 'none (all rows)'},
                      rows_used=int(values.notna().sum()), caveats=caveats)


def group_total(df: pd.DataFrame, value_col: str, group_col: str,
                filters: dict | None = None) -> ToolResult:
    """Sum of one numeric column by group (store, channel, year, ...)."""
    name = 'group_total'
    for col in (value_col, group_col):
        if col not in df.columns:
            return _error(name, f'Unknown column: {col}')
    subset, err = _apply_filters(df, filters)
    if err:
        return _error(name, err, {'filters': filters})
    work = subset.assign(**{value_col: pd.to_numeric(subset[value_col], errors='coerce')})
    n_bad = int(work[value_col].isna().sum())
    n_nogroup = int(work[group_col].isna().sum())
    grouped = work.dropna(subset=[value_col, group_col]).groupby(group_col)[value_col].sum()
    caveats = ['Sums of the chosen column. Revenue is not profit.']
    if n_bad:
        caveats.append(f'{n_bad} row(s) with missing or non-numeric {value_col} were excluded.')
    if n_nogroup:
        caveats.append(f'{n_nogroup} row(s) with a missing {group_col} were excluded.')
    return ToolResult(tool=name, value={str(k): float(v) for k, v in grouped.items()},
                      definition=f'Sum of {value_col} by {group_col}',
                      scope={'filters': filters or 'none (all rows)'},
                      rows_used=int(len(work) - n_bad - n_nogroup), caveats=caveats)


def data_quality_report(df: pd.DataFrame) -> ToolResult:
    """Row count, duplicate rows, and missing values per column."""
    missing = {c: int(n) for c, n in df.isna().sum().items() if n > 0}
    caveats = []
    if missing:
        caveats.append('Missing values may limit conclusions drawn from those columns.')
    return ToolResult(tool='data_quality_report',
                      value={'rows': len(df), 'duplicate_rows': int(df.duplicated().sum()),
                             'columns_with_missing': missing},
                      definition='Counts of duplicate rows and missing values in the loaded table',
                      scope={'filters': 'none (full table)'}, rows_used=len(df), caveats=caveats)


# ------------------------------------------------------------ merge check
def check_merge(left: pd.DataFrame, right: pd.DataFrame, on, value_col: str, how: str = 'left'):
    """Merge, and report whether the join changed the row count or the revenue sum.
    `value_col` must be a numeric column in `left`. Returns (merged, report)."""
    before_rows = len(left)
    before_sum = float(pd.to_numeric(left[value_col], errors='coerce').sum())
    merged = left.merge(right, on=on, how=how)
    after_rows = len(merged)
    after_sum = float(pd.to_numeric(merged[value_col], errors='coerce').sum())
    fan_out = after_rows > before_rows or abs(after_sum - before_sum) > 1e-9
    report = {
        'rows_before': before_rows, 'rows_after': after_rows,
        'sum_before': before_sum, 'sum_after': after_sum,
        'changed': fan_out,
        'warning': ('The join changed the row count or the total. Check the grain and keys '
                    'of both tables before using this result.') if fan_out else '',
    }
    return merged, report

# --------------------------------------------------- data prep & join pipeline
def _find_matching_key(
    df1: pd.DataFrame, df2: pd.DataFrame, candidate_names: list[str]
) -> tuple[str | None, str | None]:
  """Finds matching key columns between two tables regardless of casing, BOM, or whitespace."""

  def normalize(s: str) -> str:
    return (
        s.lower()
        .replace("\ufeff", "")
        .replace(" ", "")
        .replace("_", "")
        .replace("-", "")
    )

  map1 = {normalize(c): c for c in df1.columns}
  map2 = {normalize(c): c for c in df2.columns}

  for cand in candidate_names:
    norm_cand = normalize(cand)
    if norm_cand in map1 and norm_cand in map2:
      return map1[norm_cand], map2[norm_cand]

  return None, None


def prepare_epresso_data(
    df_sales: pd.DataFrame, df_products: pd.DataFrame, df_stores: pd.DataFrame
) -> tuple[pd.DataFrame, list[dict]]:
  """Standardizes keys, prepares date dimensions, and joins dimensions onto Sales Fact

  using check_merge to audit row counts and revenue totals.
  """
  reports = []

  # Clean BOM (\ufeff), whitespace, and hidden quotes across column headers
  for df in (df_sales, df_products, df_stores):
    df.columns = [c.strip().lstrip("\ufeff") for c in df.columns]

  # 1. Date parsing: extract Year and Month
  date_col = next((c for c in df_sales.columns if c.lower() == "date"), None)
  if date_col:
    df_sales[date_col] = pd.to_datetime(df_sales[date_col])
    df_sales["Year"] = df_sales[date_col].dt.year
    df_sales["Month"] = df_sales[date_col].dt.strftime("%Y-%m")

  # Detect exact column name for Revenue
  rev_col = next(
      (c for c in df_sales.columns if c.lower() == "revenue"), "Revenue"
  )
  if rev_col not in df_sales.columns:
    raise ValueError(
        f"Sales table missing Revenue column. Found: {list(df_sales.columns)}"
    )

  # 2. Match and merge Products Dim
  sales_prod_key, prod_key = _find_matching_key(
      df_sales, df_products, ["Product ID", "ProductID", "Product_ID", "Product"]
  )

  if not sales_prod_key or not prod_key:
    raise KeyError(
        "Could not find matching Product key. Sales columns:"
        f" {list(df_sales.columns)}, Products columns:"
        f" {list(df_products.columns)}"
    )

  df_sales[sales_prod_key] = df_sales[sales_prod_key].astype(str).str.strip()
  df_products[prod_key] = df_products[prod_key].astype(str).str.strip()

  if sales_prod_key != prod_key:
    df_products = df_products.rename(columns={prod_key: sales_prod_key})
    prod_key = sales_prod_key

  merged_1, report_1 = check_merge(
      left=df_sales,
      right=df_products,
      on=sales_prod_key,
      value_col=rev_col,
      how="left",
  )
  report_1["step"] = (
      f"Sales Fact + Products Dim (on {sales_prod_key} -> {prod_key})"
  )
  reports.append(report_1)

  # 3. Match and merge Stores Dim
    sales_store_key, store_key = _find_matching_key(
        merged_1, df_stores, ['Store ID', 'StoreID', 'Store_ID', 'Store']
    )

    # Fallback: Stores dim often names its primary key simply 'ID'
    if not store_key and "ID" in df_stores.columns:
      sales_store_key = "Store ID"
      store_key = "ID"

    if not sales_store_key or not store_key:
      raise KeyError(
          "Could not find matching Store key. Sales columns:"
          f" {list(merged_1.columns)}, Stores columns: {list(df_stores.columns)}"
      )

    merged_1[sales_store_key] = (
        merged_1[sales_store_key].astype(str).str.strip()
    )
    df_stores[store_key] = df_stores[store_key].astype(str).str.strip()

    if sales_store_key != store_key:
      df_stores = df_stores.rename(columns={store_key: sales_store_key})
      store_key = sales_store_key

    final_df, report_2 = check_merge(
        left=merged_1,
        right=df_stores,
        on=sales_store_key,
        value_col=rev_col,
        how="left",
    )
    report_2["step"] = (
        f"Sales/Products + Stores Dim (on {sales_store_key} -> {store_key})"
    )
    reports.append(report_2)

  return final_df, reports
