"""EKAP kaynak kapısı. Kaynak kökeni, alan ve fiyat uygunluğu ayrı tutulur."""
from collections import Counter
from contextlib import closing
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import sqlite3
from statistics import median
from urllib.parse import urlsplit
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

ROOT=Path(__file__).resolve().parent
from veri_yollari import DATA as PROJECT_DATA
DATA=PROJECT_DATA/'ekap'
POLICY='EKAP_ONLY'
CONFIRMED='EKAP_DOĞRULANDI'
PENDING='EKAP_DOĞRULAMA_BEKLİYOR'
EXTERNAL='HARİCİ_KARANTİNA'
TARGET=300
CALC_VERSION='v20-m3-kalem-ajan'
IKN=re.compile(r'20\d{2}/[1-9]\d{0,8}')


def cetvel_kalemi(name,lines,amount,unit):
    """Boş teklif cetvelinin tek satırını belgeler. Kazananın cetveli sayılmaz."""
    import unicodedata
    if 'Birim_Fiyat_Teklif_Cetveli' not in name:
        return None
    lines=[unicodedata.normalize('NFKC',s) for s in lines]
    headers=[i for i,s in enumerate(lines) if re.match(r'^Tutar[ıi](?:\s|$)',s,re.I)]
    footers=[i for i,s in enumerate(lines) if re.match(r'^toplam tutar\s*\(',s,re.I)]
    if len(headers)!=1 or len(footers)!=1:
        return None
    start,end=headers[0]+1,footers[0]
    cells=lines[start:end]
    if len(cells)!=4 or cells[0]!='1' or cells[2]!=unit:
        return None
    if not re.fullmatch(r'(?:[1-9]\d{0,2}(?:\.\d{3})+|[1-9]\d*)',cells[3]):
        return None
    if int(cells[3].replace('.',''))!=amount:
        return None
    return dict(kalem_id='1',ad=cells[1],birim=unit,miktar=amount,dosya=name,
                satir_baslangic=start+1,satir_bitis=end,alinti=lines[start:end],
                kapsam='İhale teklif cetvelindeki istenen miktar')

def paket_cetvelleri(record,archived):
    """İKN alanı boş cetveli, doğrulanmış dış ZIP ve özgün DOCX ile bağlar."""
    key=record['ikn']
    name='ihale_dokumani_'+key.replace('/','_')+'.zip'
    meta=record.get('zip') or {}
    if Path(meta.get('dosya','')).name!=name:
        return []
    path=DATA/'belge_paketleri'/name
    if not path.is_file():
        return []
    raw=path.read_bytes()
    if sha256(raw).hexdigest()!=meta.get('sha256'):
        return []
    verified=[]
    namespace='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    with ZipFile(BytesIO(raw)) as outer:
        for fullname,(digest,text_digest,lines) in archived.items():
            outer_name,_,member=fullname.partition('!')
            if ('Birim_Fiyat_Teklif_Cetveli' not in member or not member.endswith('.docx') or
                    key.replace('/','-') not in member or outer_name not in outer.namelist()):
                continue
            try:
                with ZipFile(BytesIO(outer.read(outer_name))) as inner:
                    docx=inner.read(member)
                if sha256(docx).hexdigest()!=digest:
                    continue
                with ZipFile(BytesIO(docx)) as word:
                    xml=ElementTree.fromstring(word.read('word/document.xml'))
            except (KeyError,BadZipFile,ElementTree.ParseError):
                continue
            content=[''.join(t.text or '' for t in p.iter(namespace+'t')).strip() for p in xml.iter(namespace+'p')]
            if list(filter(None,content))==lines:
                verified.append(dict(dosya=fullname,sha256=digest,metin_sha256=text_digest,paket_sha256=meta['sha256'],
                                     bag='Aynı İKN’ye ait özgün EKAP ZIP paketi'))
    return verified


def official(url):
    try:
        u=urlsplit(str(url or ''))
        return (u.scheme=='https' and u.hostname in {'ekap.kik.gov.tr','ekapv2.kik.gov.tr'} and
                u.port in (None,443) and not u.username and not u.password)
    except ValueError:
        return False

