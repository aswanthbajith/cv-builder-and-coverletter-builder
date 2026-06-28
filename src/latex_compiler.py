"""Standalone LaTeX compiler utility."""

import logging
import subprocess
from pathlib import Path
from typing import Optional

from job_automation.config import load_config

logger = logging.getLogger(__name__)


class LaTeXCompiler:
    """Compile LaTeX documents to PDF using xelatex."""

    def __init__(self):
        import shutil
        compiler = shutil.which('xelatex')
        if compiler is None:
            fallback = Path("C:/Program Files/MiKTeX/miktex/bin/x64/xelatex.exe")
            if fallback.exists():
                compiler = str(fallback)
        self.compiler = compiler or 'xelatex'

    def compile(self, tex_path: Path, output_dir: Optional[Path] = None) -> Optional[Path]:
        """Compile a .tex file to PDF."""
        tex_path = Path(tex_path)
        if not tex_path.exists():
            logger.error(f"LaTeX file not found: {tex_path}")
            return None

        if output_dir is None:
            output_dir = tex_path.parent
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        pdf_path = output_dir / tex_path.with_suffix('.pdf').name

        try:
            for _ in range(2):
                result = subprocess.run(
                    [self.compiler, '-interaction=nonstopmode',
                     '-output-directory', str(output_dir),
                     str(tex_path)],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                if result.returncode != 0 and '!' in result.stdout:
                    logger.warning(f"LaTeX warning: {result.stdout[-500:]}")

            if pdf_path.exists():
                logger.info(f"Compiled PDF: {pdf_path}")
                return pdf_path
            else:
                logger.error("PDF output not found after compilation")
                return None

        except subprocess.TimeoutExpired:
            logger.error("LaTeX compilation timed out")
            return None
        except Exception as e:
            logger.error(f"PDF compilation failed: {e}")
            return None
