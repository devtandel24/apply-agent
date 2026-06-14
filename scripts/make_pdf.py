#!/usr/bin/env python3
"""Render an HTML resume to PDF using headless Chrome.

Usage: python scripts/make_pdf.py output/acme-ml-engineer/resume.html
Writes the PDF next to the HTML file (resume.html -> resume.pdf).
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from resume_check import ats_lint


def lint_html(html_path: Path) -> list[str]:
    return ats_lint(Path(html_path).read_text(encoding="utf-8"))


CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    html = Path(sys.argv[1]).resolve()
    if not html.exists():
        print(f"not found: {html}")
        return 1
    problems = lint_html(html)
    if problems:
        print("ATS lint FAILED — fix before rendering:")
        for p in problems:
            print(f"  - {p}")
        return 2
    pdf = html.with_suffix(".pdf")
    subprocess.run(
        [CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer",
         f"--print-to-pdf={pdf}", f"file://{html}"],
        check=True, capture_output=True, timeout=60,
    )
    print(f"PDF written: {pdf}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
