"""Bağımsız EKAP sonuç ve kurul kararı kanıtlarını normalleştirir."""
from datetime import date
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parent
TUTAR=r'((?:[0-9]{1,3}(?:\.[0-9]{3})+|[0-9]+),[0-9]{2})\s+(TRY|EUR|USD|GBP)'
TARIH=r'(?<!\d)(\d{2})\.(\d{2})\.(20\d{2})(?!\d)'
KIMLIK=r'20\d{2}/[1-9]\d{0,8}'
KARAR='/ekap/vatandas/kurulkarargoster.aspx'
OZET='/ekap/ortak/birbakistaihale.aspx'


def ozet_hash(value):
    return sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()


def tarih(text):
    match=re.search(TARIH,text)
    if match:
        day,month,year=map(int,match.groups())
        return date(year,month,day).isoformat()
    return None


def deger(lines,prefix):
    raw=next((r['metin'] for r in lines if r['metin'].startswith(prefix)),None)
    return raw[len(prefix):].strip(' |') if raw else ''


def sozlesmeler(lines):
    contracts=[]
    current=None
    labels={'İlk Sözleşme Bilgileri':'sozlesme', 'Yaklaşık Maliyet':'yaklasik',
            'En Düşük Teklif':'dusuk_teklif','En Yüksek Teklif':'yuksek_teklif'}
    for row in lines:
        line=row['metin']
        for label,kind in labels.items():
            m=re.fullmatch(re.escape(label)+r'\s*\|?\s*'+TUTAR,line)
            if m:
                amount,unit=m.groups()
                value=dict(fiyat=str(Decimal(amount.replace('.','').replace(',','.'))),para=unit,konum='Web metni '+str(row['satir']))
                if kind=='sozlesme':
                    current={**value,'tarih':None,'kdv':None,'yuklenici':None,'diger_fiyatlar':{}}
                    contracts.append(current)
                elif current is not None:
                    current['diger_fiyatlar'][kind]=value
        if current is not None and line.startswith('Sözleşme Tarihi'):
            current['tarih']=tarih(line)
    return contracts


