"""Yerel veri göçü ve tek sunucu örneğiyle OptiBid başlatıcısı."""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.request import build_opener, ProxyHandler

APP=Path(__file__).resolve().parent
SETTINGS=json.loads((APP/'baslatma.json').read_text('utf-8'))
VARIABLES={
    'OPTIBID_HAZIRLIK_DB':'hazirliklar.db',
    'OPTIBID_AJAN_DB':'ajan.db',
    'OPTIBID_HAVUZ':'havuz.db',
    'OPTIBID_ARASTIRMA_DB':'arastirma.db',
    'OPTIBID_AYAR_DB':'ayarlar.db',
}
SCHEMA_VERSION=1


def user_dir():
    platform_root=Path(os.environ.get('LOCALAPPDATA') or Path.home()/'.local/share')
    return Path(os.environ.get('OPTIBID_KULLANICI_DIZINI') or platform_root/'OptiBidIhaleAjani').resolve()


def port():
    return int(os.environ.get('OPTIBID_PORT',SETTINGS['port']))


def migrate(old, target):
    """Sürümü başarıdan sonra yaz. Önceden kopyalanmış veritabanlarını ezme."""
    target.mkdir(parents=True,exist_ok=True)
    marker=target/'veri_surumu.json'
    if marker.exists():
        current=json.loads(marker.read_text('utf-8'))
        if current['surum']!=SCHEMA_VERSION:
            raise ValueError('Kullanıcı verisi daha yeni bir OptiBid sürümü gerektiriyor.')
        return current
    copied=[]
    for filename in VARIABLES.values():
        src,dst=old/filename,target/filename
        if dst.exists() or not src.is_file():
            continue
        temporary=dst.with_suffix('.goc.sqlite')
        try:
            with closing(sqlite3.connect(src.resolve().as_uri()+'?mode=ro',uri=True)) as source:
                with closing(sqlite3.connect(temporary)) as backup:
                    source.backup(backup)
                    if backup.execute('PRAGMA quick_check').fetchone()!=('ok',):
                        raise ValueError(f'SQLite yedeği doğrulanamadı: {filename}')
            temporary.replace(dst)
            copied.append(filename)
        finally:
            temporary.unlink(missing_ok=True)
    current={'surum':SCHEMA_VERSION,'kopyalanan':copied}
    staging=marker.with_suffix('.tmp')
    staging.write_text(json.dumps(current,ensure_ascii=False),encoding='utf-8')
    staging.replace(marker)
    return current


def health(port_number, timeout=.45):
    dial=build_opener(ProxyHandler({}))
    try:
        with dial.open(f'http://127.0.0.1:{port_number}/api/saglik',timeout=timeout) as response:
            return json.load(response)
    except (URLError, HTTPError, ValueError, OSError):
        return None


def own(health_data, app=APP):
    path=(health_data or {}).get('uygulama_koku')
    return bool(path and Path(path).resolve()==app.resolve()
                and health_data.get('uygulama_kimligi')==SETTINGS['kimlik'])


def open_browser(url):
    paths=[shutil.which('chrome')]
    paths.extend(Path(os.environ[key])/'Google/Chrome/Application/chrome.exe'
                 for key in ('ProgramFiles','ProgramFiles(x86)','LOCALAPPDATA') if key in os.environ)
    chrome=next((str(p) for p in paths if p and Path(p).is_file()),None)
    if chrome:
        subprocess.Popen([chrome,url])
    else:
        import webbrowser
        if not webbrowser.open(url):
            raise OSError(f'Tarayıcı açılamadı. Adres: {url}')


def start(*, background=False):
    base=user_dir()
    base.mkdir(parents=True,exist_ok=True)
    port_number=port()
    url=f'http://127.0.0.1:{port_number}/'
    with closing(sqlite3.connect(base/'baslatma_kilidi.sqlite',timeout=SETTINGS['hazirlik_suresi_sn']+3)) as lock:
        lock.execute('BEGIN IMMEDIATE')
        try:
            if not own(health(port_number)):
                with socket.socket() as listener:
                    try:
                        if hasattr(socket,'SO_EXCLUSIVEADDRUSE'):
                            listener.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
                        listener.bind(('127.0.0.1',port_number))
                    except OSError as error:
                        raise OSError(f'{port_number} portu başka bir süreçte. Sürece dokunulmadı.') from error
                data=base/'data'
                migrate(APP/'data',data)
                env=dict(os.environ, OPTIBID_NO_BROWSER='1', OPTIBID_PORT=str(port_number))
                env.update({key:str(data/name) for key,name in VARIABLES.items()})
                log=base/'sunucu.log'
                options=({'creationflags':subprocess.DETACHED_PROCESS|subprocess.CREATE_NEW_PROCESS_GROUP}
                         if os.name=='nt' else {'start_new_session':True})
                with log.open('a',encoding='utf-8') as stream:
                    child=subprocess.Popen([sys.executable,'-B','-X','utf8','-u','calistir.py'],cwd=APP,env=env,
                                           stdin=subprocess.DEVNULL,stdout=stream,stderr=stream,**options)
                deadline=monotonic()+SETTINGS['hazirlik_suresi_sn']
                while monotonic()<deadline:
                    if own(health(port_number)):
                        break
                    if child.poll() is not None:
                        raise OSError(f'OptiBid açılırken durdu. Günlük: {log}')
                    sleep(.15)
                else:
                    if child.poll() is None:
                        child.terminate()
                    raise TimeoutError(f'OptiBid hazır olmadı. Günlük: {log}')
        finally:
            lock.rollback()
    if not background:
        open_browser(url)
    return url


def startup(enabled, directory=None):
    if directory is None and os.name!='nt':
        raise OSError('Oturum açılışı ayarı Windows içindir.')
    directory=directory or Path(os.environ['APPDATA'])/'Microsoft/Windows/Start Menu/Programs/Startup'
    path=directory/'OptiBid_Ihale_Ajani.cmd'
    signature='rem OptiBid ihale ajani tarafindan olusturuldu'
    if path.exists() and signature not in path.read_text('utf-8'):
        raise ValueError('Başlangıç dosyası başka bir uygulamaya ait.')
    if not enabled:
        path.unlink(missing_ok=True)
        return path
    directory.mkdir(parents=True,exist_ok=True)
    python=sys.executable.replace('%','%%')
    script=str(APP/'baslat.py').replace('%','%%')
    dependency=os.environ.get('PYTHONPATH','').replace('%','%%')
    content=('@echo off\r\nchcp 65001 >nul\r\n'+signature+'\r\n'
             +f'set "PYTHONPATH={dependency}"\r\n"{python}" -B -X utf8 "{script}" --arka-plan\r\n')
    if not path.exists() or path.read_bytes()!=content.encode():
        path.write_bytes(content.encode())
    return path


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arka-plan',action='store_true')
    choice=parser.add_mutually_exclusive_group()
    choice.add_argument('--oturum-acilisini-ac',action='store_true')
    choice.add_argument('--oturum-acilisini-kapat',action='store_true')
    args=parser.parse_args()
    try:
        print(startup(args.oturum_acilisini_ac) if (args.oturum_acilisini_ac or args.oturum_acilisini_kapat)
              else start(background=args.arka_plan))
    except (OSError, ValueError, sqlite3.Error) as exc:
        root=user_dir()
        root.mkdir(parents=True,exist_ok=True)
        with (root/'baslatma_hatasi.log').open('a',encoding='utf-8') as log:
            print(exc,file=log)
        parser.exit(1,f'{exc}\n')
