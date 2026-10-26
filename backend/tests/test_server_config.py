import importlib.util
from pathlib import Path
import stat
import pytest

spec=importlib.util.spec_from_file_location('configure_server',Path(__file__).resolve().parents[2]/'scripts/configure-server.py')
config=importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)

def test_private_config_creation_and_preservation(tmp_path):
    path=tmp_path/'private/live.env'
    config.configure(path,'example.duckdns.org','testkey123')
    first=path.read_text()
    token=config.find_value(first.splitlines(),'FO_API_TOKEN')
    assert len(token)>=32 and stat.S_IMODE(path.stat().st_mode)==0o600
    path.write_text(first.replace('KITE_ACCESS_TOKEN=','KITE_ACCESS_TOKEN=existing-test-session')+'CUSTOM_SETTING=retain\n')
    config.configure(path,'example.duckdns.org','newtestkey')
    second=path.read_text()
    assert config.find_value(second.splitlines(),'FO_API_TOKEN')==token
    assert 'KITE_ACCESS_TOKEN=existing-test-session' in second and 'CUSTOM_SETTING=retain' in second
    assert 'FO_LIVE_ORDERS=false' in second

def test_rejects_invalid_input_without_replacing_file(tmp_path):
    path=tmp_path/'live.env';path.write_text('sentinel')
    for domain,key in [('https://example.com','validkey'),('example.com','bad\nkey')]:
        with pytest.raises(ValueError): config.configure(path,domain,key)
        assert path.read_text()=='sentinel'

def test_rejects_symlink(tmp_path):
    target=tmp_path/'target';target.write_text('sentinel')
    link=tmp_path/'link';link.symlink_to(target)
    with pytest.raises(ValueError): config.configure(link,'example.com','validkey')
    assert target.read_text()=='sentinel'
