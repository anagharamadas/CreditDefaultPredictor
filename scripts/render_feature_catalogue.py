"""Write docs/FEATURE_CATALOGUE.md from the catalogue renderer.

Run:  PYTHONPATH=src python scripts/render_feature_catalogue.py
"""

from pathlib import Path

from credit_default.features.catalogue import render_markdown

OUT = Path("docs/FEATURE_CATALOGUE.md")

if __name__ == "__main__":
    OUT.write_text(render_markdown())
    print(f"wrote {OUT}")
