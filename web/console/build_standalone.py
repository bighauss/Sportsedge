"""Package the zero-network SportsEdge console as ONE offline HTML file.

This is an optional local export. It does not upload data, publish a site or
contain provider credentials, odds, projections or wagering features.
"""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def build(out: Path) -> None:
    html = (ROOT / 'index.html').read_text(encoding='utf-8')
    css = (ROOT / 'styles.css').read_text(encoding='utf-8')
    core = (ROOT / 'core.js').read_text(encoding='utf-8')
    app = (ROOT / 'app.js').read_text(encoding='utf-8')
    if '</script' in core.lower() or '</script' in app.lower() or '</style' in css.lower():
        raise ValueError('Inline script/style sentinel found; refuse unsafe packaging')
    html = html.replace('<link rel="stylesheet" href="./styles.css">', '<style>\n' + css + '\n</style>')
    html = html.replace('<script defer src="./core.js"></script>', '<script>\n' + core + '\n</script>')
    html = html.replace('<script defer src="./app.js"></script>', '<script>\n' + app + '\n</script>')
    html = html.replace(
        'content="default-src \'self\'; script-src \'self\'; style-src \'self\'; connect-src \'none\'; img-src \'self\' data:; object-src \'none\'; base-uri \'none\'; form-action \'none\'; frame-src \'none\'"',
        'content="default-src \'none\'; script-src \'unsafe-inline\'; style-src \'unsafe-inline\'; connect-src \'none\'; img-src data:; object-src \'none\'; base-uri \'none\'; form-action \'none\'; frame-src \'none\'"'
    )
    if 'src="./core.js"' in html or 'src="./app.js"' in html or 'href="./styles.css"' in html:
        raise ValueError('Packaging incomplete')
    if 'PAPER / 0u' not in html or 'connect-src \'none\'' not in html:
        raise ValueError('Safety labels or offline policy missing')
    # Explicitly refuse overwrite; this is an immutable user's local copy.
    with out.open('x', encoding='utf-8') as f:
        f.write(html)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    build(args.out)
    print(f'OFFLINE RESEARCH CONSOLE / PAPER_0U: {args.out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
