"""Business logic.

Keep Streamlit code OUT of this file so every function can be
tested on its own and reused by the assistant.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import io
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
    return pd.read_csv(buffer, sep=None, engine='python')
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
      'dtypes': pd.DataFrame(
          {'column': df.columns, 'dtype': df.dtypes.astype(str).values}
      ),
  }


# ---------------------------------------------------------- tool contract
@dataclass
class ToolResult:
  """Every analytical function returns this.

  The assistant may only narrate it. Keep `value` to plain Python types
  (numbers,
  strings, dicts, lists).
  """

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
  return ToolResult(
      tool=tool,
      value=None,
      definition='',
      scope=scope or {},
      rows_used=0,
      caveats=[],
      error=message,
  )


def _resolve_column(df: pd.DataFrame, col_name: str) -> str | None:
  """Resolves aliases and case-insensitive column names against loaded DataFrame."""
  if not col_name:
    return None

  alias_map = {
      'channel': 'StoreType',
      'channels': 'StoreType',
      'sales_channel': 'StoreType',
      'sales channel': 'StoreType',
      'store_type': 'StoreType',
      'store type': 'StoreType',
      'store': 'StoreType',
      'product_name': 'Product',
      'product name': 'Product',
      'item': 'Product',
      'sku': 'Product',
      'calendar_year': 'Year',
      'calendar year': 'Year',
      'sales': 'Revenue',
      'total_sales': 'Revenue',
  }

  normalized_query = str(col_name).strip().lower()
  target_name = alias_map.get(normalized_query, str(col_name).strip())

  # Direct case-insensitive match against dataframe columns
  for c in df.columns:
    if c.lower() == target_name.lower():
      return c
  return None


def _apply_filters(df: pd.DataFrame, filters: dict | None):
  """Validate filters against the LOADED data, then apply them
