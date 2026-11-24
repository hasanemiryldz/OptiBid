"""Aynı kapsamı kaynakta bağlı, KDV esası belirsiz C grubu gözlemleri."""
from decimal import Decimal
from emsal import equal
from fiyat_referansi import dagilim, para
from hesap_araclari import birim_donustur, sayi
from urun_ayarlari import kdv_orani


def kdv_senaryolari(doc, rule, rows, result, ayar, hedef):
    if not rule or len(doc['kalemler']) != 1 or result['gruplar']['A']:
        return None
    extra = doc.get('ek_bilgiler',{})
    if extra.get('para_birimi','TRY') != 'TRY' or extra.get('ulke','TR') != 'TR':
        return None
    profil = doc['kalemler'][0]['teknik']
    if any(not equal(profil.get(k), v) for k, v in rule['hedef'].items()):
        return None
    observations = []
    unit = rule['birim']
    for row in rows:
        if (row.get('grup') != 'C' or row.get('kdv') or row.get('karma')
                or row.get('para') != 'TRY' or not row.get('kalem_bolum')
                or row.get('teknik_durum') != 'URUN_DOGRULANDI'
                or not row.get('fiyat_kaniti') or not row.get('teklif_cetveli')):
            continue
        teknik = row['teknik']
        if any(not equal(teknik.get(k), v) for k, v in rule['hedef'].items()):
            continue
        item = row['teklif_cetveli']
        if not item.get('alinti'):
            continue
        try:
            miktar = sayi(item['miktar'])
            donusum = None
            if item['birim'] != unit:
                # Dönüşüm yalnız emsalin kendi kaynak teknik bilgisine dayanır.
                donusum = birim_donustur(miktar, item['birim'], unit, teknik.get(rule.get('carpan')))
                miktar = sayi(donusum['miktar'])
            total = sayi(row['fiyat'])
        except ValueError:
            continue
        raw = total / miktar
        index = row.get('endeks_iz')
        comparable = (total * Decimal(index['hedef_endeks']) / Decimal(index['kaynak_endeks']) / miktar
                      if index else raw if row['tarih'][:7] == hedef else None)
        evidence = {key: row[key] for key in ('ikn','tarih','kaynak','kaynak_url','fiyat','ufuk')}
        evidence.update(miktar=str(miktar), kaynak_miktar=item['miktar'], kaynak_birim=item['birim'],
                        alinti=item['alinti'], donusum=donusum, endeks_iz=index)
        observations.append((evidence, raw, comparable))
    if not observations:
        return None

    oran = kdv_orani(ayar)
    scenarios = {}
    for key, divisor in (('haric_varsayimi', Decimal(1)), ('dahil_varsayimi', 1 + oran / 100)):
        visible, within, all_periods = [], [], []
        for evidence, raw, comparable in observations:
            converted = comparable / divisor if comparable is not None else None
            if converted is not None:
                all_periods.append(converted)
                age = evidence['ufuk']
                if age and not age['disinda']:
                    within.append(converted)
            visible.append({**evidence, 'ozgun_birim': para(raw),
                            'kaynak_tarihinde_haric': para(raw / divisor),
                            'ortak_ayda_haric': para(converted) if converted is not None else None})
        scenarios[key] = dict(ufuk_ici=dagilim(within), duyarlilik=dagilim(all_periods), satirlar=visible)
    return dict(oran=str(oran), ay=hedef, birim=unit, **scenarios)
