"""Yerel aktarım veritabanından iç kontrolü geçen sözleşme satırlarını okur."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3

ROOT=Path(__file__).resolve().parent
def adaylar(rule):
    kaynak=rule.get("alim_kaynagi")
    if not kaynak:
        return []
    dbpath=ROOT/kaynak["dosya"]
    if not dbpath.is_file():
        return []
    with closing(sqlite3.connect(dbpath.as_uri()+"?mode=ro",uri=True)) as db:
        sql="""SELECT s.ikn,s.satir_no,s.alanlar_json,s.dogrulama_durumu,
                      t.alan,t.deger_json,t.kaynak
               FROM standart_kayit s JOIN tamamlanan_alan t USING(dosya_sha256,satir_no)
               WHERE s.dosya_sha256=? ORDER BY s.satir_no,t.alan"""
        rows={}
        for ikn,no,values,status,k,v,ref in db.execute(sql,(kaynak["sha256"],)):
            if no not in rows:
                rows[no]=(ikn,json.loads(values),status,{}, {})
            rows[no][3][k]=json.loads(v)
            rows[no][4][k]=ref
    result=[]
    for no,(ikn,r,status,t,refs) in rows.items():
        if (r.get("kaynak_sinifi")!=kaynak["sinif"] or status!="ic_tutarli"
            or r.get("gozlem_turu")!="sozlesme_bedeli" or t.get("kdv_esasi")!="KDV Hariç"
            or t.get("kalem_kaynagi")!="Toplam Sözleşme Bedeli (Tek Kalem)"
            or t.get("boyut")!="A4 (210x297 mm)" or t.get("gramaj")!=80 or t.get("yaprak_paket")!=500):
            continue
        result.append(dict(ikn=ikn,tur=rule["tur"],kategori=rule["kategori"],tarih=r["ihale_tarihi"],
            miktar=r["miktar"],birim=r["birim"],fiyat=r["sozlesme_toplami"],para=r["para"],ulke="TR",
            kdv="hariç",fiyat_turu="sözleşme toplamı",kalite="Veri seti · iç tutarlı",yeni=True,
            kaynak="/api/veri-dayanagi/"+ikn,teknik={"Boyut":"A4","Gramaj (g/m²)":t["gramaj"],"Paketteki yaprak sayısı":t["yaprak_paket"]},
            satir=no,dosya_sha256=kaynak["sha256"],alan_kaynaklari=refs,
            yuklenici=t.get("yuklenici"),yuklenici_kaynagi=refs.get("yuklenici")))
    return result
