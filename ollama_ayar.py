"""Yerel Ollama model seçimini sunucu tarafında kalıcı saklar."""
import json
import os
from contextlib import closing
from pathlib import Path
import sqlite3
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
DEFAULT_MODEL = 'qwen3:8b'
MODELS = (DEFAULT_MODEL,)

def path():
    return Path(os.environ.get('OPTIBID_AYAR_DB',ROOT/'data/ayarlar.db'))

def secili():
    # Yeni istek politikası. Eski ayar dosyaları ve rapor metadatası geçmişi korur.
    return DEFAULT_MODEL

def kaydet(model):
    if not isinstance(model,str) or model not in MODELS:
        raise ValueError('Bu sürümde yeni istekler yalnız qwen3:8b kullanır.')
    p=path()
    p.parent.mkdir(parents=True,exist_ok=True)
    with closing(sqlite3.connect(p)) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS yerel_ayar(anahtar TEXT PRIMARY KEY,deger TEXT NOT NULL)')
        db.execute("INSERT INTO yerel_ayar VALUES('ollama_model',?) ON CONFLICT(anahtar) DO UPDATE SET deger=excluded.deger",(model,))
    return model

def mevcut_modeller(timeout=3):
    with urlopen('http://127.0.0.1:11434/api/tags',timeout=timeout) as r:
        return json.load(r)['models']

def durum(timeout=3):
    installed=None
    status='kapalı'
    if os.environ.get('OPTIBID_LLM','on')!='off':
        status='erişilemiyor'
        try:
            installed={m['name'] for m in mevcut_modeller(timeout)}
            status='bağlı'
        except (OSError,ValueError,KeyError,TypeError):
            pass
    if installed is not None and DEFAULT_MODEL not in installed:
        status='qwen3:8b kurulu değil'
    return {'secili':secili(),'durum':status,'num_ctx':4096,'es_zamanli':1,
            'kurulum':'ollama pull qwen3:8b' if status=='qwen3:8b kurulu değil' else None,
            'modeller':[{'ad':name,'kurulu':name in installed if installed is not None else None} for name in MODELS]}
