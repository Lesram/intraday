"""
Feature pipeline types with strong schema contracts.
Provides standardized data structures for leak-free feature processing.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    import pandas as pd

# Stable dtype strings across pandas versions
DType = Literal["float64", "float32", "int64", "int32", "bool"]


@dataclass(frozen=True)
class FeatureSchema:
    """Schema contract for feature data structures."""

    columns: list[str]
    dtypes: dict[str, DType]    # name -> dtype string

    def __post_init__(self):
        """Validate schema consistency."""
        if len(self.columns) != len(set(self.columns)):
            raise ValueError("Duplicate column names in schema")

        if set(self.columns) != set(self.dtypes.keys()):
            raise ValueError("Columns and dtypes keys must match")

    def validate_dataframe(self, df: "pd.DataFrame") -> None:
        """Validate DataFrame against this schema."""
        import pandas as pd

        # Check columns
        missing_cols = set(self.columns) - set(df.columns)
        if missing_cols:
            raise ValueError(f"Missing columns: {sorted(missing_cols)}")

        extra_cols = set(df.columns) - set(self.columns)
        if extra_cols:
            raise ValueError(f"Extra columns: {sorted(extra_cols)}")

        # Check dtypes (allow compatible types)
        for col, expected_dtype in self.dtypes.items():
            actual_dtype = str(df[col].dtype)

            # Allow compatible numeric types
            if expected_dtype.startswith('float') and pd.api.types.is_float_dtype(df[col]) or expected_dtype.startswith('int') and pd.api.types.is_integer_dtype(df[col]) or expected_dtype == 'bool' and pd.api.types.is_bool_dtype(df[col]) or actual_dtype == expected_dtype:
                continue
            else:
                raise ValueError(f"Column '{col}' has dtype {actual_dtype}, expected {expected_dtype}")

    def reorder_columns(self, df: "pd.DataFrame") -> "pd.DataFrame":
        """Reorder DataFrame columns to match schema."""
        return df[self.columns]


@dataclass(frozen=True)
class FeatureFrame:
    """Feature data container with alignment guarantees."""

    X: "pd.DataFrame"           # features, index aligned to price series
    y: "pd.Series | None"       # optional target, same index
    index_mask: "pd.Series[bool]"  # True rows are valid for training/inference

    def __post_init__(self):
        """Validate FeatureFrame consistency."""
        if self.y is not None:
            if not self.X.index.equals(self.y.index):
                raise ValueError("Feature and target indices must be aligned")

        if not self.X.index.equals(self.index_mask.index):
            raise ValueError("Feature and mask indices must be aligned")

        if len(self.X) != len(self.index_mask):
            raise ValueError("Feature and mask must have same length")

    @property
    def valid_rows(self) -> int:
        """Count of valid rows for training/inference."""
        return self.index_mask.sum()

    def filter_valid(self) -> "FeatureFrame":
        """Return FeatureFrame with only valid rows."""
        mask = self.index_mask
        return FeatureFrame(
            X=self.X[mask],
            y=self.y[mask] if self.y is not None else None,
            index_mask=self.index_mask[mask]  # Will be all True
        )


class LookaheadLeakError(ValueError):
    """Raised when lookahead bias is detected in features."""

    def __init__(self, message: str, columns: list[str]):
        super().__init__(message)
        self.columns = columns


class SchemaValidationError(ValueError):
    """Raised when feature schema validation fails."""

    def __init__(self, message: str, missing_columns: list[str] | None = None,
                 extra_columns: list[str] | None = None):
        super().__init__(message)
        self.missing_columns = missing_columns or []
        self.extra_columns = extra_columns or []
