"""Ürün serilerini ve resmî TÜİK dosyasından alınan aylık düzeyleri okur."""
import json
import os
from pathlib import Path
import re
from hesap_araclari import fiyat_endeksle
from veri_yollari import DATA

ROOT=Path(__file__).resolve().parent

def kategori_serisi(tur,kategori):
    paths=json.loads((ROOT/'kategori_endeks.json').read_text(encoding='utf-8-sig'))
    return paths.get('/'.join([tur,*kategori]))


def seriler():
    p=Path(os.environ.get('OPTIBID_TUIK_VERI',DATA/'tuik/yi_ufe.json'))
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding='utf-8'))['seriler']

def bilgi(seri):
    value=seriler().get(seri)
    if not value:
        raise ValueError('Bu kategori için resmî TÜİK serisi kayıtlı değil.')
    return {k:v for k,v in value.items() if k!='noktalar'}

def endeksle(tutar,seri,kaynak_ay,hedef_ay=None,*,dataset=None):
    series=(seriler() if dataset is None else dataset).get(seri)
    if not series:
        raise ValueError('Bu kategori için resmî TÜİK serisi kayıtlı değil.')
    if series.get('baz')!=2003 or series.get('seri')!=seri:
        raise ValueError('Seri kodu veya 2003 baz yılı doğrulanamadı.')
    target=hedef_ay or series['son_ay']
    if any(not isinstance(m,str) or not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])',m) for m in (kaynak_ay,target)):
        raise ValueError('Endeks dönemi YYYY-AA biçiminde olmalı.')
    months=series['noktalar']
    if target not in months or kaynak_ay not in months:
        raise ValueError('Kaynak veya hedef aya ait yayımlanmış endeks yerel tabloda bulunamadı.')
    a,b=months[kaynak_ay],months[target]
    result=fiyat_endeksle(tutar,a['deger'],b['deger'])
    return {**result,'seri':seri,'kaynak_ay':kaynak_ay,'hedef_ay':target,'kaynak_endeks':a['deger'],
            'hedef_endeks':b['deger'],'kaynak_hucre':a['hucre'],'hedef_hucre':b['hucre'],
            'baz':series['baz'],'index_source_policy':'TUIK_OFFICIAL',
            'veri_surumu':series['dosya_sha256'],'bulten':series['bulten'],
            'yayim_tarihi':series.get('yayim_tarihi'),'aktarim_zamani':series.get('aktarim_zamani')}
