#!/usr/bin/env python3
"""Generate read-only US deployment settings without broker credentials."""
import argparse
from pathlib import Path
import os
import re
import secrets
import tempfile


def configure(path,domain,mode='us_demo',port=4002,data_type=None):
    path=Path(path).expanduser()
    if path.is_symlink():raise ValueError('Settings path must not be a symlink')
    path=path.resolve()
    if path.is_relative_to(Path(__file__).resolve().parents[1]):raise ValueError('Keep settings outside the Git checkout')
    if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?',domain) or '.' not in domain or '..' in domain:
        raise ValueError('Use a DNS hostname without scheme, port or path')
    if mode not in ('us_demo','ibkr') or port not in (4002,7497):raise ValueError('Use research/demo mode and the paper Gateway/TWS port (4002/7497)')
    if path.exists() and (not path.is_file() or path.stat().st_uid!=os.geteuid()):raise ValueError('Settings file must be owned by your current user')
    lines=path.read_text().splitlines() if path.exists() else []
    values={}
    for line in lines:
        if '=' in line and not line.lstrip().startswith('#'):
            key,value=line.split('=',1);values[key.strip()]=value.strip().strip('\"\'')
    requested=data_type if data_type is not None else values.get('IBKR_DATA_TYPE','live')
    if requested not in ('live','delayed','delayed_frozen'):raise ValueError('Choose live, delayed or delayed_frozen data')
    token=values.get('FO_API_TOKEN')
    if token and len(token)<32:raise ValueError('Existing backend token too short; settings unchanged')
    changed=dict(FO_DOMAIN=domain,FO_MODE=mode,FO_LIVE_ORDERS='false',IBKR_PORT=str(port),IBKR_CLIENT_ID='71',IBKR_DATA_TYPE=requested)
    if not token:changed['FO_API_TOKEN']=secrets.token_urlsafe(48)
    for key,value in changed.items():
        lines=[line for line in lines if not re.match(r'^\s*'+re.escape(key)+r'\s*=',line)]
        lines.append(key+'='+value)
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd,temp=tempfile.mkstemp(prefix='.us-settings-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as stream:stream.write('\n'.join(lines)+'\n');stream.flush();os.fsync(stream.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)


def main():
    parser=argparse.ArgumentParser(description='Create private US demo/IBKR research settings; never requests a broker password')
    parser.add_argument('--domain',required=True)
    parser.add_argument('--mode',choices=('us_demo','ibkr'),default='us_demo')
    parser.add_argument('--port',type=int,choices=(4002,7497),default=4002)
    parser.add_argument('--data-type',choices=('live','delayed','delayed_frozen'),default=None)
    parser.add_argument('--env-file',default='~/compass-private/us.env')
    args=parser.parse_args()
    try:configure(args.env_file,args.domain,args.mode,args.port,args.data_type)
    except (ValueError,OSError) as error:raise SystemExit(str(error))
    print('Private US settings saved. Broker orders disabled. Backend token not displayed.')
    print('Verify DNS points to your NEW server before connecting any client or deploying HTTPS.')

if __name__=='__main__':main()
