#!/usr/bin/env python3
"""Prepare verified Android build tools under /workspace; Linux x86_64 only."""
import hashlib
import os
from pathlib import Path
import platform
import subprocess
import tarfile
import urllib.parse
import zipfile

BASE = Path('/workspace/toolchains')
GRADLE_SHA = 'f397b287023acdba1e9f6fc5ea72d22dd63669d59ed4a289a29b1a76eee151c6'
SDK_SHA = '7ec965280a073311c339e571cd5de778b9975026cfcbe79f2b1cdcb1e15317ee'
JDK_SHA = '810d3773df7e0d6c4394e4e244b264c8b30e0b05a0acf542d065fd78a6b65c2f'

def download(url, name, expected):
    path = BASE / name
    if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        subprocess.run(['curl', '-fL', '--retry', '2', url, '-o', str(path)], check=True)
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise RuntimeError('Artifact checksum mismatch: ' + name)
    return path

def unzip(archive, target):
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for item in z.infolist():
            dest = (target / item.filename).resolve()
            if not dest.is_relative_to(target.resolve()):
                raise RuntimeError('Unsafe archive path')
            z.extract(item, target)
            if not item.is_dir():
                dest.chmod((item.external_attr >> 16) or 0o644)

def main():
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        raise RuntimeError('Use Android Studio on platforms other than Linux x86_64')
    BASE.mkdir(parents=True, exist_ok=True)
    jdk = BASE / 'jdk-21.0.9+10'
    if not (jdk / 'bin/javac').exists():
        archive = download('https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.9%2B10/OpenJDK21U-jdk_x64_linux_hotspot_21.0.9_10.tar.gz', 'jdk.tar.gz', JDK_SHA)
        with tarfile.open(archive) as t:
            t.extractall(BASE, filter='data')
    sdk = BASE / 'android-sdk'
    tools = sdk / 'cmdline-tools/v19'
    if not (tools / 'cmdline-tools/bin/sdkmanager').exists():
        unzip(download('https://dl.google.com/android/repository/commandlinetools-linux-13114758_latest.zip', 'commandline19.zip', SDK_SHA), tools)
    gradle = BASE / 'gradle-8.11.1'
    if not (gradle / 'bin/gradle').exists():
        unzip(download('https://services.gradle.org/distributions/gradle-8.11.1-bin.zip', 'gradle.zip', GRADLE_SHA), BASE)
    home = BASE / 'gradle-home'
    home.mkdir(exist_ok=True)
    proxy = urllib.parse.urlparse(os.environ.get('HTTPS_PROXY', ''))
    # Runtime proxy routing only; never save proxy credentials.
    props = home / 'gradle.properties'
    if proxy.hostname and not props.exists():
        props.write_text('\n'.join([
            f'systemProp.https.proxyHost={proxy.hostname}', f'systemProp.https.proxyPort={proxy.port or 80}',
            f'systemProp.http.proxyHost={proxy.hostname}', f'systemProp.http.proxyPort={proxy.port or 80}',
            'systemProp.http.nonProxyHosts=localhost|127.*']) + '\n')
    env = os.environ.copy()
    env.update(JAVA_HOME=str(jdk), ANDROID_USER_HOME=str(BASE / 'android-user'))
    env['JAVA_TOOL_OPTIONS'] = env.get('JAVA_TOOL_OPTIONS', '') + ' -Djavax.net.ssl.trustStore=/etc/ssl/certs/java/cacerts -Duser.home=' + str(BASE / 'java-user')
    command = [str(tools / 'cmdline-tools/bin/sdkmanager'), '--sdk_root=' + str(sdk)]
    if proxy.hostname:
        command += ['--proxy=http', '--proxy_host=' + proxy.hostname, '--proxy_port=' + str(proxy.port or 80)]
    if not (sdk / 'licenses/android-sdk-license').exists():
        subprocess.run(command + ['--licenses'], input='y\n' * 50, text=True, env=env, check=True)
    subprocess.run(command + ['platforms;android-35', 'build-tools;35.0.0', 'platform-tools'], env=env, check=True)
    print('Android cloud toolchain prepared.')

if __name__ == '__main__':
    main()
