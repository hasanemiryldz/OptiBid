"""Kayıtlı rapor miktarı üzerinden taslak teklif senaryosu."""
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from hesap_araclari import sayi
import asyncio
import json
import re

def turkce_sayi(value):
    if not re.fullmatch(r'(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?',value):
        raise ValueError('Ondalık ayracı için virgül, binlik ayracı için nokta kullanın.')
    return value.replace('.','').replace(',','.')

def hesap(miktar:str, alis:str, nakliye:str, diger:str, finansman:str, oran:str, esas:str):
    try:
        q,b,n,d,f,r=map(Decimal,(miktar,alis,nakliye,diger,finansman,oran))
    except (InvalidOperation,TypeError):
        raise ValueError("Geçerli bir tutar girin.") from None
    if not all(x.is_finite() and 0<=x<=10**12 for x in (q,b,n,d,f,r)) or q<=0 or esas not in ('maliyet','ciro') or esas=='ciro' and r>=100:
        raise ValueError("Miktarı, giderleri ve hedef oranı kontrol edin.")
    cost=q*b+n+d+f
    target=cost*(1+r/100) if esas=='maliyet' else cost/(1-r/100)
    unit=(target/q).quantize(Decimal('.01'),rounding=ROUND_CEILING)
    sale=unit*q
    profit=sale-cost
    return {k:str(round(v,2)) if v is not None else None for k,v in
            [('miktar',q),('maliyet',cost),('basabas',cost/q),('birim_teklif',unit),('satis',sale),('kar',profit),
             ('kar_maliyet_yuzde',100*profit/cost if cost else None),('ciro_marji',100*profit/sale if sale else None)]}

async def arac(args):
    from mcp_hesap import arac as call
    return await call('maliyet_senaryosu_hesapla',args)

def dogrula_arac(name,args,expected,reply,calc_ref):
    from mcp_hesap import calistir
    try:
        value,trace=calistir(name,args)
    except Exception:
        return dict(reply,answer_status='UNAVAILABLE',metin='MCP hesap aracı yanıt vermedi. Mesajınızı yeniden gönderin.')
    if value!=expected:
        return dict(reply,answer_status='CONFLICT',conflicts=['Araç çıktısı yerel hesapla uyuşmadı.'],
                    metin='Hesap sonucu doğrulanamadı.')
    return dict(reply,answer_status='SUPPORTED',metin='Sonuç doğrulanmış MCP hesabından alındı.',
                calculations=[{'type':'HESAP_SONUCU','calc_ref':calc_ref,'sonuc':value}],iz=trace)

def durum_bilgisi(snap):
    from collections import Counter
    from ekap_veri import snapshot
    _,_,current=snapshot()
    if not snap:
        from dosya_fiyatlari import envanter
        file_meta=envanter()['ozet']
        current={**current,'tum_dosya_fiyati':file_meta['fiyati_bulunan'],'dosya_fiyati':None}
        return dict(veri_surumu=current['surum'],kapsam=current,durum='Hazırlık ekranı')
    result=snap['sonuc']
    scope=result.get('havuz_kapsami',{})
    report={k:scope[k] for k in ('ham','benzersiz','benzersiz_ikn','ekap','bekliyor','karantina') if k in scope}
    report.update(kullanilan=len(result.get('emsaller',[])),aday=result.get('kategori_adayi'),
                  kosullu_referans=len(result.get('fiyat_referanslari',[])),
                  dosya_fiyati=result.get('dosya_fiyat_analizi',{}).get('kullanilan_fiyat',0),
                  tum_dosya_fiyati=result.get('dosya_fiyat_analizi',{}).get('havuz_ozeti',{}).get('fiyati_bulunan',0))
    groups={key:len(rows) for key,rows in (result.get('gruplar') or {}).items()}
    reasons=Counter(row['neden'] for row in result.get('dislanan',[]))
    return dict(veri_surumu=result['veri_surumu'],guncel_veri_surumu=current['surum'],kapsam=report,durum=result['durum'],
                neden=result.get('neden'),dislamalar=dict(reasons),hatalar=result.get('modul_hatalari',{}),gruplar=groups,
                filtreler=dict(kategori=snap['belge']['kategori'],tur=snap['belge']['ihale_turu'],
                               kdv=result.get('kdv'),donem=(result.get('endeks') or {}).get('son_ay')))