def sayfayi_oku(capture):
    """Bir alanın varlığı eşleşen sayfa satırlarından karar verilir."""
    from ekap_veri import official
    url=capture['url']
    path=urlsplit(url).path.lower()
    if not official(url) or path not in (KARAR,OZET):
        raise ValueError('EKAP asıl kaynak adresi gerekli.')
    lines=capture['satirlar']
    ikn=capture['ikn']
    if not re.fullmatch(KIMLIK,ikn):
        raise ValueError('İKN biçimi geçersiz. Başka kayıt türleri ayrı kuyrukta saklanır.')
    ikn_match=lambda s: bool(re.search(r'(?<![\d/])'+re.escape(ikn)+r'(?!\d)',s))
    kind=capture['tur']
    category=capture['kategori']
    catalog=json.loads((ROOT/'catalog.json').read_text(encoding='utf-8-sig'))
    if len(category)!=2 or category[1] not in catalog['turler'].get(kind,{}).get(category[0],{}):
        raise ValueError('Kanıt kategorisi katalogda yok.')
    source_pos=None
    if path==KARAR:
        identity=next((r for r in lines if 'İHALE' in r['metin'] and ikn_match(r['metin'])),None)
        if not identity:
            raise ValueError('Karar metninde İKN bulunamadı.')
        name=capture['ad']
        if name.casefold() not in identity['metin'].casefold():
            raise ValueError('Karar metninde ihale adı eşleşmedi.')
        bid_date=tarih(identity['metin'])
        contracts=[]
        source_pos=identity['satir']
        status='KİK kurul kararı'
        reason='Kurul kararı ihale alanlarını destekliyor. Nihai sözleşme bedeli bu kaynakla teyit edilemedi.'
        canonical_quantity=None
    else:
        identity=deger(lines,'İhale Kayıt No')
        if not ikn_match(identity):
            raise ValueError('Sayfanın ihale kimliği uyuşmadı.')
        if deger(lines,'İhale Türü - Usulü').split(' - ')[0]!=kind:
            raise ValueError('Sayfanın ihale türü uyuşmadı.')
        name=deger(lines,'İhale Adı')
        if not name:
            raise ValueError('Sayfada ihale adı yok.')
        source_pos=next(r['satir'] for r in lines if r['metin'].startswith('İhale Adı'))
        status=deger(lines,'İhale Durumu')
        bid_date=tarih(deger(lines,'İhale Yeri - Tarihi - Saati'))
        contracts=sozlesmeler(lines)
        reason=''
        canonical_quantity=None
    mixed=bool(capture.get('karma')) or len(contracts)>1 or bool(re.search(r'(?<!\d)[2-9]\d*',deger(lines,'Kısım Sayısı')))
    spec={}
    item=None
    if path==OZET and not mixed:
        measure=re.match(r'([0-9][0-9.]*)\s+(paket|top|adet|koli)\b',name,re.I)
        if measure:
            canonical_quantity=int(measure[1].replace('.',''))
            unit=measure[2].lower()
            item=dict(kalem_id='1',ad=name,miktar=canonical_quantity,birim=unit,alinti=[name],
                      satir_baslangic=source_pos,satir_bitis=source_pos,kapsam='EKAP ihale başlığında istenen miktar')
        if re.search(r'\bA4\b',name,re.I):
            spec['Boyut']='A4'
        if m:=re.search(r'\b([0-9]+)\s*(?:gram|g/m²|gr\b)',name,re.I):
            spec['Gramaj (g/m²)']=int(m[1])
        if m:=re.search(r'\b1\s+pakette\s+([0-9]+)\s+adet\b',name,re.I):
            spec['Paketteki yaprak sayısı']=int(m[1])
        if m:=re.search(r'\b1\s+kolide\s+([0-9]+)\s+paket\b',name,re.I):
            spec['Kolideki paket sayısı']=int(m[1])
    elif path==KARAR:
        # Alıntılı idari şartname miktarı teknik bağlamdır.
        for row in lines:
            m=re.search(r'Miktarı:\s*([0-9][0-9.]*)\s+(paket|adet|koli)\b',row['metin'],re.I)
            if m:
                item=dict(kalem_id='1',ad=name,miktar=int(m[1].replace('.','')),birim=m[2].lower(),
                          alinti=[m[0]],satir_baslangic=row['satir'],satir_bitis=row['satir'],
                          kapsam='Kurul kararında aktarılan ihale miktarı')
                break
    cancelled='iptal' in status.casefold()
    result=contracts[0] if len(contracts)==1 and contracts[0]['tarih'] and not cancelled else None
    single_sales=bool(canonical_quantity and result and deger(lines,'Kısmi Teklif')=='Verilemez' and
                      status=='Sonuç İlanı Yayımlanmış' and not mixed)
    if cancelled:
        reason='EKAP ihalesi iptal edilmiş. Fiyat hesabında kullanılmaz.'
    elif mixed:
        reason='Karma veya çok kısımlı toplam. Kesin kalem fiyatı ayrıştırılamadı.'
    elif result and not single_sales:
        reason='Sözleşme bedeli var. Aynı kapsamda sonuç bedeli ve tek kalem miktarı birlikte doğrulanamadı.'
    elif single_sales:
        reason='EKAP toplamı ve ihale başlığı miktarı aynı tek kalem kapsamında. Sözleşme bedelinin KDV esası belirsiz.'
    elif not reason:
        reason='Belge ihale bağlamını destekliyor. Tarihli sözleşme bedeli bulunamadı.'
    return dict(ikn=ikn,kategori=category,tur=kind,ad=name,teknik=spec,
                teknik_durum='URUN_DOGRULANDI' if {'Boyut','Gramaj (g/m²)','Paketteki yaprak sayısı'}<=spec.keys() else 'KOSULLU',
                ihale_tarihi=bid_date,sonuc=result,sozlesmeler=contracts,belgeler=[],teklif_cetveli=item,
                ihale_durumu=status,karma=mixed,iptal=cancelled,rapor_siniri=reason,
                tek_kalem_bolumu=single_sales,kaynak_url=url,web_kaniti=capture,
                okas=re.findall(r'\b\d{8}\b',deger(lines,'İhale Branş Kodları (OKAS)')))


def oku(directory):
    path=directory/'sayfa_kanitlari.json'
    if not path.is_file():
        return {}
    payload=json.loads(path.read_text(encoding='utf-8-sig'))
    records={}
    for capture in payload['kanitlar']:
        proof=sayfayi_oku(capture)
        records[proof['ikn']]=proof
    return records


def ice_aktar(captures,path):
    """Aynı içerik tekrar geldiğinde dosyayı bile değiştirmez. Önceki kanıt sürümü kalır."""
    data=json.loads(path.read_text(encoding='utf-8-sig')) if path.is_file() else {'kanitlar':[]}
    seen={ozet_hash(row) for row in data['kanitlar']}
    added=0
    for capture in captures:
        sayfayi_oku(capture)
        digest=ozet_hash(capture)
        if digest not in seen:
            data['kanitlar'].append(capture)
            seen.add(digest)
            added+=1
    if added:
        tmp=path.with_suffix('.tmp')
        tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        tmp.replace(path)
    return added
