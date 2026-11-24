"""Yüklenen dosyaların bütün fiyatlarını alan kökeniyle analize açar.

Bu katman resmî EKAP teyidi üretmez. Eski "Doğrulandı" etiketi veya iç
aritmetik tutarlılık, resmî teyit yerine kullanılamaz. Dosya fiyatları,
EKAP dayanaklı fiyat katmanından ayrı sonuç alanında kalır.
"""
from collections import Counter, defaultdict
from contextlib import closing
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
from statistics import median
from urllib.parse import urlsplit
from veri_yollari import DATA, HOME

ROOT=Path(__file__).resolve().parent
SURUM='dosya-fiyatlari-v19'


def sayi(raw):
    try:
        n=Decimal(str(raw))
        return n if n.is_finite() and 0<n<=Decimal('1e18') else None
    except (InvalidOperation,ValueError,TypeError):
        return None


def para(n):
    return str(n.quantize(Decimal('.01'),rounding=ROUND_HALF_UP)) if n is not None else None


def normal(raw):
    """İki mevcut dosya biçimini tek şemaya çevir; bilinmeyeni doldurma."""
    def field(a,b): return raw.get(a) if raw.get(a) is not None else raw.get(b)
    text=lambda v:str(v) if v is not None else None
    return dict(ikn=str(raw.get('ikn','')).strip(),ad=raw.get('kalem_adi') or raw.get('urun_hizmet_tanimi') or raw.get('ihale_adi'),
        idare=raw.get('idare'),kategori=field('kaynak_kategori','emsal_grubu') or 'Sınıflandırılmadı',
        tier=field('kaynak_sinifi','kategori_tier'),tarih=raw.get('ihale_tarihi'),
        miktar=text(raw.get('miktar')),birim=raw.get('birim'),para=field('para','para_birimi') or None,
        toplam=text(field('sozlesme_toplami','sozlesme_bedeli_orijinal')),
        birim_fiyat=text(field('kaynak_birim_fiyat','birim_fiyat_orijinal')),
        kdv=raw.get('kdv_esasi') if raw.get('kdv_esasi') in ('hariç','dahil') else 'belirsiz',
        kaynak_beyani=field('kaynak_beyani','ekap_dogrulama_durumu'),
        sozlesme_tarihi=raw.get('sozlesme_tarihi'),kaynak_sozlesme_sirasi=raw.get('kaynak_sozlesme_sirasi'))


def kaynaklar():
    """Durum filtresi, kategori/Tier sınırı ve SQL LIMIT kullanmadan oku."""
    from ekap_veri import official
    entries=[];external=[]
    for path in sorted((DATA/'alim').glob('*/alim.sqlite')):
        with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
            for digest,line,raw in db.execute('SELECT dosya_sha256,satir_no,alanlar_json FROM standart_kayit ORDER BY satir_no'):
                record=json.loads(raw)
                source=dict(dosya=str(path.relative_to(HOME)),kaynak_sha256=digest,konum='standart_kayit:'+str(line))
                if record.get('kaynak_dosya'):
                    source.update(dosya=str(path.with_name(Path(record['kaynak_dosya']).name).relative_to(HOME)),
                                  konum=record['kaynak_sayfa']+' · satır '+str(line))
                    if official(record.get('kaynak_url')):
                        source['url']=record['kaynak_url']
                entries.append((normal(record),source))
    path=HOME/'OptiBid_Emsal_Tam_Veri_genisletilmis.json'
    if path.is_file():
        content=path.read_bytes();digest=sha256(content).hexdigest()
        for pos,raw in enumerate(json.loads(content.decode('utf-8-sig'))):
            ref=raw.get('_kaynak') or {}
            source=ref.get('kaynak') if isinstance(ref,dict) else None
            parsed=urlsplit(str(source or ''))
            if parsed.scheme in ('http','https') and parsed.hostname and parsed.hostname not in ('ekap.kik.gov.tr','ekapv2.kik.gov.tr'):
                # Bilinen haricî ilanı fiyat analiziyle karıştırma.
                external.append(dict(ikn=raw.get('ikn'),neden='EKAP dışı kaynak; ayrı arşivde tutuldu.'))
                continue
            entries.append((normal(raw),dict(dosya=path.name,kaynak_sha256=digest,konum='/'+str(pos))))
    unique={}
    for row,source in entries:
        # Aynı sayının 85.7 / 85.70 / 85.700 yazılışı yeni gözlem değildir.
        def numerical(x):
            value=sayi(x)
            return str(value.normalize()) if value is not None else str(x)
        key=tuple(numerical(row[k]) if k in ('miktar','toplam','birim_fiyat') else str(row[k])
                  for k in ('ikn','kategori','tarih','birim','para','miktar','toplam','birim_fiyat',
                            'sozlesme_tarihi','kaynak_sozlesme_sirasi'))
        if key not in unique:unique[key]={**row,'kaynaklar':[]}
        unique[key]['kaynaklar'].append(source)
    records=list(unique.values())
    collisions=Counter(r['ikn'] for r in records if r['birim'] and (r['miktar'] or r['birim_fiyat']))
    for row in records:
        row['kimlik_celiskisi']=bool(row['birim'] and collisions[row['ikn']]>1)
    return records,dict(ham_satir=len(entries),benzersiz=len(records),tekrar=len(entries)-len(records),
                       harici_ilan=len(external))