def yardim(question,adim=None):
    steps=(
        'İlanın alım türünü seçin. Mal, hizmet, yapım ve danışmanlık ayrı kategori ağaçları açar.',
        'İlanda ürünü veya işi karşılayan en dar kategoriyi seçin. Teknik sorular bu seçime göre değişir.',
        'Her kaleme ilandaki adı, istenen miktarı ve birimi girin. Koli ile paket farklıysa kolideki paket sayısını teknik adımda belirtin.',
        'İlanda verilen teknik değeri girin. Şartname bu değeri belirtmiyorsa Bilinmiyor seçeneğini kullanın.',
        'İlanda belirtilen teslim yerini, süresini ve gün türünü girin. Ardından Raporu hazırla düğmesini kullanın.',
    )
    if 'kdv' in question:
        return ('KDV dahil ve KDV hariç bedellerin hesap esası farklıdır. Karşılaştırma aynı KDV esasındaki '
                'belgelenmiş bedellerle yapılır. Geçmiş sözleşmede esas yazmıyorsa gözlem ayrı gösterilir.')
    if re.search(r'marj|maliyet üzerine|maliyete göre',question):
        return 'Maliyet üzerine kâr, maliyete göre hesaplanır. Ciro marjı, kârın satış gelirine oranıdır.'
    if type(adim) is int and 0<=adim<len(steps):
        return steps[adim]
    return ('Yeni hazırlık ile ihale türünü ve kategoriyi seçin. Kalemleri, teknik şartları ve teslimatı girin. '
            'Raporu hazırlayınca EKAP kaynaklarını inceleyebilir ve kendi maliyetinizle teklif senaryosu çalıştırabilirsiniz.')


