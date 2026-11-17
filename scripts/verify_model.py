#!/usr/bin/env python3
import hashlib
import json
import sys
from pathlib import Path

def verify(root):
    root = Path(root)
    manifest = json.loads((root / 'manifest.json').read_text())
    if manifest['revision'] != 'c4d1c30b8d512d278726de439b8cc81fccc70c8f':
        raise ValueError('Unexpected model revision')
    for name, spec in manifest['files'].items():
        path = root / name
        if path.stat().st_size != spec['size']: raise ValueError(f'Invalid size: {name}')
        h = hashlib.sha256()
        with path.open('rb') as f:
            for chunk in iter(lambda: f.read(8 << 20), b''): h.update(chunk)
        if h.hexdigest() != spec['sha256']: raise ValueError(f'Invalid SHA256: {name}')
    print('Verified THIS/THAT 1.2 checkpoint', flush=True)

if __name__ == '__main__': verify(sys.argv[1])
