#!/usr/bin/env python3
"""Paper Boom: a paper dart outrunning its own sonic boom (a pleated paper shock cone).

Entry point: copy the pre-rendered art/entry.png to the output, byte for byte.
Fallback only: if the art is missing or not a PNG, run the (slow) renderer instead."""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'art', 'entry.png')
SIG = b'\x89PNG\r\n\x1a\n'


def main():
    out_dir = os.environ.get('MAKEFUN_OUTPUT_DIR') or '/output'
    os.makedirs(out_dir, exist_ok=True)
    dst = os.path.join(out_dir, 'entry.png')
    data = b''
    if os.path.isfile(SRC):
        with open(SRC, 'rb') as fh:
            data = fh.read()
    if data[:8] == SIG:
        with open(dst, 'wb') as fh:
            fh.write(data)
    else:
        print('main.py: %s missing or not a PNG; re-rendering (slow)' % SRC, file=sys.stderr)
        sys.path.insert(0, HERE)
        try:
            import render
        except ImportError:
            print('main.py: error: render.py not found next to main.py; cannot produce entry.png',
                  file=sys.stderr)
            return 1
        render.main(['--out', dst])
    return 0


if __name__ == '__main__':
    sys.exit(main())
