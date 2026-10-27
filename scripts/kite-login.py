#!/usr/bin/env python3
"""Run on your own server terminal; never sends credentials through chat or Android."""
import argparse
import getpass
import os
import re
from urllib.parse import urlsplit, parse_qs
from pathlib import Path
from dotenv import dotenv_values, set_key
from kiteconnect import KiteConnect
from kiteconnect import exceptions as kite_errors
from requests import exceptions as request_errors


def extract_request_token(value, domain):
    value=value.strip()
    if len(value)>8192: raise ValueError('Input is too long; paste the final redirect URL or request token')
    if '://' in value:
        try:
            url=urlsplit(value)
            query=parse_qs(url.query,keep_blank_values=True,max_num_fields=20)
            valid=(url.scheme=='https' and url.hostname==(domain or '').strip().lower()
                   and url.port in (None,443) and url.username is None and url.password is None
                   and url.path=='/kite/callback' and not url.fragment)
        except ValueError:
            raise ValueError('Invalid redirect URL; use the final callback address from your browser') from None
        if not valid: raise ValueError('Use the final HTTPS callback URL for the hostname in your private settings')
        if 'status' in query and query['status']!=['success']:
            raise ValueError('The redirect does not report success; complete a fresh Zerodha login')
        tokens=query.get('request_token',[])
        if len(tokens)!=1: raise ValueError('No single request_token found; copy the final browser address after login')
        value=tokens[0]
    elif value.startswith('request_token='):
        value=value[len('request_token='):]
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,1024}',value):
        raise ValueError('Invalid request token format; use the final redirect URL, not the login URL, API key or API secret')
    return value


def failure_message(error):
    # Deliberately never include exception text: broker/network errors can contain secrets.
    if isinstance(error,(kite_errors.TokenException,kite_errors.InputException)) and 'checksum' in str(error).lower():
        reason='Kite rejected the login checksum. Re-copy the API secret from the SAME developer app as your saved API key, and use a new login from this helper.'
    elif isinstance(error,kite_errors.TokenException):
        reason='Broker rejected authentication. Use a fresh, unused request token and the secret matching this API key.'
    elif isinstance(error,kite_errors.PermissionException):
        reason='Broker denied API permission. Check the app/account permissions and required broker IP settings.'
    elif isinstance(error,kite_errors.InputException):
        reason='Broker rejected the login inputs. Check that the API key and API secret belong to the same app.'
    elif isinstance(error,request_errors.SSLError):
        reason='TLS certificate verification failed. Fix server trust configuration; do not disable TLS verification.'
    elif isinstance(error,(request_errors.Timeout,request_errors.ConnectionError,kite_errors.NetworkException)):
        reason='Cannot complete the broker request. Check server Internet access and generate a new login before retrying.'
    else:
        reason='Broker session exchange or profile verification failed. Check the registered app and use a fresh login.'
    code=getattr(error,'code',None)
    suffix=f' HTTP {code}.' if isinstance(code,int) and 400<=code<=599 else ''
    return reason+suffix+' Existing configuration was preserved.'


def exchange_and_verify(client,request_token,api_secret):
    try:
        session=client.generate_session(request_token,api_secret=api_secret)
    except Exception as error:
        raise SystemExit('TOKEN EXCHANGE FAILED: '+failure_message(error)) from None
    try:
        client.set_access_token(session['access_token'])
        client.profile()
    except Exception as error:
        raise SystemExit('ACCOUNT CHECK FAILED after token exchange: '+failure_message(error)) from None
    return session


def main():
    parser=argparse.ArgumentParser(description='Create a daily Kite session in a private external env file')
    parser.add_argument('--env-file',required=True)
    parser.add_argument('--prompt-secret',action='store_true',help='Prompt for a fresh secret instead of using a saved shell environment value')
    args=parser.parse_args()
    path=Path(args.env_file).resolve()
    if path.is_relative_to(Path(__file__).resolve().parents[1]):
        parser.error('Keep the credentials file outside the checkout')
    if not path.is_file() or path.stat().st_mode & 0o077:
        parser.error('Use an existing private env file with owner-only permissions (chmod 600)')
    values=dotenv_values(path)
    api_key=(values.get('KITE_API_KEY') or getpass.getpass('Kite API key: ')).strip()
    api_secret=((None if args.prompt_secret else os.getenv('KITE_API_SECRET')) or getpass.getpass('Kite API secret from the same developer app (not saved): ')).strip()
    client=KiteConnect(api_key=api_key,timeout=15)
    print('Open this login URL in your own browser; keep this terminal private:')
    print(client.login_url())
    print('After login, copy the complete final browser address. It stays hidden when pasted here.')
    try:
        request_token=extract_request_token(getpass.getpass('Final redirect URL or request token (hidden): '),values.get('FO_DOMAIN'))
    except ValueError as error:
        raise SystemExit(str(error)) from None
    if request_token in (api_key,api_secret):
        raise SystemExit('The request token matches your API key/secret. Use the final redirect URL from a fresh browser login. Settings preserved.')
    session=exchange_and_verify(client,request_token,api_secret)
    set_key(str(path),'KITE_API_KEY',api_key)
    set_key(str(path),'KITE_ACCESS_TOKEN',session['access_token'])
    path.chmod(0o600)
    print('Session verified and saved privately. Restart the backend to load it; automation will be OFF.')

if __name__=='__main__': main()
