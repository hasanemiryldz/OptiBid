import json
from decimal import Decimal
from pathlib import Path


def oku():
    with Path(__file__).with_suffix('.json').open(encoding='utf-8') as file:
        return json.load(file)


def endeks_yasi(tarih, hedef, ufuk):
    if not tarih or not hedef:
        return None
    try:
        yil, ay = map(int, tarih[:7].split('-'))
        hedef_yil, hedef_ay = map(int, hedef.split('-'))
    except ValueError:
        return None
    fark = (hedef_yil - yil) * 12 + hedef_ay - ay
    return {'ay': fark, 'disinda': abs(fark) > ufuk}


def kdv_orani(ayar):
    oran = Decimal(str(ayar['kdv_orani_yuzde']))
    if not oran.is_finite() or not Decimal(0) <= oran <= Decimal(100):
        raise ValueError('KDV senaryosu oranı 0 ile 100 arasında olmalı.')
    return oran
