#!/usr/bin/env python3
"""Fetch the pinned upstream checkpoint; verify SHA256/LFS and Git blob hashes."""
import hashlib
import json
import subprocess
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
REPO = 'flock-io/this-that-model-1.2'
REV = 'c4d1c30b8d512d278726de439b8cc81fccc70c8f'
FILES = {'README.md', 'config.json', 'generation_config.json', 'model.safetensors',
         'tokenizer.json', 'tokenizer_config.json', 'chat_template.jinja'}

def digest(path, git=False):
    h = hashlib.sha1() if git else hashlib.sha256()
    if git: h.update(f'blob {path.stat().st_size}\0'.encode())
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(8 << 20), b''): h.update(chunk)
    return h.hexdigest()

def main():
    dest = ROOT / 'models' / 'this-that-1.2'
    dest.mkdir(parents=True, exist_ok=True)
    with urlopen(f'https://huggingface.co/api/models/{REPO}/revision/{REV}?blobs=true', timeout=30) as r:
        metadata = json.load(r)
    assert metadata['sha'] == REV
    manifest = {'repository': REPO, 'revision': REV, 'files': {}}
    for item in metadata['siblings']:
        name = item['rfilename']
        if name not in FILES: continue
        path = dest / name
        lfs = item.get('lfs')
        expected = lfs['sha256'] if lfs else item['blobId']
        if not (path.exists() and path.stat().st_size == item['size'] and digest(path, not lfs) == expected):
            part = path.with_suffix(path.suffix + '.part')
            print(f'Downloading {name}: {item["size"]:,} bytes', flush=True)
            subprocess.run(['curl', '--fail', '--location', '--silent', '--show-error',
                            '--connect-timeout', '20', '--max-time', '7200', '--retry', '4',
                            '--continue-at', '-', '--output', str(part),
                            f'https://huggingface.co/{REPO}/resolve/{REV}/{name}'], check=True)
            if part.stat().st_size != item['size'] or digest(part, not lfs) != expected:
                raise RuntimeError(f'Integrity check failed: {name}; remove the .part file before retrying')
            part.replace(path)
        manifest['files'][name] = {'size': path.stat().st_size, 'sha256': digest(path)}
        print(f'Verified {name}', flush=True)
    assert set(manifest['files']) == FILES
    (dest / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')

if __name__ == '__main__': main()
