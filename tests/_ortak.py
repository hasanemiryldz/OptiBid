import json
import os
from pathlib import Path
import sqlite3
import shutil
import sys
import tempfile
from contextlib import closing
from unittest import TestCase
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]

class Yalitim(TestCase):
    def setUp(self):
        tmp=Path(self.enterContext(tempfile.TemporaryDirectory()))
        pool=tmp/'havuz.db'
        with closing(sqlite3.connect((ROOT/'data/havuz.db').as_uri()+'?mode=ro',uri=True)) as db, closing(sqlite3.connect(pool)) as dest:
            db.backup(dest)
        index=tmp/'yi_ufe.json'
        shutil.copy2(ROOT/'data/tuik/yi_ufe.json', index)
        self.enterContext(patch.dict(os.environ, {
            'OPTIBID_HAVUZ':str(pool), 'OPTIBID_HAZIRLIK_DB':str(tmp/'hazirliklar.db'),
            'OPTIBID_AJAN_DB':str(tmp/'ajan.db'), 'OPTIBID_ARASTIRMA_DB':str(tmp/'arastirma.db'),
            'OPTIBID_TUIK_VERI':str(index), 'OPTIBID_PORT':'0', 'OPTIBID_NO_BROWSER':'1',
            'OPTIBID_LLM':'off'
        }))
        import emsal, motor
        self.enterContext(patch.object(emsal,'POOL',pool))
        self.motor=motor
        self.doc=motor.oku('kagit_ornegi.json')

def altin(r):
    return {**{k:r[k] for k in ('durum','medyan','alt','ust','toplam','kdv','ay','yontem')},
            'aday_sayisi':r['aday_sayisi'],'kullanilan':sorted(x[0] for x in r['emsaller']),'dislanan':sorted(r['haric'])}
