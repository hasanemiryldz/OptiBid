"""Yerel hazırlıklar için kalıcı rapor ve süreli silme işlemleri."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import sqlite3
from time import time
from uuid import UUID, uuid4

def init(db):
    from sartname import init as sartname_init
    sartname_init(db)
    db.execute("CREATE TABLE IF NOT EXISTS rapor_kayitlari(id TEXT PRIMARY KEY, rev INTEGER, belge TEXT, sonuc TEXT, tarih TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS silinen_hazirliklar(id TEXT PRIMARY KEY, grup TEXT, bitis REAL)")
    db.execute("""CREATE TABLE IF NOT EXISTS rapor_gecmisi(
        id TEXT, rev INTEGER, belge TEXT, sonuc TEXT, tarih TEXT, PRIMARY KEY(id,tarih))""")
    db.execute("""CREATE TABLE IF NOT EXISTS rapor_senaryolari(
        id TEXT PRIMARY KEY, rapor_id TEXT, rapor_tarihi TEXT, veri TEXT, kayit_tarihi TEXT)""")
    db.execute("CREATE INDEX IF NOT EXISTS silinen_hazirliklar_bitis ON silinen_hazirliklar(bitis)")

@contextmanager
def connection(path, write=False):
    db=sqlite3.connect(path)
    try:
        if write:
            db.execute("PRAGMA secure_delete=ON")
            db.execute("BEGIN IMMEDIATE")
        with db:
            yield db
    finally:
        db.close()

def purge(db):
    from sartname import purge as sartname_purge
    sartname_purge(db,time())
    for table,id_col in (("rapor_gecmisi","id"),("rapor_senaryolari","rapor_id")):
        db.execute(f"DELETE FROM {table} WHERE {id_col} IN (SELECT id FROM silinen_hazirliklar WHERE bitis<=?)",(time(),))
    db.execute("DELETE FROM rapor_kayitlari WHERE id IN (SELECT id FROM silinen_hazirliklar WHERE bitis<=?)",(time(),))
    db.execute("DELETE FROM hazirliklar WHERE id IN (SELECT id FROM silinen_hazirliklar WHERE bitis<=?)",(time(),))
    db.execute("DELETE FROM silinen_hazirliklar WHERE bitis<=?",(time(),))


def temizlenecek(path):
    """Zamanı gelmiş silme yokken yazma işlemi başlatma."""
    from contextlib import closing
    now = time()
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
        row = db.execute("""SELECT EXISTS (SELECT 1 FROM silinen_hazirliklar WHERE bitis<=?)
            OR EXISTS (SELECT 1 FROM sartname_dosyalari s WHERE s.yukleme<?
                AND NOT EXISTS (SELECT 1 FROM sartname_baglari WHERE sha=s.sha))""",
            (now,now-86400)).fetchone()
    return bool(row[0])


def list_records(db):
    sql="""SELECT h.doc,r.sonuc,r.tarih FROM hazirliklar h
           LEFT JOIN rapor_kayitlari r ON r.id=h.id AND r.rev=h.rev
           WHERE NOT EXISTS (SELECT 1 FROM silinen_hazirliklar s WHERE s.id=h.id)
           ORDER BY COALESCE(r.tarih,'') DESC,h.rowid DESC"""
    records=[]
    for raw,result,when in db.execute(sql):
        doc=json.loads(raw)
        summary=json.loads(result) if result else {}
        doc["rapor_ozeti"]=dict(tarih=when,fiyat=summary.get("medyan") if summary.get("source_policy")=="EKAP_ONLY" else None,ay=summary.get("ay") if summary.get("source_policy")=="EKAP_ONLY" else None,
                               guven="Düşük" if summary.get("medyan") else None)
        records.append(doc)
    return records

def snapshot(db, key):
    key=str(UUID(key))
    row=db.execute("""SELECT r.belge,r.sonuc,r.tarih FROM rapor_kayitlari r JOIN hazirliklar h
        ON h.id=r.id AND h.rev=r.rev WHERE r.id=? AND NOT EXISTS
        (SELECT 1 FROM silinen_hazirliklar s WHERE s.id=r.id)""",(key,)).fetchone()
    return {"belge":json.loads(row[0]),"sonuc":json.loads(row[1]),"tarih":row[2]} if row else None

def save_report(db, doc, result):
    key=str(UUID(doc["id"]))
    row=db.execute("""SELECT rev FROM hazirliklar h WHERE id=? AND NOT EXISTS
        (SELECT 1 FROM silinen_hazirliklar s WHERE s.id=h.id)""",(key,)).fetchone()
    if not row or row[0]!=doc.get("rev"):
        return None
    when=datetime.now(timezone.utc).isoformat()
    doc.pop("rapor_ozeti",None)
    db.execute("INSERT OR IGNORE INTO rapor_gecmisi SELECT * FROM rapor_kayitlari WHERE id=?",(key,))
    db.execute("INSERT OR REPLACE INTO rapor_kayitlari VALUES (?,?,?,?,?)",
               (key,row[0],json.dumps(doc,ensure_ascii=False),json.dumps(result,ensure_ascii=False),when))
    return when

def mark_deleted(db, params):
    purge(db)
    all_records=params.get("tum") is True
    if all_records:
        if params.get("onay")!="TÜM KAYITLARI SİL":
            raise ValueError("Onay metni eşleşmiyor.")
        keys=[r[0] for r in db.execute("SELECT id FROM hazirliklar")]
    else:
        ids=params.get("id")
        if not isinstance(ids,list) or not 1<=len(ids)<=1000:
            raise ValueError("Silmek için bir kayıt seçin.")
        keys=list(dict.fromkeys(str(UUID(i)) for i in ids))
    token=str(uuid4())
    deadline=time()+8
    count=0
    for key in keys:
        count+=db.execute("""INSERT OR IGNORE INTO silinen_hazirliklar
            SELECT id,?,? FROM hazirliklar WHERE id=?""",(token,deadline,key)).rowcount
    return {"grup":token,"bitis":deadline,"adet":count}

def undo(db, group):
    purge(db)
    return db.execute("DELETE FROM silinen_hazirliklar WHERE grup=?",(str(UUID(group)),)).rowcount