def verified():
    import emsal
    manifest=DATA/'gozlemler.json'
    manifests=[manifest] if manifest.is_file() else []
    manifests.extend(sorted((DATA/'incelenen_yeni_sonuclar').glob('*.json')))
    from ekap_sayfalari import oku as sayfa_kanitlari
    pages=sayfa_kanitlari(DATA)
    if not manifests or not emsal.ARCHIVE.is_file():
        return pages
    docs={}
    items={}
    with closing(sqlite3.connect(emsal.ARCHIVE.as_uri()+'?mode=ro',uri=True)) as db:
        for key,amount,unit in db.execute('SELECT ikn,miktar,birim FROM ihaleler'):
            items[key]=(amount,unit)
        for i,name,digest,text in db.execute('SELECT ikn,dosya,sha256,metin FROM belgeler'):
            docs[i,name]=(digest,sha256(text.encode()).hexdigest(),text.splitlines())
    result={}
    records=(record for path in manifests for record in json.loads(path.read_text(encoding='utf-8-sig')))
    for record in records:
        key=record['ikn']
        name=key.replace('/','_')+'.png'
        if key in result:
            continue
        if not IKN.fullmatch(key) or record['sonuc']['dosya']!=name:continue
        image=DATA/'sonuclar'/name
        if not image.is_file() or sha256(image.read_bytes()).hexdigest()!=record['sonuc']['sha256']:continue
        accepted=[]
        for doc in record['belgeler']:
            original=docs.get((key,doc['dosya']))
            pos=doc['ikn_satir']-1
            if (original and (doc['sha256'],doc['metin_sha256'])==original[:2] and
                0<=pos<len(original[2]) and key in original[2][pos]):
                accepted.append(doc)
        if accepted:
            matched={d['dosya'] for d in accepted}
            candidates={name:original for (ikn,name),original in docs.items() if ikn==key and name not in matched}
            accepted.extend(paket_cetvelleri(record,candidates))
            admitted=None
            signed=record.get('bedel_dayanagi')
            if isinstance(signed,dict):
                doc=next((d for d in accepted if d['dosya']==signed.get('dosya')),None)
                if doc:
                    lines=docs[key,doc['dosya']][2]
                    start=signed.get('satir',0)-1
                    excerpt=signed.get('alinti','')
                    if 0<=start<len(lines) and excerpt==lines[start] and any('sonuç ilanı' in x.casefold() for x in lines[:10]):
                        admitted=signed
            item_proofs={}
            if key in items:
                for doc in accepted:
                    if item:=cetvel_kalemi(doc['dosya'],docs[key,doc['dosya']][2],*items[key]):
                        item_proofs[doc['dosya']]={**item,'belge_sha256':doc['sha256'],
                                                  'paket_sha256':doc.get('paket_sha256')}
            result[key]={**record,'belgeler':accepted,'bedel_dayanagi':admitted,
                         'teklif_cetveli':next(iter(item_proofs.values())) if len(item_proofs)==1 else None}
    for key,page in pages.items():
        if key not in result:
            result[key]=page
        else:
            result[key]['web_kaniti']=page['web_kaniti']
            result[key]['kaynak_url']=page['kaynak_url']
    # Arşivdeki ürün çıkarımını kökeniyle taşı; tek başına imzalı ürün
    # teyidi veya KDV dayanağı olarak kullanma. Önceki sürüm bu alanları
    # rapora hiç aktarmadığı için fiyat katmanı teknik profili göremiyordu.
    with closing(sqlite3.connect(emsal.ARCHIVE.as_uri()+'?mode=ro',uri=True)) as db:
        for key,raw in db.execute('SELECT ikn,teknik_json FROM ihaleler'):
            if key not in result or result[key].get('web_kaniti') and result[key].get('teknik'):
                continue
            t=json.loads(raw or '{}')
            result[key]['teknik']={'Boyut':'A4' if t.get('boyut_mm')==[210,297] else None,
                'Gramaj (g/m²)':t.get('gramaj_g_m2'),'Paketteki yaprak sayısı':t.get('pakette_yaprak'),
                'Kolideki paket sayısı':t.get('kolide_paket')}
            result[key]['teknik_kaynagi']='Yerel EKAP belge arşivindeki ürün çıkarımı; imzalanan ürünün bağımsız teyidi değildir.'
    return result

