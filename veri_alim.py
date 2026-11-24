"""Veri setini değiştirmeden profil ve onaya sunulan sözlük üretir."""
import csv
import hashlib
import io
import json
import sqlite3
import zipfile
from collections import Counter
from contextlib import closing
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree as ET

import openpyxl

ROOT = Path(__file__).resolve().parent
MADDE = {
    "ikn":"ikn", "ihale_adi":"ihale_adi", "idare":"idare", "ihale_tarihi":"ihale_tarihi",
    "kategori_tier":"kaynak_sinifi", "emsal_grubu":"kaynak_kategori", "urun_hizmet_tanimi":"kalem_adi",
    "miktar":"miktar", "birim":"birim", "sozlesme_bedeli_orijinal":"sozlesme_toplami",
    "yaklasik_maliyet_orijinal":"yaklasik_maliyet", "birim_fiyat_orijinal":"kaynak_birim_fiyat",
    "para_birimi":"para", "ekap_dogrulama_durumu":"kaynak_beyani"
}

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()

def save(path,data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')

def profile(values):
    valid=[v for v in values if v is not None and v!='']
    counts=Counter(valid)
    return dict(tur=sorted({type(v).__name__ for v in valid}),bos=len(values)-len(valid),
                bos_orani=(len(values)-len(valid))/len(values),benzersiz=len(counts),
                minimum=min(valid,default=None),maksimum=max(valid,default=None),
                sik=counts.most_common(5),ornek=list(counts)[:5])

def normalize(value,numeric):
    if value is None or value=='':return None
    if numeric:return Decimal(str(value))
    return str(value)

def compare(rows,reference):
    seen=set()
    fark=Counter()
    unknown=0
    duplicates=0
    for row in rows:
        key=row['ikn']
        duplicates+=key in seen
        seen.add(key)
        if key not in reference:
            unknown+=1
            continue
        for col,v in reference[key].items():
            x=row[col]
            if normalize(x,isinstance(v,(float,int)))!=normalize(v,isinstance(v,(float,int))):
                fark[col]+=1
    return dict(tekrar=duplicates,fazla=unknown,eksik=len(reference.keys()-seen),hucre_farki=dict(fark))

def incele(folder):
    files=sorted(p for p in folder.iterdir() if p.is_file())
    js,=folder.glob('*.json')
    cs,=folder.glob('*.csv')
    sq,=folder.glob('*.sqlite')
    rows=json.loads(js.read_text(encoding='utf-8-sig'))
    ref={r['ikn']:r for r in rows}
    if len(rows)!=len(ref):raise ValueError('JSON içinde yinelenen İKN')
    directory=ROOT/'data/alim'/sha(js)[:8]
    directory.mkdir(parents=True,exist_ok=True)
    cols=list(rows[0])
    raw=cs.read_bytes()
    txt=raw.decode('utf-8-sig')
    sep=csv.Sniffer().sniff(txt[:8192],delimiters=',;\t|').delimiter
    reader=csv.DictReader(io.StringIO(txt),delimiter=sep)
    csvrows=list(reader)
    report=dict(dosyalar=[dict(ad=p.name,bayt=p.stat().st_size,sha256=sha(p),bicim=p.suffix) for p in files],
                json_satir=len(rows),sutunlar={c:profile([r[c] for r in rows]) for c in cols},
                csv=dict(ayrac=sep,kodlama='utf-8-sig' if raw.startswith(bytes.fromhex('efbbbf')) else 'utf-8',
                         bozuk_karakter=txt.count('\ufffd'),baslik_satiri=1,bos_satir=sum(not any(r) for r in csv.reader(io.StringIO(txt),delimiter=sep)),
                         yinelenen_baslik=sum(list(r.values())==cols for r in csvrows),karsilastirma=compare(csvrows,ref)),
                json_bos_satir=sum(not any(r.values()) for r in rows),xlsx={})
    with closing(sqlite3.connect(sq.as_uri()+'?mode=ro',uri=True)) as db:
        db.row_factory=sqlite3.Row
        report['sqlite']=compare(db.execute('SELECT * FROM emsaller_tam_200'),ref)
        report['detay_ile_ortusen']=len({r[0] for r in db.execute('select ikn from emsaller')}&ref.keys())
    with closing(sqlite3.connect((ROOT/'data/havuz.db').as_uri()+'?mode=ro',uri=True)) as db:
        report['havuz_ile_ortusen']=len({r[0] for r in db.execute('select ikn from kayit')}&ref.keys())
    for path in folder.glob('*.xlsx'):
        with closing(openpyxl.load_workbook(path,read_only=True,data_only=False)) as book, zipfile.ZipFile(path) as z:
            sheets={}
            for idx,s in enumerate(book,1):
                xml=ET.fromstring(z.read(f'xl/worksheets/sheet{idx}.xml'))
                sheets[s.title]=dict(durum=s.sheet_state,formul=len(xml.findall('.//{*}f')),birlesik=len(xml.findall('.//{*}mergeCell')),
                                     gizli_sutun=[c.attrib for c in xml.findall('.//{*}col') if c.get('hidden')=='1'])
                it=iter(s.values)
                header=next(it)
                if list(header)==cols:
                    data=[dict(zip(header,row)) for row in it if any(v is not None for v in row)]
                    sheets[s.title]['satir']=len(data)
                    if len(data)==len(rows):sheets[s.title]['karsilastirma']=compare(data,ref)
            report['xlsx'][path.name]=sheets
    save(directory/'profil.json',report)
    sozluk={c:dict(hedef=MADDE.get(c,'kaynak_hesap.'+c),kanit=dict(sutun=c,ornek=report['sutunlar'][c]['ornek'][:3])) for c in cols}
    save(directory/'veri_sozlugu.onay.json',dict(durum='onay_bekliyor',dosya_sha256=sha(js),alanlar=sozluk,
         eksik=['bilgi_tarihi','kdv_esasi','kaynak_url','yüklenici'],notlar=['Sözleşme toplamı ve yaklaşık maliyet ayrı gözlemlerdir.','Güncellenmiş tutarlar ve kaynak beyanı bağımsız doğrulama sayılmaz.']))
    return directory,report
