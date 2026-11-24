"""Doğrulanmış yerel arşiv alıntıları için kalıcı FTS5 ve isteğe bağlı Ollama embedding araması."""
import argparse
from array import array
from contextlib import closing
from hashlib import sha256
import json
from math import isfinite, sqrt
import os
from pathlib import Path
import re
import sqlite3
from urllib.request import Request, build_opener, ProxyHandler

import baslat
from veri_yollari import ARCHIVE

SETTINGS=json.loads((Path(__file__).with_name('belge_indeksi.json')).read_text('utf-8'))


def path():
    return Path(os.environ.get('OPTIBID_BELGE_INDEKSI') or baslat.user_dir()/'data'/'belge_indeksi.sqlite')


def rows_from_archive(archive=ARCHIVE):
    from ekap_veri import verified
    from ekap_sayfalari import ozet_hash

    proofs=verified()
    allowed={(i,b['dosya'],b['sha256']):r for i,r in proofs.items() for b in r['belgeler']}
    if archive.is_file() and allowed:
        with closing(sqlite3.connect(archive.as_uri()+'?mode=ro',uri=True)) as db:
            for ikn,name,digest,body in db.execute('SELECT ikn,dosya,sha256,metin FROM belgeler'):
                key=ikn,name,digest
                if key in allowed:
                    p=allowed[key]
                    for number,line in enumerate(body.splitlines(),1):
                        if 18<=len(line)<=2400:
                            yield (*key,number,line,p.get('kaynak_url'),
                                   json.dumps(p.get('kategori'),ensure_ascii=False),(p.get('sonuc') or {}).get('tarih'))
    for ikn,proof in proofs.items():
        page=proof.get('web_kaniti')
        if page:
            digest=ozet_hash(page)
            for row in page['satirlar']:
                if 18<=len(row['metin'])<=2400:
                    yield (ikn,'EKAP asıl sayfası',digest,row['satir'],row['metin'],page['url'],
                           json.dumps(proof.get('kategori'),ensure_ascii=False),(proof.get('sonuc') or {}).get('tarih'))


def initialize(db, chunks):
    records=sorted(set(chunks),key=lambda row:row[:5])
    version=sha256(json.dumps((SETTINGS['surum'],records),ensure_ascii=False).encode()).hexdigest()
    with db:
        db.execute('CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS vector(id INTEGER PRIMARY KEY,digest TEXT, value BLOB)')
        db.execute('''CREATE VIRTUAL TABLE IF NOT EXISTS alinti USING fts5(
            ikn UNINDEXED, dosya UNINDEXED, sha UNINDEXED, konum UNINDEXED, metin,
            url UNINDEXED, kategori UNINDEXED, tarih UNINDEXED, tokenize='unicode61 remove_diacritics 2')''')
        db.execute('BEGIN IMMEDIATE')
        saved=db.execute("SELECT value FROM meta WHERE key='version'").fetchone()
        if saved!=(version,):
            db.execute('DELETE FROM vector')
            db.execute('DELETE FROM alinti')
            db.executemany('INSERT INTO alinti VALUES (?,?,?,?,?,?,?,?)',records)
            db.execute("INSERT OR REPLACE INTO meta VALUES('version',?)",(version,))
    return version,len(records)


