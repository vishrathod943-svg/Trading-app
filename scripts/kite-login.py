#!/usr/bin/env python3
"""Run on your own server terminal; never sends credentials through chat or Android."""
import argparse
import getpass
import os
from pathlib import Path
from dotenv import dotenv_values, set_key
from kiteconnect import KiteConnect


def main():
    parser=argparse.ArgumentParser(description='Create a daily Kite session in a private external env file')
    parser.add_argument('--env-file',required=True)
    args=parser.parse_args()
    path=Path(args.env_file).resolve()
    if path.is_relative_to(Path(__file__).resolve().parents[1]):
        parser.error('Keep the credentials file outside the checkout')
    if not path.is_file() or path.stat().st_mode & 0o077:
        parser.error('Use an existing private env file with owner-only permissions (chmod 600)')
    values=dotenv_values(path)
    api_key=values.get('KITE_API_KEY') or getpass.getpass('Kite API key: ')
    api_secret=os.getenv('KITE_API_SECRET') or getpass.getpass('Kite API secret (not saved): ')
    client=KiteConnect(api_key=api_key,timeout=15)
    print('Open this login URL in your own browser; keep this terminal private:')
    print(client.login_url())
    request_token=getpass.getpass('Request token from your registered redirect URL: ')
    try:
        session=client.generate_session(request_token,api_secret=api_secret)
        client.set_access_token(session['access_token'])
        client.profile()
    except Exception:
        raise SystemExit('Session exchange failed. Verify the registered app, request token and API secret. Existing configuration was preserved.')
    set_key(str(path),'KITE_API_KEY',api_key)
    set_key(str(path),'KITE_ACCESS_TOKEN',session['access_token'])
    path.chmod(0o600)
    print('Session verified and saved privately. Restart the backend to load it; automation will be OFF.')

if __name__=='__main__': main()