def envanter(target_month=None,*,records=None,official_proofs=None):
    """Her fiyatı korur; özetleri kategori/birim/dönem/fiyat esasına ayırır."""
    from tuik_endeks import seriler,endeksle
    from ekap_veri import verified
    if records is None:
        raw,meta=kaynaklar()
    else:
        raw=records;meta=dict(ham_satir=len(raw),benzersiz=len(raw),tekrar=0,harici_ilan=0)
    config=json.loads((ROOT/'dosya_fiyat_kategorileri.json').read_text(encoding='utf-8'))['kategori_eslesmeleri']
    catalog=json.loads((ROOT/'catalog.json').read_text(encoding='utf-8'))
    indices=seriler();proofs=verified() if official_proofs is None else official_proofs
    output=[];groups=defaultdict(list)
    for original in raw:
        row={**original};spec=config.get(row['kategori'],{})
        amount,total,declared=map(sayi,(row.get('miktar'),row.get('toplam'),row.get('birim_fiyat')))
        unit=row.get('birim');notes=[]
        derived=total/amount if total and amount else None
        # 4 ondalıklı kaynak birim fiyatının çarpım farkını hata sayma.
        coherent=bool(declared is None or derived is None or abs(declared*amount-total)<=amount*Decimal('.00005')+Decimal('.01'))
        price=declared if declared is not None else derived
        if not coherent:notes.append('Kaynak birim fiyatı ile toplam/miktar uyuşmuyor; özet dışında, iki değer de korundu.')
        basis=('Kaynakta beyan edilen birim fiyat' if declared is not None else 'Toplam / kaynak miktarı'
               if derived is not None else 'Sözleşme toplamı' if total is not None else 'Fiyat bulunamadı')
        row.update(tur=spec.get('tur'),kategori_yolu=spec.get('kategori'),kapsam=spec.get('kapsam','bilinmiyor'),
            kaynak_birim_fiyat=para(declared),toplam_miktar_birim_fiyat=para(derived),
            kullanilan_birim_fiyat=para(price),fiyat_tam_hassasiyet=str(price) if price is not None else None,
            fiyat_yontemi=basis,aritmetik_tutarli=coherent,ekap_teyit_durumu='TEYİT_BEKLİYOR',
            kaynak_sinifi='KULLANICI_YUKLEMESI',resmi_fiyat_olarak_kullan=False,
            kaynak_ikn_bicimi=bool(re.fullmatch(r'20\d{2}/[1-9]\d{0,8}',row['ikn'])))
        proof=proofs.get(row['ikn'])
        event=proof.get('sonuc') if proof else None
        # Yalnız aynı tutar eşleşirse daha açık fiyat olay tarihini kullan.
        if (event and total and sayi(event.get('fiyat'))==total and event.get('para')==row['para']
                and row.get('sozlesme_tarihi') in (None,event.get('tarih'))):
            row['ekap_teyit_durumu']='EKAP_BEDELI_ESLESTI_DIGER_ALANLAR_KISMI'
            when=event.get('tarih');date_basis='EKAP sözleşme tarihi'
        elif row.get('sozlesme_tarihi'):
            when=row['sozlesme_tarihi'];date_basis='Dosyada bildirilen sözleşme tarihi'
        else:
            when=row.get('tarih');date_basis='Dosyadaki ihale tarihi; fiyat olay tarihi teyit edilmedi'
        row.update(fiyat_tarihi=when,fiyat_tarih_esasi=date_basis,endeksli_birim_fiyat=None,endeks_iz=None)
        if not row['kaynak_ikn_bicimi']:notes.append('Yerel kimlik; resmî EKAP İKN olarak doğrulanmadı.')
        if row.get('kimlik_celiskisi'):notes.append('Aynı kimlikte farklı kaynak değerleri var; özet dışında, alternatifler korundu.')
        index_code=spec.get('endeks')
        if price and index_code and index_code in indices and row['para']=='TRY':
            target=target_month or indices[index_code]['son_ay']
            try:
                trace=endeksle(str(price),index_code,str(when or '')[:7],target,dataset=indices)
                row.update(endeksli_birim_fiyat=trace['tutar_endeksli'],endeks_iz=trace,
                           endeksli_tam_hassasiyet=str(price*Decimal(trace['hedef_endeks'])/Decimal(trace['kaynak_endeks'])))
            except ValueError as error:notes.append(str(error)+' Özgün fiyat korundu.')
        elif not index_code:
            notes.append('Bu kapsam için uygun fiyat endeksi atanmadı; farklı ürünün Yİ-ÜFE serisiyle güncel fiyat üretilmedi.')
        if row['kapsam']=='karma_veya_teknik_eksik':notes.append('Karma veya teknik eksiği olan alım. Fiyat A4/80 g/500 yaprak fiyatına genellenmez.')
        elif row['kapsam']=='urun_adayi':notes.append('A4/80 g ve 500 yaprak/paket eşdeğerliği kaynak dosya sınıflamasına dayanan varsayımdır; bağımsız teknik teyit değildir.')
        else:notes.append('İş kapsamı, süre ve içerik değişebilir; bu fiyatlar tek başına eşdeğer teklif sayılmaz.')
        notes.append('KDV esası '+row['kdv']+'; kaynak dosyanın doğrulandı etiketi bağımsız resmî fiyat teyidi sayılmaz.')
        row.update(notlar=notes,veri_dayanagi='/api/dosya-fiyat-dayanagi/'+row['ikn'])
        output.append(row)
        if price is not None and coherent and not row.get('kimlik_celiskisi') and unit in catalog['birimler']:
            # Belgeli bir dönüşüm yoksa özgün ölçü birimi korunur.
            period=(row.get('endeks_iz') or {}).get('hedef_ay') or 'Özgün tarihler / nominal'
            key=(row['kategori'],unit,row['para'],row['kdv'],period)
            groups[key].append(row)
    summaries=[]
    for (category,unit,currency,vat,period),items in sorted(groups.items(),key=lambda entry:tuple(str(value or '') for value in entry[0])):
        indexed=all(r.get('endeksli_tam_hassasiyet') for r in items)
        prices=[Decimal(r['endeksli_tam_hassasiyet'] if indexed else r['fiyat_tam_hassasiyet']) for r in items]
        summaries.append(dict(kategori=category,birim=unit,para=currency,kdv=vat,donem=period,
            sayi=len(items),medyan=para(median(prices)),alt=para(min(prices)),ust=para(max(prices)),
            iknler=[r['ikn'] for r in items],kapsam=items[0]['kapsam'],tur=items[0]['tur'],kategori_yolu=items[0]['kategori_yolu'],
            hesap_turu='DOSYA_TEMELLI_KOSULLU_ISTATISTIK' if indexed else 'TARIHSEL_NOMINAL_BETIMLEME',
            fiyat_esasi='Endeksli' if indexed else 'Özgün tarihlerdeki fiyatlar',
            sinir='Yüklenen dosya iddialarının tanımlayıcı özeti; resmî teyitli piyasa tahmini, fiyat önerisi veya kazanma olasılığı değildir.'))
    counts=Counter(r['kategori'] for r in output)
    priced=sum(r['kullanilan_birim_fiyat'] is not None or sayi(r['toplam']) is not None for r in output)
    meta.update(fiyati_bulunan=priced,
                birim_fiyati_bulunan=sum(r['kullanilan_birim_fiyat'] is not None for r in output),
                ozetlerde_kullanilan=sum(s['sayi'] for s in summaries),kategori_sayisi=len(counts),
                kategori_sayilari=dict(counts),fiyatsiz=len(output)-priced,
                fiyat_aktarim_kapsami='TUM_SATIRLAR',harici_ilan_fiyat_analizine_alinmadi=True)
    version=sha256(json.dumps([SURUM,output,config,target_month],sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:16]
    return dict(surum=version,motor_surumu=SURUM,source_policy='USER_IMPORTED_UNVERIFIED',
                resmi_ekap_fiyat_katmaniyla_birlestirilmedi=True,ozet=meta,kayitlar=output,grup_ozetleri=summaries)


def rapor_icin(doc,inventory):
    """Bütün havuzdan seçilen kategoriye ilgili tüm kayıtları ayırır."""
    def match(row):return row.get('tur')==doc.get('ihale_turu') and row.get('kategori_yolu')==doc.get('kategori')
    records=[r for r in inventory['kayitlar'] if match(r)]
    excluded=set(doc.get('ek_bilgiler',{}).get('rapor_haric',[]))
    selected=[r for r in records if r['ikn'] not in excluded and r['ikn']!=doc.get('ek_bilgiler',{}).get('ikn')]
    # Özet kullanıcı dışlamaları sonrası yeniden hesaplanır; ekran filtresi değildir.
    summaries=[]
    for s in inventory['grup_ozetleri']:
        if not match(s):continue
        identifiers=set(s['iknler'])
        members=[r for r in selected if r['ikn'] in identifiers and not r.get('kimlik_celiskisi')]
        if not members:continue
        indexed=s['fiyat_esasi']=='Endeksli'
        values=[Decimal(r['endeksli_tam_hassasiyet'] if indexed else r['fiyat_tam_hassasiyet']) for r in members]
        summaries.append(dict(s,sayi=len(members),iknler=[r['ikn'] for r in members],
                              medyan=para(median(values)),alt=para(min(values)),ust=para(max(values))))
    return dict(source_policy=inventory['source_policy'],surum=inventory['surum'],havuz_ozeti=inventory['ozet'],
        kategori_adayi=len(records),kullanilan_fiyat=sum(r['kullanilan_birim_fiyat'] is not None or sayi(r['toplam']) is not None for r in selected),
        ozete_alinan=sum(s['sayi'] for s in summaries),gosterilen_satir=len(selected),kayitlar=selected,grup_ozetleri=summaries,
        kategori_disinda=len(inventory['kayitlar'])-len(records),
        kapsam_siniri='Dosya fiyatları ayrı katmandır. EKAP teyidi yoksa doğrulanmış emsal olarak gösterilmez.')


def ilgili_kayitlar(sorgu='',tur='',kategori=None):
    """Tüm fiyatları tarar. Bir eşleşmeyi resmî doğrulama diye etiketlemez."""
    query=re.sub(r'[^\w\s]',' ',str(sorgu).casefold())
    stop={'için','ile','bir','alım','alımı','ihale','ihaleleri','benzer','bul','ara','getir','internette','link','linklerini','ve'}
    terms={t for t in query.split() if len(t)>2 and t not in stop}
    inventory=envanter();matches=[]
    for row in inventory['kayitlar']:
        if tur and row['tur']!=tur:continue
        if kategori and row['kategori_yolu']!=kategori:continue
        text=' '.join(str(row.get(k) or '') for k in ('ad','kategori','ikn')).casefold()
        score=sum(t in text for t in terms)
        if terms and not score:continue
        matches.append((score,{'id':row['ikn'],'ikn':row['ikn'],'ad':row['ad'],'kategori':row['kategori_yolu'],
             'birim':row['birim'],'fiyat':row['kullanilan_birim_fiyat'],'sozlesme_toplami':row['toplam'],
             'tarih':row['fiyat_tarihi'],'para':row['para'],'kdv':row['kdv'],
             'kaynak':row['veri_dayanagi'],'durum':'Dosya beyanı · bağımsız EKAP teyidi bekliyor'}))
    matches.sort(key=lambda x:(-x[0],x[1]['ikn']))
    return {'taranan':len(inventory['kayitlar']),'eslesen':len(matches),'kayitlar':[r for _,r in matches]}
