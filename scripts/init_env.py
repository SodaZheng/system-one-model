#!/usr/bin/env python3
"""Create a deployment key without replacing an existing configuration."""
import os
import secrets
from pathlib import Path
path = Path(__file__).resolve().parents[1] / '.env'
try:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    print('.env already exists; preserved.')
else:
    with os.fdopen(fd, 'w') as f:
        f.write('API_KEY=' + secrets.token_urlsafe(32) + '\nPORT=8080\n')
    print('Created .env (mode 0600). API key not printed.')
