"""Para ve birim hesapları için Decimal tabanlı ortak kurallar."""
from decimal import Decimal, InvalidOperation

def sayi(value, min_value=0):
    try:
        n=Decimal(str(value))
    except (InvalidOperation,ValueError,TypeError):
        raise ValueError('Geçerli bir sayısal değer girin.') from None
    if not n.is_finite() or n<=min_value or n>10**15:
        raise ValueError('Sayısal değer izin verilen aralığın dışında.')
    return n

def birim_donustur(miktar,birim,hedef,paket_carpani=None):
    quantity=sayi(miktar)
    if birim==hedef and birim in ('koli','paket'):
        factor=Decimal(1)
    elif {birim,hedef}=={'koli','paket'}:
        pack=sayi(paket_carpani)
        if pack!=pack.to_integral_value():
            raise ValueError('Koli başına tam paket sayısı gerekli.')
        factor=pack if birim=='koli' else Decimal(1)/pack
        if birim=='paket':
            return {'miktar':str(quantity/pack),'birim':hedef,'islem':'bölme','paket_carpani':str(pack)}
    else:
        raise ValueError('Bu birimler arasında belgeli dönüşüm yok.')
    return {'miktar':str(quantity*factor),'birim':hedef,'islem':'çarpma','paket_carpani':str(factor)}

def sozlesme_birimine_bol(tutar,miktar,birim):
    """Aynı kapsamı kaynakta bağlanmış sözleşme toplamının birim karşılığı."""
    return dict(tutar=str(round(sayi(tutar)/sayi(miktar),2)),birim=birim)


def fiyat_endeksle(tutar,kaynak_endeks,hedef_endeks):
    amount=sayi(tutar)
    base=sayi(kaynak_endeks)
    end=sayi(hedef_endeks)
    factor=end/base
    # Oranı rapor için yaz, hesapta ara kuruş yuvarlaması uygulama.
    return {'carpan':str(factor),'tutar_endeksli':str(round(amount*end/base,2))}
