from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pdfplumber

from .workbook import RAW_HEADERS


def find_pdftoppm() -> str | None:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        bundled = Path(frozen_root) / "poppler_bin" / "pdftoppm.exe"
        if bundled.exists():
            return str(bundled)

    env_override = shutil.which("pdftoppm.exe")
    if env_override:
        return env_override

    env_path = shutil.which("pdftoppm")
    if env_path and not env_path.lower().endswith(".cmd"):
        return env_path

    home_candidate = (
        Path.home()
        / ".cache"
        / "codex-runtimes"
        / "codex-primary-runtime"
        / "dependencies"
        / "native"
        / "poppler"
        / "Library"
        / "bin"
        / "pdftoppm.exe"
    )
    if home_candidate.exists():
        return str(home_candidate)
    return None


def render_pdf_pages(pdf_path: str | Path, output_dir: str | Path, dpi: int = 200) -> list[Path]:
    pdf = Path(pdf_path)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    pdftoppm = find_pdftoppm()
    if not pdftoppm:
        raise RuntimeError("未找到 pdftoppm。请安装 Poppler，或设置 PATH 后重试。")

    prefix = out_dir / pdf.stem
    command = [pdftoppm, "-png", "-r", str(dpi), str(pdf), str(prefix)]
    subprocess.run(command, check=True)
    return sorted(out_dir.glob(f"{pdf.stem}-*.png"))


def extract_selectable_text(pdf_path: str | Path) -> list[str]:
    pages: list[str] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text(x_tolerance=2, y_tolerance=2) or "")
    return pages


def create_manual_table_template(
    output_path: str | Path,
    rows: int = 14,
    source_page: int | str = "",
) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        handle.write(",".join(RAW_HEADERS) + "\n")
        for index in range(1, rows + 1):
            values = ["支架", str(index), "", "", "", "", "", str(source_page), ""]
            handle.write(",".join(values) + "\n")
    return output


def pdf_has_selectable_text(pdf_path: str | Path) -> bool:
    return any(page.strip() for page in extract_selectable_text(pdf_path))
