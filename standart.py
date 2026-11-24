"""Kategori bağımsız dışa aktarım; ham cevabı ve eksikleri korur."""
from copy import deepcopy
from decimal import Decimal,InvalidOperation
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def belge(doc):
    catalog=json.loads((ROOT/'catalog.json').read_text(encoding='utf-8-sig'))
    aliases=json.loads((ROOT/'birim_sozlugu.json').read_text(encoding='utf-8'))['es_adlar']
    value=deepcopy(doc)
    warnings=[]
    for item in value.get('kalemler',[]):
        raw=item.get('birim')
        item['ham_miktar']=item.get('miktar')
        unit=aliases.get(str(raw).strip().casefold(),raw)
        item['birim']=unit
        item['ham_birim']=raw
        if unit not in catalog['birimler']:warnings.append('Birim sözlüğünde bulunmayan değer: '+str(raw))
        try:
            n=Decimal(str(item.get('miktar','')).replace(',','.'))
            if not n.is_finite() or n<=0:raise ValueError()
            item['miktar']=format(n,'f')
        except (InvalidOperation,ValueError):
            item['miktar']=None
            warnings.append('Kalem miktarı tamamlanmalı: '+str(item.get('ad') or 'Adsız kalem'))
        item['teknik_sartlar']=[{'alan':key,'deger':v,'dayanak':item.get('cevaplar',{}).get(key,{}),'durum':'bilinmiyor' if v is None else 'kullanıcı beyanı'} for key,v in item.get('teknik',{}).items()]
    value['standart_surumu']='optibid-1.1'
    value['kategori_yolu']=[value.get('ihale_turu'),*value.get('kategori',[])]
    value['standartlastirma']={'uyarilar':warnings,'kaynak':'Kullanıcının kayıtlı cevabı; resmî teyit değildir.'}
    return value


def disari_aktar(doc):
    from mcp_hesap import calistir
    expected=belge(doc)
    try:
        result,trace=calistir('standart_belge_uret',{'hazirlik':doc},timeout=8)
        if result==expected:
            return dict(result,standartlastirma_izi=trace)
    except Exception:
        pass
    return dict(expected,standartlastirma_izi={'arac':'standart_belge_uret','mod':'yerel'})
