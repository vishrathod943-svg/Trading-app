#!/usr/bin/env python3
"""Opt-in phone desktop HTTPS password; no broker/backend secret input or output."""
import argparse
import getpass
import os
from pathlib import Path
import tempfile
import warnings


def password_hash(password):
    if len(password)<14 or len(password)>64 or not password.isascii():
        raise ValueError('Use 14–64 ASCII characters for a separate desktop website password')
    # Ubuntu 24.04 Python 3.12/libcrypt supports bcrypt; fail rather than weaken.
    with warnings.catch_warnings():
        warnings.simplefilter('ignore',DeprecationWarning)
        import crypt
    if crypt.METHOD_BLOWFISH not in crypt.methods:raise ValueError('bcrypt unavailable; use Ubuntu 24.04 Python 3.12')
    hashed=crypt.crypt(password,crypt.mksalt(crypt.METHOD_BLOWFISH,rounds=2**14))
    if not hashed or not hashed.startswith(('$2a$','$2b$','$2y$')):raise ValueError('bcrypt hashing failed')
    return hashed


def save(path,hashed):
    path=Path(path).expanduser()
    if path.is_symlink():raise ValueError('Private settings must not be a symlink')
    if path.resolve().is_relative_to(Path(__file__).resolve().parents[1]):raise ValueError('Keep private settings outside the repository')
    if path.exists() and (not path.is_file() or path.stat().st_uid!=os.geteuid()):raise ValueError('Settings must be owned by the current user')
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(dir=path.parent,prefix='.desktop-')
    try:
        # Single quotes keep bcrypt dollars literal during Compose env-file parsing.
        with os.fdopen(fd,'w') as f:
            f.write("DESKTOP_PASSWORD_HASH='"+hashed+"'\n");f.flush();os.fsync(f.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)


def main():
    parser=argparse.ArgumentParser(description='Create separate website login for optional HTTPS noVNC access')
    parser.add_argument('--env-file',default='~/compass-private/desktop.env')
    args=parser.parse_args()
    password=getpass.getpass('Create desktop WEBSITE password (14–64 characters, hidden): ')
    if password!=getpass.getpass('Repeat desktop WEBSITE password (hidden): '):raise SystemExit('Passwords differ; nothing saved')
    try:save(args.env_file,password_hash(password))
    except (ValueError,OSError) as e:raise SystemExit(str(e))
    print('Private password hash saved. Website username: operator. No broker credentials requested.')
    print('This does not start or expose VNC. Keep desktop ports closed and loopback-only.')

if __name__=='__main__':main()
