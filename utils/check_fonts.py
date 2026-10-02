"""CLI to test font discovery and cache validation (moved to utils).

Usage:
  python -m utils.check_fonts --list
  python -m utils.check_fonts --search "Helvetica" --test-fitz
  python -m utils.check_fonts --dump fonts.json
"""

from __future__ import annotations

_PRINT_DEBUG = False  # ← ACTIVADO para ver todos los prints de debug
if not _PRINT_DEBUG:
    def _no_print(*args, **kwargs):
        return None
    print = _no_print

import json
from pathlib import Path

# Import moved to function level to avoid circular import
# from utils import font_index


def run_list():
    from utils import font_index
    try:
        idx = font_index.build_font_index()
    except Exception as ex:
        print(f"Error enumerating fonts: {ex}")
        print("On macOS ensure PyObjC is installed for CoreText access, or run with a different fallback method.")
        return
    print(f"Found {len(idx)} families on {font_index.PLATFORM}")
    for i, (fam, items) in enumerate(sorted(idx.items())):
        print(f"{i+1:3d}. {fam} ({len(items)} files)")
        if i >= 50:
            print("... (truncated)")
            break


def run_search(query: str, test_fitz: bool = False):
    from utils import font_index
    try:
        idx = font_index.build_font_index()
    except Exception as ex:
        print(f"Error enumerating fonts: {ex}")
        print("On macOS ensure PyObjC is installed for CoreText access, or run with a different fallback method.")
        return
    found = {fam: items for fam, items in idx.items() if query.lower() in fam.lower()}
    if not found:
        print("No families match:", query)
        return
    for fam, items in sorted(found.items()):
        print(f"Family: {fam} -> {len(items)} entries")
        for e in items:
            print("  ", e.get('name'), e.get('path'))
            if test_fitz:
                try:
                    import fitz  # PyMuPDF
                    try:
                        _ = fitz.Font(fontfile=e.get('path'))
                        print("    [fitz OK]")
                    except Exception as ex:
                        print("    [fitz FAIL]", ex)
                except Exception:
                    print("    [fitz not installed]")


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--search", help="Search family substring")
    parser.add_argument("--dump", help="Dump JSON index to path")
    parser.add_argument("--test-fitz", action="store_true", help="Try to instantiate fonts via PyMuPDF")

    args = parser.parse_args()

    if args.list:
        run_list()
    elif args.search:
        run_search(args.search, test_fitz=args.test_fitz)
    elif args.dump:
        from utils import font_index
        try:
            idx = font_index.build_font_index()
        except Exception as ex:
            print(f"Error enumerating fonts: {ex}")
            return
        p = Path(args.dump)
        p.write_text(json.dumps(idx, indent=2, ensure_ascii=False), encoding="utf-8")
        print("Wrote:", p)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
