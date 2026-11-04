"""Writing style regression: banned dash punctuation in product strings.

See WRITING_STYLE.md. Prose hyphens are a review convention (code
identifiers legitimately contain hyphens); em dashes, en dashes, and
ASCII double hyphens have no legitimate use in product code.
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRODUCT = ["app.py", "pruvcore", "pruvcards", "providers", "pruvfetch",
           "ui", "scripts/smoke_live.py"]


def _sources():
    for rel in PRODUCT:
        path = os.path.join(ROOT, rel)
        if os.path.isdir(path):
            for name in sorted(os.listdir(path)):
                if name.endswith(".py"):
                    yield os.path.join(path, name)
        else:
            yield path


def test_no_em_or_en_dashes_in_product_code():
    bad = [src for src in _sources()
           if "\u2014" in open(src, encoding="utf-8").read()
           or "\u2013" in open(src, encoding="utf-8").read()]
    assert bad == []


def test_no_ascii_double_hyphen_in_product_code():
    bad = [src for src in _sources()
           if " -- " in open(src, encoding="utf-8").read()]
    assert bad == []
