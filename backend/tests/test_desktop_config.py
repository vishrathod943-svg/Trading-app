import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('desktop_config',Path(__file__).resolve().parents[2]/'scripts/configure-desktop.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def test_private_hash_file(tmp_path):
    password='validation-only-not-a-real-password'
    hashed=m.password_hash(password)
    p=tmp_path/'private/desktop.env';m.save(p,hashed)
    assert p.read_text()=="DESKTOP_PASSWORD_HASH='"+hashed+"'\n"
    assert password not in p.read_text()
    assert p.stat().st_mode & 0o777==0o600
    p2=tmp_path/'link';p2.symlink_to(p)
    with pytest.raises(ValueError):m.save(p2,hashed)

def test_short_password_rejected():
    with pytest.raises(ValueError):m.password_hash('short')
