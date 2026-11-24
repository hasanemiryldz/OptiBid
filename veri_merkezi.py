"""Yerel kaynaklardan tüm kimlikleri, çatışmaları koruyarak arar."""
from collections import Counter
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import unicodedata
from urllib.parse import urlsplit
import emsal
from veri_yollari import DATA, HOME

ROOT=Path(__file__).resolve().parent

def oku(path):
    return sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)

def norm(text):
    return unicodedata.normalize('NFKC',text.replace('İ','i').replace('I','ı')).casefold()

def harici_url(value):
    from ekap_veri import official
    try:
        url=urlsplit(str(value or ''))
        return url.scheme in ('http','https') and bool(url.hostname) and not official(value)
    except ValueError:
        return False


def kayitlar():
    rows={}
    def ekle(ikn,category,title,origin,state,path,location):
        ikn=str(ikn).strip()
        item=rows.setdefault(ikn,dict(ikn=ikn,kategoriler=[],adlar=[],kaynaklar=[],durumlar=[],ham_satir=0,kokenler=[]))
        item['kokenler'].append(dict(kaynak=origin,dosya=str(path.relative_to(ROOT.parent)) if path.is_relative_to(ROOT.parent) else path.name,
                                     konum=location,kategori=category,ad=title,durum=state))
        item['ham_satir']+=1
        for field,value in [('kategoriler',category),('adlar',title),('kaynaklar',origin),('durumlar',state)]:
            if value and value not in item[field]:item[field].append(value)
    _, archived=emsal._read_archive(None)
    for ikn,row in archived.items():
        category=row['kategori'][-1] if row['kategori'] else 'Sınıflanmadı'
        ekle(ikn,category,None,'Arşiv',row['kalite'],emsal.ARCHIVE,'ihaleler:'+ikn)
    sources=ROOT/'kaynaklar.json'
    for pos,r in enumerate(json.loads(sources.read_text(encoding='utf-8-sig'))):
        ekle(r['ikn'],r.get('kategori'),None,'Kaynak listesi',None,sources,'/'+str(pos))
        if harici_url(r.get('url')):
            rows[str(r['ikn']).strip()]['harici']=True
    if emsal.POOL.is_file():
        with closing(oku(emsal.POOL)) as db:
            tables={v for v, in db.execute("select name from sqlite_master where type='table'")}
            if 'kayit' in tables:
                for pos,i,c,s in db.execute('select rowid,ikn,kategori,kalite from kayit order by rowid'):
                    ekle(i,c,None,'Yerel havuz',s,emsal.POOL,'kayit:rowid='+str(pos))
            if 'ekap_dosya_kaydi' in tables:
                for pos,i,c,raw in db.execute('select rowid,ikn,kategori,ham from ekap_dosya_kaydi order by rowid'):
                    r=json.loads(raw)
                    ekle(i,c,r.get('urun') or r.get('ihale_adi'),'EKAP dosya aktarımı','Alan incelemesi',emsal.POOL,'ekap_dosya_kaydi:rowid='+str(pos))
            if 'kullanici_emsalleri' in tables:
                for pos,s in db.execute('select rowid,veri from kullanici_emsalleri order by rowid'):
                    r=json.loads(s)
                    ekle(r['ikn'],' / '.join(r['kategori']),None,'Eklenen emsal',r['kalite'],emsal.POOL,'kullanici_emsalleri:rowid='+str(pos))
                    if harici_url(r.get('kaynak')):rows[str(r['ikn']).strip()]['harici']=True
    for path in sorted((DATA/'alim').glob('*/alim.sqlite')):
        with closing(oku(path)) as db:
            for i,s,state in db.execute('select ikn,alanlar_json,dogrulama_durumu from standart_kayit'):
                r=json.loads(s);ekle(i,r.get('kaynak_kategori'),r.get('ihale_adi'),'Veri seti',state,path,'standart_kayit:'+i)
    expanded=HOME/'OptiBid_Emsal_Tam_Veri_genisletilmis.json'
    if expanded.is_file():
        for pos,r in enumerate(json.loads(expanded.read_text(encoding='utf-8-sig'))):
            if not (ref:=r.get('_kaynak')):
                continue
            ikn=str(r['ikn']).strip()
            ekle(ikn,ref.get('ihale_usulu'),r['ihale_adi'],'İETT resmî ilanı','İlan bilgisi',expanded,'/'+str(pos))
            rows[ikn]['harici']=True
            rows[ikn]['ilan_url']=ref['kaynak']
    return rows

def ara(query='',offset=0,durum='ekap'):
    from ekap_veri import snapshot,CONFIRMED,EXTERNAL,PENDING
    filters={'ekap':CONFIRMED,'bekliyor':PENDING,'karantina':EXTERNAL,'tumu':None}
    status=filters[durum]
    rows,_,meta=snapshot()
    terms=norm(query).split()
    matches=[]
    for row in rows:
        if status and row['origin_status']!=status or durum=='tumu' and row['origin_status']==EXTERNAL:
            continue
        proof=row['ekap_referans']
        names=[proof['ad']] if proof else row['adlar']
        categories=proof['kategori'] if proof else row['kategoriler']
        corpus=norm(' '.join([row['ikn'],*names,*categories]))
        if all(t in corpus for t in terms):
            matches.append(dict(ikn=row['ikn'],adlar=names,kategoriler=categories,durumlar=[row['origin_status']],
                                neden=row['neden'],ilan_url='/api/ekap-dayanagi/'+row['ikn'] if proof else None))
    return dict(meta,toplam=len(matches),baslangic=offset,satirlar=matches[offset:offset+25])

