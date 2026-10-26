#!/usr/bin/env python3
"""Private, editor-free initial configuration. Standard library only."""
import argparse
import getpass
import os
from pathlib import Path
import re
import secrets
import tempfile


def find_value(lines, key):
    pattern=re.compile(r'^\s*(?:export\s+)?'+re.escape(key)+r'\s*=\s*(.*)$')
    values=[match.group(1).strip().strip('\"\'') for line in lines if (match:=pattern.match(line))]
    return values[-1] if values else ''


def configure(path, domain, api_key):
    path=Path(path).expanduser()
    if path.is_symlink(): raise ValueError('Settings file must not be a symlink')
    path=path.resolve()
    if path.is_relative_to(Path(__file__).resolve().parents[1]):
        raise ValueError('Keep settings outside the Git checkout')
    if not re.fullmatch(r'[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?',domain) or '.' not in domain or '..' in domain:
        raise ValueError('Enter a hostname without https://, port or path')
    if not re.fullmatch(r'[A-Za-z0-9_-]+',api_key):
        raise ValueError('API key must be nonempty and contain only letters, numbers, underscore or hyphen')
    if path.exists() and (not path.is_file() or path.stat().st_uid!=os.geteuid()):
        raise ValueError('Settings must be a regular file owned by your current user')
    lines=path.read_text().splitlines() if path.exists() else []
    token=find_value(lines,'FO_API_TOKEN')
    if token and len(token)<32: raise ValueError('Existing backend token is too short; settings left unchanged')
    changes={'FO_DOMAIN':domain,'KITE_API_KEY':api_key,'FO_LIVE_ORDERS':'false'}
    if not token: changes['FO_API_TOKEN']=secrets.token_urlsafe(48)
    if not any(re.match(r'^\s*(?:export\s+)?KITE_ACCESS_TOKEN\s*=',line) for line in lines):
        changes['KITE_ACCESS_TOKEN']=''
    for key,value in changes.items():
        lines=[line for line in lines if not re.match(r'^\s*(?:export\s+)?'+re.escape(key)+r'\s*=',line)]
        lines.append(key+'='+value)
    path.parent.mkdir(parents=True,mode=0o700,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix='.fo-settings-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as stream:
            stream.write('\n'.join(lines)+'\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp): os.unlink(temp)


def main():
    parser=argparse.ArgumentParser(description='Save private settings without a text editor')
    parser.add_argument('--domain',required=True)
    parser.add_argument('--env-file',default='~/fo-private/live.env')
    args=parser.parse_args()
    try:
        key=getpass.getpass('Paste Kite API key here (hidden), then press Enter: ').strip()
        configure(args.env_file,args.domain,key)
    except (ValueError,OSError) as error:
        raise SystemExit(str(error))
    print('Private settings saved. Existing access/backend tokens preserved. Real trading is OFF.')

if __name__=='__main__': main()
