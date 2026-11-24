"""OptiBid arşivine salt okunur MCP erişimi."""
from mcp.server.fastmcp import FastMCP
import motor

server = FastMCP("OptiBid-arşiv")

@server.tool()
def belge_ara(sorgu: str, ikn: str = "") -> list[dict]:
    """İzinli EKAP arşivinden gerçek metin, SHA-256 ve satır konumu getirir."""
    from belge_indeksi import ara
    return ara(sorgu,ikn)

@server.tool()
def veri_yeterliligi_kontrol(hazirlik: dict) -> dict:
    """Teknik profil ve emsal sayısının fiyat hesabına uygunluğunu denetler."""
    result = motor.analiz(hazirlik)
    return {"uygun": "medyan" in result,
            "hesap_yapilabilir":bool(result.get('fiyat_referanslari') or result.get('emsaller') or result.get('dosya_fiyat_analizi',{}).get('kullanilan_fiyat')),
            "kosullu_referans_sayisi":len(result.get('fiyat_referanslari',[])),
            "emsal_sayisi": len(result["emsaller"]),
            "durum":result["durum"],"neden":result.get("neden"),"emsaller":[x[0] for x in result["emsaller"]],"referans":{k:v for k,v in result.items() if k!="teklifler"}}

@server.tool()
def fiyat_tahmin_et(hazirlik: dict) -> dict:
    """EKAP dayanağını denetler ve uygun fiyat koşulları varsa hesaplar."""
    return motor.analiz(hazirlik)

@server.tool()
def dosya_fiyatlarini_incele(hazirlik:dict) -> dict:
    """Tüm yüklenen fiyatları okur; seçilen kategori fiyatlarını EKAP teyidinden ayrı sunar."""
    from dosya_fiyatlari import envanter,rapor_icin
    inventory=envanter(hazirlik.get('ek_bilgiler',{}).get('emsal_donemi'))
    return rapor_icin(hazirlik,inventory)

@server.tool()
def teklif_karsilastir(hazirlik: dict) -> dict:
    """Teklif satırlarının tutarlarını ve teknik uyuşmazlıklarını hesaplar."""
    result = motor.analiz(hazirlik)
    return {"teklifler": result["teklifler"]}

@server.tool()
def veri_havuzu_ozeti(sorgu: str = "", baslangic: int = 0) -> dict:
    """Birleşik havuzda ihale adı, kategori ve İKN arar."""
    from veri_merkezi import ara
    if not 0 <= baslangic or len(sorgu)>200:
        raise ValueError("Arama girdisi geçersiz.")
    return ara(sorgu,baslangic)


@server.tool()
def maliyet_senaryosu_hesapla(miktar:str, alis:str, nakliye:str, diger:str, finansman:str, oran:str, esas:str) -> dict:
    """Onaylı satış miktarı ve verilen giderlerle başabaş ve kâr hesaplar."""
    from senaryo import hesap
    return hesap(miktar,alis,nakliye,diger,finansman,oran,esas)

@server.tool()
def birim_donustur(miktar: str,birim: str,hedef: str,paket_carpani: str|None=None) -> dict:
    """Koli ve paket arasında belgeli ambalaj katsayısıyla dönüşüm yapar."""
    from hesap_araclari import birim_donustur as convert
    return convert(miktar,birim,hedef,paket_carpani)

@server.tool()
def fiyat_endeksle(tutar: str,seri: str,kaynak_ay: str,hedef_ay: str|None=None) -> dict:
    """Özgün TRY bedelini, resmî TÜİK serisinin iki ayı arasında taşır."""
    from tuik_endeks import endeksle
    return endeksle(tutar,seri,kaynak_ay,hedef_ay)

@server.tool()
def endeks_durumu(seri: str) -> dict:
    """Yerel resmî TÜİK endeks tablosunu ve son kayıtlı dönemi gösterir."""
    from tuik_endeks import bilgi
    return bilgi(seri)

@server.tool()
def analiz_durumu_getir(rapor_id: str = '', rev: int = 0, tarih: str = '') -> dict:
    """Genel veri durumunu veya belirtilen kalıcı rapor sürümünün dışlama nedenlerini okur."""
    from senaryo import durum_bilgisi
    if not rapor_id:
        return durum_bilgisi(None)
    import os
    from pathlib import Path
    import kayitlar
    path=Path(os.environ.get('OPTIBID_HAZIRLIK_DB',motor.ROOT/'data/hazirliklar.db'))
    if not path.is_file():
        raise ValueError('Rapor veritabanı bulunamadı.')
    with kayitlar.connection(path) as db:
        snap=kayitlar.snapshot(db,rapor_id)
    if not snap or snap['tarih']!=tarih or snap['belge']['rev']!=rev:
        raise ValueError('İstenen rapor sürümü değişti.')
    return durum_bilgisi(snap)


@server.tool()
def ilgili_dosya_kayitlarini_ara(sorgu:str='',tur:str='',kategori:list[str]|None=None) -> dict:
    """Dosyalardaki bütün fiyatları tarar, ilgili kalemleri kaynak ve teyit durumuyla getirir."""
    from dosya_fiyatlari import ilgili_kayitlar
    return ilgili_kayitlar(sorgu,tur,kategori)

@server.tool()
def internet_ihale_ara(sorgu:str) -> dict:
    """Gerçek arama sağlayıcısıyla yalnız EKAP adresli benzer ihale adaylarını bulur. Fiyat teyidi üretmez."""
    from arastirma import bul
    return bul(sorgu)

@server.tool()
def internet_kaynagini_oku(url:str) -> dict:
    """Yalnız resmî EKAP sayfasının okunabilir metnini getirir; dinamik/engelli içeriği okunmuş saymaz."""
    from arastirma import oku
    return oku(url)

@server.tool()
def standart_belge_uret(hazirlik:dict) -> dict:
    """Kalem ve birimleri ortak JSON şemasına dönüştürür, ham cevapları ve dayanakları korur."""
    from standart import belge
    return belge(hazirlik)

if __name__ == "__main__":
    server.run(transport="stdio")


