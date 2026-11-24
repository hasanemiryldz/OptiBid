"""OptiBid kaynak manifestini ve mevcut SQLite arşivini tekilleştirerek aktarır."""
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from urllib.request import urlopen
from hashlib import sha256
import argparse

ROOT = Path(__file__).resolve().parent
def aktar(indir=False):
    manifest = json.loads((ROOT/'kaynaklar.json').read_text(encoding='utf-8-sig'))
    with sqlite3.connect((ROOT.parent/'optibid.db').as_uri()+'?mode=ro',uri=True) as kaynak, sqlite3.connect(ROOT/'data/havuz.db') as db:
        db.execute("""CREATE TABLE IF NOT EXISTS kayit(ikn TEXT PRIMARY KEY,kategori TEXT,kaynak TEXT,tarih TEXT,ulke TEXT,para TEXT,miktar INTEGER,birim TEXT,fiyat TEXT,fiyat_turu TEXT,kalite TEXT,tahmine_uygun INTEGER)""")
        for ikn,tarih,para,miktar,birim,bedel,durum in kaynak.execute("SELECT ikn,ihale_tarihi,para_birimi,miktar,birim,sozlesme_bedeli,durum FROM ihaleler"):
            db.execute("INSERT OR REPLACE INTO kayit VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(ikn,'kırtasiye','optibid.db#'+ikn,tarih,'TR',para,miktar,birim,bedel,'sözleşme toplamı',durum,int(durum=='URUN_DOGRULANDI')))
        for r in manifest:
            db.execute("INSERT OR IGNORE INTO kayit VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(r['ikn'],r['kategori'],r['url'],r.get('tarih'),'TR',r.get('para'),r.get('miktar'),r.get('birim'),r.get('fiyat'),'sözleşme toplamı' if r.get('fiyat') else None,r.get('kalite','resmî ilan referansı'),0))
            if indir:
                try:
                    with urlopen(r['url'],timeout=8) as response:
                        data=response.read(8000001)
                    if len(data)>8000000: raise ValueError('Boyut sınırı')
                    dest=ROOT/'data/kaynaklar';dest.mkdir(exist_ok=True)
                    (dest/sha256(data).hexdigest()).write_bytes(data)
                    db.execute("CREATE TABLE IF NOT EXISTS belgeler(url TEXT,sha256 TEXT,zaman TEXT,PRIMARY KEY(url,sha256))")
                    db.execute("INSERT OR IGNORE INTO belgeler VALUES(?,?,?)",(r['url'],sha256(data).hexdigest(),datetime.now(timezone.utc).isoformat()))
                except Exception as e:
                    print(r['ikn'],str(e))
        return dict(kategoriler=dict(db.execute('SELECT kategori,count(*) FROM kayit GROUP BY kategori')),benzersiz=db.execute('SELECT count(*) FROM kayit').fetchone()[0],fiyata_uygun=db.execute('SELECT sum(tahmine_uygun) FROM kayit').fetchone()[0],arsiv_belgeleri=kaynak.execute('SELECT count(*) FROM belgeler').fetchone()[0])
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--indir',action='store_true')
    print(json.dumps(aktar(parser.parse_args().indir),ensure_ascii=False,indent=2))
