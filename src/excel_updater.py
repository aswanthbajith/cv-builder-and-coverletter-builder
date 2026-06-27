"""Excel updater module for writing results back to spreadsheet."""

import logging
from pathlib import Path
from typing import Optional
import pandas as pd

try:
    from .config import config
except ImportError:
    from config import config

logger = logging.getLogger(__name__)


class ExcelUpdater:
    """Update Excel files with generation results and hyperlinks."""

    def __init__(self, output_path: Optional[str] = None):
        self.output_path = output_path or config.get('paths.output_excel', 'output/Job_Matching_Updated.xlsx')

    def update(self, df: pd.DataFrame) -> None:
        """Save DataFrame with hyperlinks and formatting."""
        Path(self.output_path).parent.mkdir(parents=True, exist_ok=True)

        df_links = self._add_hyperlinks(df)

        with pd.ExcelWriter(self.output_path, engine='openpyxl') as writer:
            df_links.to_excel(writer, index=False, sheet_name='Job Matches')

            worksheet = writer.sheets['Job Matches']
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except Exception:
                        pass
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[column_letter].width = adjusted_width

        logger.info(f"Saved updated Excel to: {self.output_path}")

    def _add_hyperlinks(self, df: pd.DataFrame) -> pd.DataFrame:
        """Convert file paths to Excel HYPERLINK formulas."""
        result = df.copy()

        for col in ['resume_pdf', 'resume_tex', 'cover_letter']:
            if col in result.columns:
                result[col] = result[col].apply(
                    lambda x: f'=HYPERLINK("{x}","Open {col.replace("_", " ").title()}")'
                    if pd.notna(x) and str(x).strip() else ''
                )

        return result