def snapshot():
    from veri_merkezi import kayitlar
    all_rows=kayitlar()
    good=verified()
    for key,proof in good.items():
        if key not in all_rows:
            all_rows[key]=dict(ikn=key,kategoriler=list(proof['kategori']),adlar=[proof['ad']],kaynaklar=[],
                               durumlar=[],ham_satir=0,kokenler=[])
        row=all_rows[key]
        if proof.get('web_kaniti'):
            row['ham_satir']+=1
            row['kaynaklar'].append('EKAP asıl sayfası')
            row['kokenler'].append(dict(kaynak='EKAP asıl sayfası',dosya='data/ekap/sayfa_kanitlari.json',
                                        konum=key,url=proof['kaynak_url']))
        elif not row['ham_satir']:
            row['ham_satir']=1
            row['kaynaklar'].append('EKAP kanıtı')
            row['kokenler'].append(dict(kaynak='EKAP kanıtı',dosya=proof['sonuc']['dosya'],konum=proof['sonuc']['konum']))
    rows=[]
    for key,r in sorted(all_rows.items()):
        proof=good.get(key)
        labels=set(r['kaynaklar'])
        status=CONFIRMED if proof else EXTERNAL if r.get('harici') and not labels.intersection({'Veri seti','EKAP dosya aktarımı'}) else PENDING
        if proof and proof.get('rapor_siniri'):
            state=proof['rapor_siniri']
        elif proof:
            state=('Bedel ve imza tarihi EKAP sonucunda eşleşti. Gerçek sözleşmenin KDV esası ve '
                   'imzalanan kalem miktarı kanıtlanmadı.' if not proof.get('bedel_dayanagi') else
                   'Bedel dayanağı bulundu. Teknik ve ticari eşleşme analizde sınanır.')
        elif not IKN.fullmatch(key):
            state='Kaynak kimliği EKAP İKN biçiminde değil. Doğrulanabilir İKN veya özgün belge gerekli.'
        elif status==EXTERNAL:
            state='Yerel EKAP kanıtlarıyla eşleşmedi. Haricî kaynak ham arşivde saklanıyor.'
        else:
            state='Yerel EKAP kanıtlarında bu İKN için özgün sonuç ve alan bağlantısı bulunamadı.'
        rows.append({**r,'origin_status':status,'field_evidence_status':'KISMİ' if proof else 'EKSİK',
                     'price_eligibility':'NOMİNAL_GÖZLEM' if proof and proof.get('sonuc') else 'KAPALI','neden':state,
                     'dogrulama':dict(yontem='EKAP asıl sayfasının alan bazlı denetimi' if proof and proof.get('web_kaniti') else
                                             'Yerel özgün EKAP sonuç ve belge arşiviyle tam İKN taraması',
                                      sonuc='eşleşti' if proof else 'kanıt eksik',
                                      uzaktan_dogrulandi=bool(proof and proof.get('web_kaniti'))),
                     'ekap_referans':proof})
    counts=Counter(r['origin_status'] for r in rows)
    from dosya_fiyatlari import kaynaklar
    file_prices,_=kaynaklar()
    file_rules=json.loads((ROOT/'dosya_fiyat_kategorileri.json').read_text(encoding='utf-8'))
    version=sha256(json.dumps([CALC_VERSION,rows,file_prices,file_rules],sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:16]
    return rows,good,dict(source_policy=POLICY,surum=version,ham=sum(r['ham_satir'] for r in rows),
        benzersiz=len(rows),ekap=counts[CONFIRMED],bekliyor=counts[PENDING],karantina=counts[EXTERNAL],
        hedef=TARGET,hedef_acigi=max(0,TARGET-counts[CONFIRMED]),
        fiyat_gozlemi=sum(len(r['sozlesmeler']) if 'sozlesmeler' in r else int(bool(r.get('sonuc'))) for r in good.values()),
        fiyatsiz_ilan=sum(not r.get('sonuc') and not r.get('sozlesmeler') for r in good.values()),
        web_kaniti=sum(bool(r.get('web_kaniti')) for r in good.values()),
        benzersiz_ikn=sum(bool(IKN.fullmatch(r['ikn'])) for r in rows),
        cetvel_kalemi=sum(bool(r.get('teklif_cetveli')) for r in good.values()),katilim=None,
        belge=sum(len(r['belgeler'])+bool(r.get('web_kaniti')) for r in good.values()),teknik_80=sum(r['teknik_durum']=='URUN_DOGRULANDI' for r in good.values()))

def nominal(good,doc):
    target=doc.get('ek_bilgiler',{}).get('ikn')
    return [dict(ikn=key,fiyat=r['sonuc']['fiyat'],tarih=r['sonuc']['tarih'],para=r['sonuc']['para'],
            kdv=None,kaynak='/api/ekap-dayanagi/'+key,ekap_arama='https://ekapv2.kik.gov.tr/ekap/search',
            konum=r['sonuc']['konum'],kaynak_url=r.get('kaynak_url'),
            kaynak_turu='EKAP asıl sayfası' if r.get('kaynak_url') else 'EKAP sonuç görüntüsü',
            alan='Sözleşme bedeli',fiyat_turu='sözleşme toplamı',fiyat_olayi='sözleşme imzası',ulke='TR',
            firma=r['sonuc']['yuklenici'],ad=r['ad'],
            teklif_cetveli=r.get('teklif_cetveli'),teknik_durum=r['teknik_durum'],
            kalem_bolum=r.get('tek_kalem_bolumu',False),karma=r.get('karma',False),teknik=r.get('teknik',{}),
            miktar_esasi='AYNI_KAYNAKTA_TEK_KALEM' if r.get('tek_kalem_bolumu') else 'IHALE_CETVELI_KOSULLU',
            fiyat_kaniti=r.get('sonuc'),teknik_kaynagi=r.get('teknik_kaynagi'))
            for key,r in sorted(good.items()) if key!=target and r.get('sonuc') and
            r['kategori']==doc['kategori'] and r['tur']==doc['ihale_turu'] and not r.get('iptal')]

def coklu_sozlesmeler(good,doc):
    """Aynı İKN içindeki özgün sözleşme satırlarını fiyat istatistiğine katmadan koru."""
    extra=doc.get('ek_bilgiler',{})
    return [dict(ikn=key,sira=n,tutar=s['fiyat'],para=s['para'],tarih=s.get('tarih'),konum=s.get('konum'),
                 url=p.get('kaynak_url'),kdv=s.get('kdv'))
            for key,p in sorted(good.items())
            if len(p.get('sozlesmeler') or [])>1 and key!=extra.get('ikn') and not p.get('iptal')
            and p['tur']==doc['ihale_turu'] and p['kategori']==doc['kategori']
            for n,s in enumerate(p['sozlesmeler'],1)]

def fiyat_adayi(record,rule,extra):
    """Aynı sonuç satırında bedeli ve fiyat esasını bağlayabilen tek kalemi alır."""
    from emsal import number
    source=record.get('bedel_dayanagi')
    if not source:return None
    end=record['sonuc']
    vat=extra.get('kdv_esasi')
    if vat not in ('hariç','dahil'):
        return None
    if end['para']!='TRY' or extra.get('para_birimi','TRY')!='TRY' or extra.get('ulke','TR')!='TR':return None
    line=source['alinti'].strip().casefold()
    numeral=r'(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?'
    price_unit=re.escape(end['para'].casefold())
    measure=re.escape(rule['birim'].casefold())
    match=re.fullmatch(rf'sözleşme bedeli ({numeral}) {price_unit}, tek kalem ({numeral}) {measure} ([^,]+), kdv {vat}\.?',line)
    if not match or re.search(r'\b(?:değil\w*|haricinde|dışında|hariç|dahil|veya|muadil)\b',match[3]):
        return None
    price=number(end['fiyat'])
    amount=number(source.get('miktar'))
    if not price or not amount or source.get('birim')!=rule['birim']:return None
    observed=tuple(Decimal(token.replace('.','').replace(',','.')) for token in match.group(1,2))
    if observed!=(price,amount):return None
    technical=source.get('teknik',{})
    evidenced={}
    for key in rule['hedef']:
        value=technical.get(key)
        terms=source.get('teknik_alinti',{}).get(key,'').casefold()
        if value is not None and terms and terms in match[3] and str(value).casefold() in terms:
            evidenced[key]=value
    return dict(teknik=evidenced,ikn=record['ikn'],tarih=end['tarih'],birim=rule['birim'],fiyat=str(price),miktar=str(amount),
                fiyat_turu='sözleşme toplamı',kdv=vat,ham_birim=str(round(price/amount,2)),
                kaynak='/api/ekap-dayanagi/'+record['ikn'],dayanak=source,kademe=record.get('kademe','SINIFLANDIRILMAMIŞ'))

def degerlendir(doc,rule,rows,good,meta):
    from emsal import equal
    from hesap_araclari import birim_donustur, sayi
    from tuik_endeks import seriler,endeksle
    from tuik_endeks import kategori_serisi
    from urun_ayarlari import oku as urun_ayari, endeks_yasi
    from fiyat_referansi import dagilim
    from gozlenen_fiyatlar import kdv_senaryolari
    ayar = urun_ayari()
    ufuk = ayar['endeks_ufku_ay']
    series=seriler()
    code=kategori_serisi(doc['ihale_turu'],doc['kategori']) or (rule.get('endeks') if rule else None)
    index=series.get(code)
    extra=doc.get('ek_bilgiler',{})
    target=extra.get('emsal_donemi') or (index['son_ay'] if index else None)
    nominal_rows=nominal(good,doc)
    result=dict(source_policy=POLICY,tender_source_policy=POLICY,index_source_policy='TUIK_OFFICIAL',
                veri_surumu=meta['surum'],havuz_kapsami=meta,emsaller=[],emsal_ayrinti=[],haric=[],
                dislanan=[],nominal=nominal_rows,ayri_sozlesmeler=coklu_sozlesmeler(good,doc),
                tier1_sayisi=0,kategori_adayi=0,endekslenen_nominal=0,
                degerlendirme_surumu=CALC_VERSION,gruplar=dict(A=[],B=[],C=[],D=[],E=[]),
                endeks={k:v for k,v in index.items() if k!='noktalar'} if index else None,
                endeks_ufku_ay=ufuk)
    for row in nominal_rows:
        row['ufuk'] = endeks_yasi(row['tarih'], target, ufuk)
        if row['kalem_bolum']:
            from hesap_araclari import sozlesme_birimine_bol
            item=row['teklif_cetveli']
            row['turetilmis_birim']=sozlesme_birimine_bol(row['fiyat'],item['miktar'],item['birim'])
        if row['karma']:
            row['endeks_eksik']='Karma toplam bu kategoriye ait tek ürün endeksiyle düzeltilmedi.'
            continue
        if not index or row['para']!='TRY':
            row['endeks_eksik']='Bu para birimi ve kategori için uyumlu endeks tanımlı değil.'
            continue
        try:
            row['endeks_iz']=endeksle(row['fiyat'],code,row['tarih'][:7],target,dataset=series)
        except ValueError as exc:
            row['endeks_eksik']=str(exc)
        else:
            result['endekslenen_nominal']+=1
            if row.get('turetilmis_birim'):
                trace=row['endeks_iz']
                rate=Decimal(trace['hedef_endeks'])/Decimal(trace['kaynak_endeks'])
                item=row['teklif_cetveli']
                row['endeksli_birim']=sozlesme_birimine_bol(str(Decimal(row['fiyat'])*rate),item['miktar'],item['birim'])
    if rule and len(doc['kalemler'])==1:
        item=doc['kalemler'][0]
        try:
            if item['birim']==rule['birim']:
                converted={'miktar':str(sayi(item.get('miktar'))),'birim':rule['birim']}
            else:
                converted=birim_donustur(item.get('miktar'),item['birim'],rule['birim'],item['teknik'].get(rule.get('carpan')))
        except ValueError:
            pass
        else:
            result.update(standart_miktar=converted['miktar'],birim=converted['birim'],kdv=extra.get('kdv_esasi') or 'belirsiz')
    reference=[]
    observations={r['ikn']:r for r in nominal_rows}
    for r in rows:
        if r.get('origin_status')==EXTERNAL:
            continue
        group=None
        match=None
        key=r['ikn']
        proof=good.get(key)
        category=bool(proof and proof['kategori']==doc['kategori'] and proof['tur']==doc['ihale_turu'])
        result['kategori_adayi']+=category
        if key==extra.get('ikn'):
            group='E' if proof else None
            reason='Hedef ihale kendi fiyat hesabından çıkarıldı.'
        elif not proof:
            reason=r['neden']
        elif not category:
            group='E'
            reason='Kategori veya alım türü farklı.'
        elif extra.get('rapor_haric') and key in extra['rapor_haric']:
            reason='Çalışmadan elle çıkarıldı.'
        elif proof.get('iptal') or proof.get('karma'):
            group='E'
            reason=proof['rapor_siniri']
        elif key not in observations or (proof.get('web_kaniti') and not proof.get('teklif_cetveli')):
            group='D'
            reason=proof.get('rapor_siniri') or 'Kategoride EKAP dayanağı var, karşılaştırılabilir sonuç fiyatı yok.'
        elif not (rule and len(doc['kalemler'])==1 and (match:=fiyat_adayi(proof,rule,extra))):
            group='C'
            reason=r['neden'] if not proof.get('bedel_dayanagi') else 'Para birimi, KDV esası veya imzalanan tek kalemin fiyatı karşılaştırılamadı.'
        elif any(k not in match['teknik'] or not equal(doc['kalemler'][0]['teknik'].get(k),v) for k,v in match['teknik'].items()) or set(match['teknik'])!=set(rule['hedef']):
            group='B'
            reason='İmzalanan kalemin belgelenmiş teknik özellikleri hedefle aynı kapsamda değil veya eksik.'
        elif not result.get('standart_miktar'):
            group='B'
            reason='Hedef ya da emsal miktarı karşılaştırma biriminde doğrulanamadı.'
        else:
            date_month=match['tarih'][:7]
            try:
                if not target:
                    raise ValueError('Ortak fiyat dönemi seçilmedi.')
                if date_month!=target:
                    match['endeks_iz']=endeksle(match['fiyat'],code,date_month,target,dataset=series)
                    levels=match['endeks_iz']
                    value=Decimal(match['fiyat'])*Decimal(levels['hedef_endeks'])/Decimal(levels['kaynak_endeks'])
                elif index:
                    match['endeks_iz']=endeksle(match['fiyat'],code,date_month,target,dataset=series)
                    value=Decimal(match['fiyat'])
                else:
                    value=Decimal(match['fiyat'])
            except ValueError:
                group='B'
                reason='Ortak dönem için uyumlu seride iki geçerli ay bulunamadı; özgün fiyat korundu.'
            else:
                match['islenmis_birim']=str(value/Decimal(match['miktar']))
                match['ufuk']=endeks_yasi(match['tarih'], target, ufuk)
                reference.append(match)
                result['gruplar']['A'].append(dict(ikn=key,neden='Teknik, birim, KDV ve ortak dönem eşleşti.'))
                continue
        detail=dict(ikn=key,neden=reason,grup=group or ('kapsam' if proof else 'kaynak'))
        if group:
            context={k:proof[k] for k in ('kaynak_url','ad','ihale_tarihi','ihale_durumu') if k in proof}
            result['gruplar'][group].append({**detail,**context,**({'fiyat_dayanagi':match} if match else {})})
        if key in observations:
            observations[key].update(grup=group,neden=reason)
        result['haric'].append([key,reason])
        result['dislanan'].append(detail)
    result.update(aday_sayisi=len(rows),durum='Yetersiz veri',
                  neden='Fiyat hesabı için bedeli, kalemi ve KDV esası birlikte doğrulanan EKAP emsali bulunamadı.',
                  yontem='EKAP_ONLY · tarihli nominal gözlem')
    for item in result['gruplar']['A']:
        observations[item['ikn']].update(grup='A',neden=item['neden'])
    result['asama_sayilari']={
        'tarihli_toplam':len(nominal_rows),
        'kaynakta_miktar_ve_bedel':sum(bool(r.get('teklif_cetveli')) for r in nominal_rows),
        'tek_kalem_birim_fiyati':sum(bool(r.get('kalem_bolum')) for r in nominal_rows),
        'endeksli_toplam':result['endekslenen_nominal']}
    eligible=[r for r in reference if r['ufuk'] and not r['ufuk']['disinda']]
    n=len(eligible)
    if reference:
        result['dogrudan_duyarlilik']=dagilim([Decimal(r['islenmis_birim']) for r in reference])
        result['dogrudan_ufuk_disi']=[r for r in reference if r not in eligible]
    result.update(tier1_sayisi=sum(r['kademe']=='TIER1' for r in eligible),
                  kademe_sayilari=dict(Counter(r['kademe'] for r in eligible)),
                  emsal_ayrinti=eligible,emsaller=[[r['ikn'],r['tarih'],str(round(Decimal(r['islenmis_birim']),2))] for r in eligible])
    if n:
        amounts=[Decimal(r['islenmis_birim']) for r in eligible]
        central=median(amounts)
        result.update(durum='Emsal referansı',
                      ay=target,medyan=str(round(central,2)),alt=str(round(min(amounts),2)),ust=str(round(max(amounts),2)),
                      yontem='Ortak dönemdeki uygun sözleşme birim bedellerinin ağırlıksız ortancası. Miktar birimleştirme ve hedef toplamda kullanıldı.')
        result.pop('neden')
        if result.get('standart_miktar'):
            result['toplam']=str(round(central*Decimal(result['standart_miktar']),2))
            result['para_birimi']='TRY'
    from fiyat_referansi import hazirla
    result.update(hazirla(doc,rule,nominal_rows,target))
    result['kdv_senaryolari']=kdv_senaryolari(doc,rule,nominal_rows,result,ayar,target)
    if reference and not n:
        result['neden']='Doğrudan emsaller seçilen zaman ufkunun dışında. Eski gözlemler duyarlılık bölümünde gösteriliyor.'
    elif not n and result['fiyat_referanslari']:
        result.update(durum='Koşullu fiyat referansı' if result['kosullu_ozetler'] else 'Yalnız emsal referansı',
            neden='Fiyat ve kaynak miktarı bulunan EKAP gözlemleri hesaplandı. KDV ve sözleşme miktarı teyidi eksikleri aşağıda açıklandı; bunlar doğrudan teklif fiyatı değildir.')
    result['asama_sayilari'].update(
        kosullu_fiyat_referansi=result['referans_sayisi'],
        teknik_eslesen_referans=result['teknik_eslesen_referans'])
    # Ambalaj alanlarını karıştıran önceki girdiyi sessizce değiştirme.
    result['uyarilar']=[]
    from emsal import ARCHIVE
    if not ARCHIVE.is_file():
        result['uyarilar'].append('Yerel ihale arşivi bulunamadı. Raporda erişilebilen kaynaklar gösteriliyor.')
    if not rule and len(doc['kalemler'])==1:
        from emsal import number
        item=doc['kalemler'][0]
        amount=number(item.get('miktar'))
        if amount:
            result.update(standart_miktar=str(amount),birim=item.get('birim'),kdv=extra.get('kdv_esasi') or 'belirsiz')
    if rule and rule.get('carpan') and len(doc['kalemler'])==1:
        tech=doc['kalemler'][0].get('teknik',{})
        if str(tech.get(rule['carpan']))==str(tech.get('Paketteki yaprak sayısı')) and tech.get(rule['carpan']):
            result['uyarilar'].append('Kolideki paket sayısı ile paketteki yaprak sayısı aynı girilmiş. Miktar dönüşümünü kontrol edin; 5 paket/koli ile 500 yaprak/paket farklı alanlardır.')
    from dosya_fiyatlari import envanter,rapor_icin
    result['dosya_fiyat_analizi']=rapor_icin(doc,envanter(target,official_proofs=good))
    return result