def cevap(snap,question,adim=None,context=None,history=None,*,context_verified=False):
    from asistan import arama_istegi,internet,genel
    if arama_istegi(question):
        value=internet(question,snap,context)
        return dict(value,report_id=snap['belge'].get('id') if snap else None,
                    input_revision=snap['belge'].get('rev') if snap else None,
                    data_version=snap['sonuc'].get('veri_surumu') if snap else None)

    from ollama_ayar import secili
    model=secili()
    requested=model
    result=snap['sonuc'] if snap else {}
    doc=snap['belge'] if snap else (context or {})
    fields=('alis','nakliye','diger','finansman','oran')
    revision=re.fullmatch(r'\s*nakliye\s+(\d+(?:[.,]\d+)*)\s*(?:tl)?\s*olursa.*',question,re.I)
    if revision and snap:
        for message in reversed((history or [])[-8:]):
            prior=message.get('user') if isinstance(message,dict) else None
            if isinstance(prior,str) and re.search(r'alış|[×*]',prior,re.I):
                previous=re.compile(r'(nakliye\s*[:=]?\s*)\d+(?:[.,]\d+)*',re.I)
                if len(list(previous.finditer(prior)))==1:
                    revised=previous.sub(lambda m:m[1]+revision[1],prior)
                    value=cevap(snap,revised)
                    if value.get('hesap'):
                        value['metin']='Nakliye değişikliği ayrı bir senaryo olarak hesaplandı. '+value['metin']
                    return value
    contract=dict(intent=None,report_id=doc.get('id'),input_revision=doc.get('rev'),data_version=result.get('veri_surumu'),
                  answer_status='UNAVAILABLE',claims=[],calculations=[],assumptions=[],missing_fields=[],conflicts=[],
                  ollama_izi=dict(requested_model=requested,actual_model=None))
    # Bilinen araç sorularını modele sınıflattırarak bekletme. Açık uçlu sorular
    # aşağıda tek bağlamlı Ollama çağrısıyla yanıtlanır.
    model='araç'
    intent='diger' if snap else 'yardim'
    normalized=question.casefold()
    if re.search(r'önceki talimat|talimatları unut|sahte kaynak',normalized):
        return dict(contract,mod=model,metin='Bu istek için rapor dayanağı doğrulanamadı.')
    if re.search(r'hangi model|model hangisi|model adı',normalized):
        intent='model'
    elif re.search(r'rapor(?:um)? neden|kaç kayıt|kaç fiyat|tüm veri|bütün veri|tüm fiyat|neden (?:sadece|yalnız)|verilerim nerede|yeni veri|diğer veri|neden kullanılmad|kayıt görünüyor|neden.*(?:rapor|hesap)|(?:rapor|hesap).*(?:çıkmadı|çalışmıyor|hesaplanmadı)',normalized):
        intent='durum'
    elif re.search(r'y[ıi̇]+.üfe|endeks|hangi aya|fiyat dönemi',normalized) and 'alış' not in normalized:
        intent='endeks'
    elif re.search(r'kaç paket|kaç koli|pakete çevir|koliye çevir|birim dönüştür',normalized):
        intent='birim'
    elif re.search(r'^merhaba[.! ]*$|nasıl kullanılır|kâr marjı nedir|bu alan|nasıl doldur|kdv.*(?:neden|önem|nedir)',normalized):
        intent='yardim'
    elif re.search(r'rakip|yüklenici|ihaleyi kim',normalized):
        intent='rakip'
    elif re.search(r'(?:alış|nakliye|maliyet üzerine).*\d',normalized):
        intent='maliyet'
    elif re.search(r'hangi bilgi.*eksik|neler eksik|eksik alan',normalized):
        intent='eksik'
    elif re.search(r'emsal|dayanak|kaynak|nasıl hesaplan|fiyat|bedel|kaç (?:tl|lira)|ortanca',normalized) and not re.search(r'alış|nakliye|\bkâr\b',normalized):
        intent='emsal'
    reply=dict(contract,mod=model,intent=intent,answer_status='NEEDS_CLARIFICATION')
    if intent=='model':
        from ajan import model_sec
        try:
            checked=model_sec([{'role':'user','content':'Yalnız tamam yaz.'}],[],timeout=15,num_predict=12)
            trace=checked['ollama_izi']
            return dict(reply,mod=trace['actual_model'],ollama_izi=trace,answer_status='SUPPORTED',
                        metin='Ollama yanıtı '+trace['actual_model']+' modeliyle doğrulandı.')
        except (OSError,ValueError,KeyError,TypeError):
            return dict(reply,mod='yerel',answer_status='UNAVAILABLE',metin='Seçili model qwen3:8b. Ollama model yanıtı doğrulanamadı.')
    if intent=='durum':
        if not snap and re.search(r'rapor.*(?:neden|çıkmadı|oluşmadı)',normalized):
            if not doc.get('id'):
                msg='Açık bir çalışma kaydı bulunamadı.'
            elif not doc.get('tamam'):
                msg='Çalışma inceleme aşamasında. Bu sürüm için kaydedilmiş bir rapor yok.'
            else:
                msg='İnceleme tamamlandı ancak asistana bu sürüme ait bir rapor bağlı değil. Rapor ekranını yeniden açın.'
            return dict(reply,mod='yerel',answer_status='PARTIAL',metin=msg)
        from mcp_hesap import calistir
        args=dict(rapor_id=doc['id'],rev=doc['rev'],tarih=snap['tarih']) if snap else {}
        try:
            diagnostics,trace=calistir('analiz_durumu_getir',args,timeout=10)
            if diagnostics!=durum_bilgisi(snap):
                raise ValueError('Tanılama sürümü farklı.')
        except Exception:
            diagnostics=durum_bilgisi(snap)
            trace={'arac':'yerel_rapor_tanisi','mod':'yerel','mcp_dogrulandi':False}
        files=result.get('dosya_fiyat_analizi',{})
        message=(f"Yüklenen dosyalarda toplam {files.get('havuz_ozeti',{}).get('fiyati_bulunan',0)} fiyat işlendi; "
                 f"seçilen kategoride {files.get('kullanilan_fiyat',0)} dosya fiyatı rapora alındı. "
                 'Dosya fiyatları ve bağımsız EKAP dayanaklı fiyatlar ayrı analiz edilir. ') if files else ''
        message+=diagnostics.get('neden') or ('Kayıtlı raporun veri sürümü ve kapsamı aşağıda.' if snap else
                                            'Veri havuzunun güncel kapsamı aşağıda. Hazırlıktan rapor üretebilirsiniz.')
        if snap and re.search(r'yeni veri|diğer veri',normalized):
            if diagnostics['guncel_veri_surumu']==diagnostics['veri_surumu']:
                message+=' Bu rapor güncel veri havuzunu taradı. Fiyat hesabına giren emsaller ve dışlama nedenleri aşağıda.'
            else:
                message+=' Veri havuzu bu rapordan sonra değişti. Yeni verileri değerlendirmek için Güncel veriyle yenile düğmesini kullanın.'
        return dict(reply,answer_status='SUPPORTED',kapsam=diagnostics['kapsam'],
                    tani=diagnostics,metin=message,iz=trace)
    if intent=='yardim' or (not snap and intent!='birim') or intent=='diger':
        guide=genel(snap,question,context=context,history=history,adim=adim,context_verified=context_verified)
        return {**reply,**guide}

    if intent=='birim':
        from hesap_araclari import birim_donustur
        if len(doc.get('kalemler',[]))!=1:
            return dict(reply,metin='Dönüşüm için bir kalem seçin.')
        item=doc['kalemler'][0]
        pack=item.get('teknik',{}).get('Kolideki paket sayısı')
        destination='koli' if re.search(r'kaç koli|koliye',normalized) else 'paket'
        explicit=re.findall(r'(\d+(?:[.,]\d+)*)\s*(koli|paket)\b',normalized)
        if len(explicit)>1:
            return dict(reply,metin='Dönüştürülecek tek miktarı ve birimini belirtin.')
        quantity,source_unit=explicit[0] if explicit else (item.get('miktar'),item.get('birim'))
        if explicit:
            try:quantity=turkce_sayi(quantity)
            except ValueError as e:return dict(reply,metin=str(e))
        args=dict(miktar=str(quantity),birim=source_unit,hedef=destination,
                  paket_carpani=str(pack) if pack else None)
        try:expected=birim_donustur(**args)
        except ValueError as e:return dict(reply,metin=str(e))
        return dogrula_arac('birim_donustur',args,expected,reply,'senaryo.birim.v1')
    if intent=='endeks':
        from tuik_endeks import endeksle,bilgi
        index=result.get('endeks')
        if not index:
            return dict(reply,answer_status='UNAVAILABLE',metin='Bu raporun kayıtlı bir TÜİK serisi yok.')
        identifiers=re.findall(r'20\d{2}/[1-9]\d*',question)
        if identifiers:
            row=next((r for r in result.get('nominal',[]) if r['ikn']==identifiers[0]),None)
            if not row or row.get('para')!='TRY':
                return dict(reply,answer_status='UNAVAILABLE',metin='İKN bu raporda endekslenebilir bir TRY gözlemiyle eşleşmiyor.')
            target=re.findall(r'20\d{2}-\d{2}',question)
            args=dict(tutar=row['fiyat'],seri=index['seri'],kaynak_ay=row['tarih'][:7],hedef_ay=target[0] if target else index['son_ay'])
            try:
                if bilgi(index['seri'])['dosya_sha256']!=index['dosya_sha256']:raise ValueError('Endeks verisi değişti. Yeni bir rapor açın.')
                expected=endeksle(**args)
            except ValueError as e:return dict(reply,answer_status='UNAVAILABLE',metin=str(e))
            return dogrula_arac('fiyat_endeksle',args,expected,reply,'senaryo.endeks.v1')
        return dict(reply,answer_status='SUPPORTED',endeks=index,
                    metin='Raporun kullandığı resmî TÜİK endeks bilgisi aşağıdadır. İKN yazarak o bedelin dönem eşitlemesini isteyebilirsiniz.')
    if intent=='emsal' and not (result.get('dosya_fiyat_analizi',{}).get('kullanilan_fiyat') or result.get('fiyat_referanslari') or result.get('nominal')):
        research=internet(question,snap,context)
        research['metin']='Bu profil için yerel raporda fiyat dayanağı bulunamadı. '+research['metin']
        return {**reply,**research}
    if intent=='emsal':
        snapshots=result.get('nominal',[])
        claims=[dict(type='EKAP_BULGUSU',field='sozlesme_bedeli',ikn=r['ikn'],deger=r['fiyat'],
                     tarih=r['tarih'],birim=r['para'],kdv=r['kdv'],source_ref=r.get('kaynak_url') or r['kaynak']) for r in snapshots]
        summaries=result.get('kosullu_ozetler',[])
        files=result.get('dosya_fiyat_analizi',{})
        if files.get('kullanilan_fiyat') and ('ekap' not in normalized or 'dosya' in normalized):
            groups=files.get('grup_ozetleri',[])
            segments=[f"{s['kategori']} · {s['sayi']} {s['birim']} kaydı · ortanca "
                      f"{s['medyan'].replace('.',',')} {s['para'] or 'para birimi belirsiz'}/{s['birim']} "
                      f"({s['donem']}, KDV {s['kdv']})" for s in groups]
            candidates=sum(r['kapsam']=='urun_adayi' and r['kullanilan_birim_fiyat'] is not None for r in files['kayitlar'])
            mixed=sum(r['kapsam']=='karma_veya_teknik_eksik' and r['kullanilan_birim_fiyat'] is not None for r in files['kayitlar'])
            message=f"Seçilen kategoride {files['kullanilan_fiyat']} dosya fiyatı incelendi."
            if candidates or mixed:
                message+=f' {candidates} A4 ürün adayı ve {mixed} karma veya teknik eksiği olan alım ayrı gösteriliyor.'
            if segments:
                message+=' '+' / '.join(segments)+'.'
            message+=' Bunlar dosya beyanlarından üretilen tarihsel tanımlayıcı istatistiklerdir. Bağımsız EKAP teyidi ve fiyat esası eksikleri raporda yer alır.'
            file_claims=[dict(type='DOSYA_FIYAT_BEYANI',field='birim_fiyat',ikn=r['ikn'],deger=r['kullanilan_birim_fiyat'],
                       tarih=r['fiyat_tarihi'],birim=r['para']+'/'+r['birim'],kdv=r['kdv'],source_ref=r['veri_dayanagi'])
                       for r in files['kayitlar'] if r['kullanilan_birim_fiyat'] is not None]
            return dict(reply,answer_status='PARTIAL',claims=file_claims,metin=message)
        message='Rapor, EKAP kaynaklarındaki tarihli sözleşme bedellerini gösteriyor.'
        if summaries:
            s=summaries[0]
            tr=lambda value:str(value).replace('.',',')
            message+=(f" {s['sayi']} teknik profili eşleşen gözlemin {s['ay']} düzeyindeki koşullu ortancası "
                      f"{tr(s['medyan'])} TL/{s['birim']}. KDV {s['kdv']}. "
                      'Bu bir teklif önerisi veya doğrulanmış KDV hariç piyasa fiyatı değildir. '
                      'Sonuç bedeli kaynak miktarına bölünüp Yİ-ÜFE ile ortak aya taşındı. '
                      'İhale miktarının sözleşmede aynen gerçekleştiği varsayımı var.')
        elif result.get('fiyat_referanslari'):
            message+=' Kaynak birim fiyatları hesaplandı; teknik veya endeks eksikleri nedeniyle ortak ortanca verilmedi.'
        else:
            message+=' Aynı kapsamda bedel ve miktar eşleştirilmediğinden birim fiyat hesaplanamadı.'
        return dict(reply,answer_status='PARTIAL' if claims else 'UNAVAILABLE',claims=claims,
                    metin=message,assumptions=[v for s in summaries for v in s['varsayimlar']])
    if intent=='rakip':
        if re.search(r'maliyet|strateji|olasılı|teklif tutar',question.casefold()):
            return dict(reply,answer_status='UNAVAILABLE',metin='Bu raporun EKAP dayanaklarında istenen rakip bilgisi bulunamadı.')
        claims=[dict(type='EKAP_BULGUSU',field='sonuc.yuklenici',ikn=r['ikn'],deger=r['firma'],
                     tarih=r['tarih'],source_ref=r['kaynak']) for r in result.get('nominal',[]) if r.get('firma')]
        return dict(reply,answer_status='PARTIAL' if claims else 'UNAVAILABLE',claims=claims,
                    metin='Kayıtlı sonuç ekranlarında görünen yükleniciler. Bu kapsam katılım ve geçerli teklif sayısını göstermez.')
    if intent=='eksik':
        from motor import oku
        kind=doc.get('ihale_turu')
        category=doc.get('kategori',[])
        definitions=oku('catalog.json')['turler'].get(kind,{})
        fields=definitions.get(category[0],{}).get(category[1],[]) if len(category)==2 else []
        missing=[]
        for item in doc.get('kalemler',[]):
            title=item.get('ad') or 'Kalem'
            missing.extend(f"{title} · {field}" for field in fields if item.get('teknik',{}).get(field) in (None,''))
            missing.extend(f"{title} · {label}" for key,label in (('miktar','Miktar'),('birim','Birim')) if not item.get(key))
        if any(row.get('kdv') not in ('hariç','dahil') for row in result.get('nominal',[])):
            missing.append('Emsal bedellerinin KDV esası')
        if any(row.get('endeks_eksik') for row in result.get('nominal',[])):
            missing.append('Bazı emsallerin karşılaştırılabilir fiyat dönemi')
        message='Eksik bilgiler · '+', '.join(missing) if missing else 'Kayıtlı hazırlık alanları dolu. Emsal kaynaklarının kapsam ve teyit durumları raporda gösterilir.'
        return dict(reply,answer_status='SUPPORTED',missing_fields=missing,metin=message)
    if intent!='maliyet':
        return {**reply,**genel(snap,question,context=context,history=history,adim=adim)}
    unit=result.get('birim')
    quantity=result.get('standart_miktar')
    if not unit or not quantity:
        return dict(reply,metin='Bir kalemin miktarını ve satış birimini doğrulayın. Birden fazla kalem için ortak giderlerin kalemlere göre dağılımı gerekir.')
    numeric=r'(\d+(?:[.,]\d+)*)'
    expression=re.search(rf'{numeric}\s+{re.escape(unit)}\s*[×x*]\s*{numeric}\s*TL\b',question,re.I)
    if expression:
        try:
            entered=sayi(turkce_sayi(expression[1]))
        except ValueError as e:
            return dict(reply,metin=str(e))
        if entered!=sayi(quantity):
            return dict(reply,metin='Yazdığınız miktar kayıtlı rapor miktarıyla uyuşmuyor. Rapor üzerinden miktarı doğrulayın.')
        question=question+' Alış '+expression[2]+' TL/'+unit
    if not re.search(r'TL\s*/\s*'+re.escape(unit)+r'\b',question,re.I):
        return dict(reply,metin='Alış bedelini hangi satış birimi için verdiniz?')
    on_cost=bool(re.search(r'maliyet(?:in)? üzerin',question.casefold()))
    on_revenue='ciro' in question.casefold()
    expected_esas=('maliyet' if on_cost else 'ciro') if on_cost!=on_revenue else None
    if not expected_esas:return dict(reply,metin='Hedef kâr oranı maliyet üzerine mi, satış cirosu üzerinden mi?')
    if 'hariç' not in question.casefold() or 'dahil' in question.casefold():
        return dict(reply,metin='Kendi maliyet senaryonuz için giderlerin KDV hariç olduğunu belirtin. Emsallerin KDV esası bu bağımsız hesabı engellemez.')
    text=question.casefold()
    number=r"(-?\d+(?:[.,]\d+)*)"
    phrases={"alis":rf"(?:alış(?:ım| bedeli| maliyeti)?|birim maliyet(?:im)?)\s*[:=]?\s*{number}",
             "nakliye":rf"nakliye\s*[:=]?\s*{number}", "diger":rf"diğer(?: gider(?:ler)?)?\s*[:=]?\s*{number}",
             "finansman":rf"finansman\s*[:=]?\s*{number}", "oran":rf"%\s*{number}"}
    args={};missing=[]
    for k in fields:
        matches=re.findall(phrases[k],text)
        if not matches and k not in ('alis','oran') and ('diğer' if k=='diger' else k) not in text:
            args[k]='0';missing.append(k);continue
        if len(set(matches))!=1 or not re.fullmatch(r'(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?',matches[0]):
            return dict(reply,metin='Tutarları alış, nakliye, diğer gider ve finansman etiketleriyle, hedefi % işaretiyle yazın.')
        args[k]=matches[0].replace('.','').replace(',','.')
    args.update(miktar=quantity,esas=expected_esas)
    try:
        expected=hesap(**args)
    except (ValueError,InvalidOperation) as error:
        return dict(reply,metin=str(error))
    try:
        answer,trace=asyncio.run(asyncio.wait_for(arac(args),timeout=25))
    except Exception:
        return dict(reply,answer_status='UNAVAILABLE',metin='Hesap aracı yanıt vermedi. Mesajınızı yeniden gönderin.')
    if answer!=expected:
        return dict(reply,answer_status='CONFLICT',conflicts=['Araç çıktısı yerel hesapla uyuşmadı.'],
                    metin='Hesap sonucu doğrulanamadı. Mesajınızı yeniden gönderin.')
    calc=dict(type='HESAP_SONUCU',calc_ref='senaryo.maliyet.v1',miktar_birimi=unit,kdv='hariç',sonuc=answer)
    return dict(reply,answer_status='PARTIAL' if missing else 'SUPPORTED',calculations=[calc],
                assumptions=[dict(type='KULLANICI_BEYANI',alan=k,deger=v) for k,v in args.items() if k!='miktar' and k not in missing],
                missing_fields=missing,metin='Taslak senaryo yalnız girilen KDV hariç giderlerden hesaplandı. KDV esası belirsiz emsal fiyatlarıyla kâr karşılaştırması yapılmadı.',
                hesap=answer,girdiler=dict(args,maliyet_kdv_esasi='hariç'),eksik=missing,iz=trace)

def kaydet(db,snap,girdiler):
    from datetime import datetime,timezone
    from uuid import uuid4
    allowed=('alis','nakliye','diger','finansman','oran','esas')
    if not isinstance(girdiler,dict) or not all(isinstance(girdiler.get(k),str) for k in allowed):
        raise ValueError("Senaryo değerlerini kontrol edin.")
    quantity=snap['sonuc'].get('standart_miktar')
    if not quantity or not (girdiler.get('maliyet_kdv_esasi')=='hariç' or snap['sonuc'].get('kdv')=='hariç'):
        raise ValueError("Kayıtlı miktar ve maliyetlerin KDV hariç beyanı gerekli.")
    args={k:girdiler[k] for k in allowed}
    value=hesap(quantity,**args)
    entry={'girdiler':args,'hesap':value,'id':str(uuid4())}
    db.execute("INSERT INTO rapor_senaryolari VALUES(?,?,?,?,?)",
               (entry['id'],snap['belge']['id'],snap['tarih'],json.dumps(entry),datetime.now(timezone.utc).isoformat()))
    return entry
