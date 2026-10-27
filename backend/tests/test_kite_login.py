import importlib.util
from pathlib import Path
import pytest
from kiteconnect.exceptions import TokenException, PermissionException
from requests.exceptions import SSLError

spec=importlib.util.spec_from_file_location('kite_login',Path(__file__).resolve().parents[2]/'scripts/kite-login.py')
login=importlib.util.module_from_spec(spec)
spec.loader.exec_module(login)

def test_token_from_full_callback_or_raw_input():
    url='https://example.duckdns.org/kite/callback?status=success&request_token=testtoken123&action=login'
    assert login.extract_request_token(url,'example.duckdns.org')=='testtoken123'
    assert login.extract_request_token('  testtoken123  ','example.duckdns.org')=='testtoken123'
    assert login.extract_request_token('request_token=testtoken123','example.duckdns.org')=='testtoken123'

@pytest.mark.parametrize('url',[
    'https://wrong.example/kite/callback?request_token=sensitive',
    'http://example.duckdns.org/kite/callback?request_token=sensitive',
    'https://example.duckdns.org/kite/callback',
    'https://example.duckdns.org/kite/callback?request_token=a&request_token=b',
    'https://example.duckdns.org/kite/callback?request_token=sensitive&status=failure',
    'https://user:sensitive@example.duckdns.org/kite/callback?request_token=a',
    'https://example.duckdns.org/kite/callback?request_token=a#sensitive',
])
def test_rejects_wrong_urls_without_reflecting_secrets(url):
    with pytest.raises(ValueError) as e: login.extract_request_token(url,'example.duckdns.org')
    assert 'sensitive' not in str(e.value)

@pytest.mark.parametrize('error',[TokenException('sensitive'),PermissionException('sensitive'),SSLError('sensitive'),Exception('sensitive')])
def test_errors_never_echo_exception_contents(error):
    message=login.failure_message(error)
    assert 'sensitive' not in message and 'preserved' in message

def test_checksum_reason_is_sanitized():
    message=login.failure_message(TokenException('Invalid checksum: sensitive'))
    assert 'checksum' in message and 'SAME developer app' in message
    assert 'sensitive' not in message

@pytest.mark.parametrize('stage',['exchange','profile'])
def test_identifies_failed_authentication_stage_without_leaking(stage):
    class Client:
        def generate_session(self,token,api_secret):
            if stage=='exchange': raise TokenException('sensitive')
            return {'access_token':'synthetic-test-token'}
        def set_access_token(self,token): pass
        def profile(self): raise TokenException('sensitive')
    with pytest.raises(SystemExit) as error:
        login.exchange_and_verify(Client(),'synthetic-request','synthetic-secret')
    message=str(error.value)
    assert ('TOKEN EXCHANGE FAILED' if stage=='exchange' else 'ACCOUNT CHECK FAILED') in message
    assert 'sensitive' not in message and 'synthetic-test-token' not in message
