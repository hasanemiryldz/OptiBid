"""Eksik KDV veya sözleşme miktarı fiyat gözlemini rapordan gizlemez.

Bu katman A (doğrudan karşılaştırma) grubunu değiştirmez. EKAP sonuç
bedelini aynı İKN'nin tek satırlı ihale miktarına böler; miktarın tamamının
bu bedelle sözleşmeye bağlandığı varsayımını açıkça taşır. KDV belirsiz
gözlemler hiçbir zaman KDV hariç maliyetle karşılaştırılmaz.
"""
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from statistics import median

SURUM = 'EKAP-FIYAT-REFERANSI-v18'


def para(value):
    return str(Decimal(str(value)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))


def dagilim(degerler):
    if not degerler:
        return dict(sayi=0, alt=None, medyan=None, ust=None)
    return dict(sayi=len(degerler), alt=para(min(degerler)), medyan=para(median(degerler)),
                ust=para(max(degerler)))


def hazirla(doc, rule, observations, target):
    """Görüntüleme/RAG top-k sınırı olmadan bütün kaynaklı gözlemleri işler."""
    from emsal import equal, number
    references, summaries = [], []
    groups = defaultdict(list)
    target_item = doc['kalemler'][0] if len(doc.get('kalemler', [])) == 1 else None
    target_ok = bool(rule and target_item and all(
        equal(target_item.get('teknik', {}).get(k), v) for k, v in rule['hedef'].items()))
    excluded = set(doc.get('ek_bilgiler', {}).get('rapor_haric', []))
    for row in observations:
        if row['ikn'] in excluded or row.get('karma'):
            continue
        item = row.get('teklif_cetveli')
        amount = number((item or {}).get('miktar'))
        total = number(row.get('fiyat'))
        if not (item and amount and total and row.get('para') == 'TRY'):
            continue
        # Bölen ihale miktarıdır: imzalanan miktar gibi sunulmaz.
        nominal = total / amount
        index = row.get('endeks_iz')
        normalized = nominal
        if index:
            normalized = nominal * Decimal(index['hedef_endeks']) / Decimal(index['kaynak_endeks'])
        tech = row.get('teknik') or {}
        matched = bool(target_ok and all(equal(tech.get(k), v) for k, v in rule['hedef'].items()))
        unit = item.get('birim')
        canonical = unit
        assumptions = []
        if row.get('miktar_esasi') != 'AYNI_KAYNAKTA_TEK_KALEM':
            assumptions.append('İhale cetvelindeki miktarın tamamının bu sözleşme bedeline karşılık geldiği varsayılır; imzalı kalem cetveli görülmedi.')
        if row.get('kdv') not in ('hariç', 'dahil'):
            assumptions.append('KDV esası belirsiz. Bu rakam KDV hariç fiyat, maliyet veya kâr hesabına aktarılmaz.')
        if not matched:
            assumptions.append('Hedef teknik profil bütünüyle eşleşmedi; fiyat kendi kaynak biriminde gösterilir, hedef fiyat ortancasına katılmaz.')
        ref = dict(ikn=row['ikn'],tarih=row['tarih'],kaynak=row['kaynak'],kaynak_url=row.get('kaynak_url'),
                   fiyat=str(total),miktar=str(amount),kaynak_birim=unit,birim=canonical,
                   ham_birim=para(nominal),islenmis_birim=para(normalized) if index else None,
                   hesap_tam_hassasiyet=str(normalized),para='TRY',kdv=row.get('kdv'),
                   teknik_eslesme=matched,teknik=tech,hedef_ay=index['hedef_ay'] if index else None,
                   kaynak_ay=row['tarih'][:7],endeks_iz=index,kalem_kaniti=item,
                   fiyat_kaniti=row.get('fiyat_kaniti'),varsayimlar=assumptions,
                   fiyat_niteligi='KOŞULLU_TARİHSEL_REFERANS',dogrudan_karsilastirilabilir=False,
                   ufuk=row.get('ufuk'))
        references.append(ref)
        if matched and index:
            # Bilinen KDV esasları ayrı; bilinmeyenler açık koşullu istatistiktir.
            groups[(canonical,row.get('kdv') or 'belirsiz',index['hedef_ay'])].append(ref)
    for (unit, vat, month), records in sorted(groups.items()):
        values=[Decimal(r['hesap_tam_hassasiyet']) for r in records]
        within=[Decimal(r['hesap_tam_hassasiyet']) for r in records if r['ufuk'] and not r['ufuk']['disinda']]
        center=median(values)
        summaries.append(dict(birim=unit,kdv=vat,ay=month,sayi=len(records),
            medyan=para(center),alt=para(min(values)),ust=para(max(values)),
            iknler=[r['ikn'] for r in records],ufuk_ici=dagilim(within),
            nitelik='KOŞULLU_REFERANS_ORTANCASI',
            yontem='Her İKN bir gözlem: sonuç bedeli / ihale miktarı, ardından aynı seriyle ortak aya taşıma; eşit ağırlıklı ortanca.',
            varsayimlar=['İhale miktarı ile sözleşme bedelinin aynı teslim kapsamını temsil ettiği varsayılır.',
                         'KDV esası belirsiz gözlemlerin aynı fiyat esasını taşıdığı varsayılır; doğrulanmış KDV hariç fiyat sayılmaz.'] if vat=='belirsiz' else [
                         'İhale miktarı ile sözleşme bedelinin aynı teslim kapsamını temsil ettiği varsayılır.'],
            piyasa_tahmini_dogrulandi=False,hedef_toplam=None))
    return dict(fiyat_referanslari=references,kosullu_ozetler=summaries,
                referans_sayisi=len(references),teknik_eslesen_referans=sum(r['teknik_eslesme'] for r in references),
                fiyat_katmani_surumu=SURUM)