def ollama(endpoint,payload=None):
    if os.environ.get('OPTIBID_LLM','on')=='off':
        raise OSError('Ollama kapalı')
    dial=build_opener(ProxyHandler({}))
    url='http://127.0.0.1:11434/api/'+endpoint
    request=Request(url,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'}) if payload else url
    with dial.open(request,timeout=SETTINGS['embedding_sure_sn']) as response:
        return json.load(response)


def embed_identity():
    return next((m['digest'] for m in ollama('tags')['models']
                 if m['name']==SETTINGS['embedding_model'] and m.get('digest')),None)


def embed(inputs, keep_alive=0):
    model=SETTINGS['embedding_model']
    result=ollama('embed',{'model':model,'input':inputs,'truncate':False,'keep_alive':keep_alive})
    if result['model']!=model or len(result['embeddings'])!=len(inputs):
        raise ValueError('Embedding model kimliği veya parti boyutu uyuşmuyor.')
    vectors=[]
    for values in result['embeddings']:
        if len(values)!=SETTINGS['embedding_boyutu'] or not all(isfinite(x) for x in values):
            raise ValueError('Embedding boyutu veya sayısal değeri geçersiz.')
        length=sqrt(sum(x*x for x in values))
        if not length:
            raise ValueError('Boş embedding.')
        vectors.append(array('f',(x/length for x in values)))
    return vectors


def prepare(db, *, limit=None, ikn=''):
    version=db.execute("SELECT value FROM meta WHERE key='version'").fetchone()
    digest=embed_identity()
    if not digest:
        raise OSError('embeddinggemma:latest yerelde kurulu görünmüyor.')
    remaining=db.execute('''SELECT rowid,metin FROM alinti WHERE (?='' OR ikn=?) AND rowid NOT IN
                        (SELECT id FROM vector WHERE digest=?) ORDER BY rowid LIMIT ?''',
                        (ikn,ikn,digest,-1 if limit is None else limit)).fetchall()
    size=SETTINGS['embedding_parti']
    for start in range(0,len(remaining),size):
        group=remaining[start:start+size]
        vectors=embed([text for _,text in group],keep_alive='30s' if start+size<len(remaining) else 0)
        with db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT value FROM meta WHERE key='version'").fetchone()!=version:
                raise ValueError('Arşiv değişti. İndeks hazırlama yeniden başlatılmalı.')
            db.executemany('INSERT OR REPLACE INTO vector VALUES (?,?,?)',
                           [(rowid,digest,v.tobytes()) for (rowid,_),v in zip(group,vectors,strict=True)])
    return {'eklenen':len(remaining),'model':SETTINGS['embedding_model'],'digest':digest}


def search(db,query,ikn=''):
    terms=list(dict.fromkeys(re.findall(r'[^\W_]+',query[:240].casefold())))[:14]
    if not terms:
        return []
    clause=' OR '.join('"'+t+'"' for t in terms)
    lex=[row[0] for row in db.execute(
        "SELECT rowid FROM alinti WHERE alinti MATCH ? AND (?='' OR ikn=?) ORDER BY bm25(alinti),rowid LIMIT ?",
        (clause,ikn,ikn,SETTINGS['fts_aday_sayisi']))]
    vectors=[]
    try:
        if db.execute('SELECT 1 FROM vector LIMIT 1').fetchone() and (digest:=embed_identity()):
            blobs=db.execute("SELECT v.id,v.value FROM vector v JOIN alinti a ON a.rowid=v.id "
                             "WHERE v.digest=? AND (?='' OR a.ikn=?)",(digest,ikn,ikn)).fetchall()
            count=db.execute("SELECT count(*) FROM alinti WHERE ?='' OR ikn=?",(ikn,ikn)).fetchone()[0]
            if count and len(blobs)==count:
                query_vector,=embed([query[:240]])
                scores=[]
                for rowid,blob in blobs:
                    v=array('f')
                    v.frombytes(blob)
                    if len(v)!=len(query_vector):
                        raise ValueError('Saklanan embedding boyutu uyuşmuyor.')
                    scores.append((sum(a*b for a,b in zip(v,query_vector,strict=True)),rowid))
                vectors=[rowid for _,rowid in sorted(scores,reverse=True)[:SETTINGS['fts_aday_sayisi']]]
    except (OSError,ValueError,KeyError,TypeError):
        vectors=[]
    rank={}
    for ordered in (lex,vectors):
        for position,rowid in enumerate(ordered,1):
            rank[rowid]=rank.get(rowid,0)+1/(16+position)
    output=[]
    seen=set()
    for rowid in sorted(rank,key=rank.get,reverse=True):
        row=db.execute('SELECT * FROM alinti WHERE rowid=?',(rowid,)).fetchone()
        if row[4] in seen:
            continue
        seen.add(row[4])
        ref,name,digest,location,quote,url,category,when=row
        output.append(dict(ikn=ref,dosya=name,sha256=digest,satir=location,alinti=quote,url=url,
                           kategori=json.loads(category),tarih=when,yontem='FTS5 + embedding' if vectors else 'FTS5'))
        if len(output)==SETTINGS['retrieval_k']:
            break
    return output


def ara(query,ikn=''):
    location=path()
    location.parent.mkdir(parents=True,exist_ok=True)
    with closing(sqlite3.connect(location,timeout=15)) as db:
        initialize(db,rows_from_archive())
        return search(db,query,ikn)


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--embedding',action='store_true')
    cli.add_argument('--ikn',default='',help='Embedding hazırlığını bu İKN ile sınırlandırır.')
    options=cli.parse_args()
    location=path()
    location.parent.mkdir(parents=True,exist_ok=True)
    with closing(sqlite3.connect(location,timeout=15)) as db:
        version,count=initialize(db,rows_from_archive())
        result={'surum':version,'alinti':count}
        if options.embedding:
            result.update(prepare(db,ikn=options.ikn))
        print(json.dumps(result,ensure_ascii=False))
