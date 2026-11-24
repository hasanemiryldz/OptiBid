"""Canlı emsal havuzu ve deterministik fiyat hesabı."""
from contextlib import closing
from datetime import date
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import logging
import os
from pathlib import Path
import sqlite3
from statistics import median
from urllib.parse import urlsplit
import re
import unicodedata
from veri_yollari import ARCHIVE, DATA

ROOT = Path(__file__).resolve().parent
POOL = Path(os.environ.get("OPTIBID_HAVUZ", DATA / "havuz.db"))
SEARCH = "https://ekap.kik.gov.tr/EKAP/Ortak/ihaleArama/index.html"
METHOD = "C17 ile ortak aya taşınmış eşit ağırlıklı emsal medyanı"

def number(value):
    try:
        n = Decimal(str(value).strip().replace(",", "."))
        return n if n.is_finite() and 0 < n <= Decimal("1e15") else None
    except InvalidOperation:
        return None

def table(db):
    db.execute("""CREATE TABLE IF NOT EXISTS kullanici_emsalleri(
        ikn TEXT PRIMARY KEY, veri TEXT NOT NULL)""")

def add(raw, pool=None):
    from re import fullmatch
    ikn = str(raw.get("ikn","")).strip()
    source = urlsplit(str(raw.get("kaynak","")).strip())
    if not fullmatch(r"20\d{2}/[1-9]\d{0,8}", ikn) or source.scheme not in ("http","https") or not source.hostname:
        raise ValueError("İKN ve bir kaynak bağlantısı girin.")
    if raw.get("dogrulandi") is not True or raw.get("ornek_veri"):
        raise ValueError("Gerçek fiyatı, tek kalemi ve teknik bilgileri kaynakta doğrulayın.")
    category = raw.get("kategori")
    catalog = json.loads((ROOT/"catalog.json").read_text(encoding="utf-8-sig"))
    fields = catalog["turler"].get(raw.get("tur"),{}).get(category[0],{}).get(category[1]) if isinstance(category,list) and len(category)==2 else None
    if fields is None:
        raise ValueError("Geçerli bir tür ve kategori seçin.")
    when = date.fromisoformat(raw.get("tarih","")).isoformat()
    quantity, price = number(raw.get("miktar")),number(raw.get("fiyat"))
    if not quantity or not price or raw.get("birim") not in catalog["birimler"]:
        raise ValueError("Pozitif miktar, fiyat ve geçerli birim gerekli.")
    if raw.get("kdv") not in ("hariç","dahil","belirsiz") or raw.get("fiyat_turu") not in ("sözleşme toplamı","sözleşme birim"):
        raise ValueError("KDV esası ve sözleşme fiyat türü seçin.")
    tech = raw.get("teknik",{})
    region = str(raw.get("ulke","")).strip().upper()
    currency = str(raw.get("para","")).strip().upper()
    if not fullmatch("[A-Z]{2}",region) or not fullmatch("[A-Z]{3}",currency):
        raise ValueError("Ülke ve para birimi kodları gerekli.")
    row = dict(ikn=ikn,kaynak=source.geturl(),tarih=when,tur=raw["tur"],kategori=category,
               miktar=str(quantity),fiyat=str(price),birim=raw["birim"],kdv=raw["kdv"],
               fiyat_turu=raw["fiyat_turu"],ulke=region,para=currency,teknik={k:tech.get(k) for k in fields},
               kalite="Kullanıcı kaynak doğrulaması", yeni=True)
    with closing(sqlite3.connect(pool or POOL)) as db, db:
        table(db)
        previous=db.execute("SELECT veri FROM kullanici_emsalleri WHERE ikn=?",(ikn,)).fetchone()
        if previous and json.loads(previous[0])!=row:
            raise ValueError("Bu İKN için farklı bir kullanıcı emsali kayıtlı.")
        db.execute("INSERT OR IGNORE INTO kullanici_emsalleri VALUES (?,?)",(ikn,json.dumps(row,ensure_ascii=False)))
    return row

def _archive_profile(product, record, raw_tech, rules, catalog):
    kind, category = record.get('tur'), record.get('kategori')
    if isinstance(category,list) and len(category)==2:
        labels = catalog['turler'].get(kind, {}).get(category[0], {}).get(category[1])
        if labels is not None:
            tech = record.get('teknik') or raw_tech
            return kind, category, {name:tech.get(name) for name in labels}
    product_key = unicodedata.normalize('NFKD',(product or '').casefold().replace('ı','i'))
    product_key = ''.join(c for c in product_key if not unicodedata.combining(c))
    matching = [r for r in rules if re.search(r['urun_deseni'], product_key)]
    if len(matching) != 1:
        return None, [], {}
    rule, = matching
    result = {}
    for name,key in rule['teknik_alanlari'].items():
        value = raw_tech.get(key)
        if name in rule.get('deger_eslemeleri',{}):
            value = rule['deger_eslemeleri'][name].get('x'.join(map(str,value)) if isinstance(value,list) else str(value))
        result[name] = value
    return rule['tur'], rule['kategori'], result


def _read_archive(series):
    archive = {}
    if not ARCHIVE.is_file():
        logging.warning('OptiBid arşivi bulunamadı: %s',ARCHIVE)
        return {}, archive
    config = json.loads((ROOT/'arsiv_profilleri.json').read_text(encoding='utf-8'))
    catalog = json.loads((ROOT/'catalog.json').read_text(encoding='utf-8-sig'))
    with closing(sqlite3.connect(ARCHIVE.as_uri()+"?mode=ro",uri=True)) as db:
        indices=dict(db.execute("SELECT ay,endeks FROM endeksler WHERE seri=?",(series,)))
        for ikn,when,amount,unit,price,currency,status,tech,product,record in db.execute(
            "SELECT ikn,ihale_tarihi,miktar,birim,sozlesme_bedeli,para_birimi,durum,teknik_json,urun,kayit_json FROM ihaleler"
        ):
            raw = json.loads(record or '{}')
            kind, categories, technical = _archive_profile(product,raw,json.loads(tech or '{}'),
                                                            config['kalem_eslesmeleri'],catalog)
            archive[ikn]=dict(ikn=ikn,tur=kind,kategori=categories,tarih=when,miktar=amount,
                birim=unit,fiyat=price,para=currency,ulke=raw.get('ulke','TR'),
                kdv=raw.get('kdv') if raw.get('kdv') in ('hariç','dahil') else None,
                fiyat_turu=raw.get('fiyat_turu','sözleşme toplamı'),kalite=status,kaynak=SEARCH,yeni=False,
                teknik=technical,siniflandirma='sınıflandı' if categories else 'sınıflanmadı')
        for ikn,dosya,metin in db.execute("SELECT ikn,dosya,metin FROM belgeler WHERE dosya LIKE '%sozlesme_tasarisi%'"):
            if ikn not in archive or archive[ikn]["kalite"]!="URUN_DOGRULANDI":
                continue
            for no,line in enumerate(metin.splitlines(),1):
                if "katma değer vergisi" in line.casefold() and "sözleşme bedeline dahil olmayıp" in line.casefold():
                    archive[ikn]["kdv_belgesi"]={"dosya":dosya,"satir":no,"alinti":line.strip()}
                    break
    return indices, archive


def read(pool, series):
    indices, archive = _read_archive(series)
    rows=archive.copy()
    manifest=json.loads((ROOT/"kaynaklar.json").read_text(encoding="utf-8-sig"))
    meta={r["ikn"]:r for r in manifest}
    for entry in manifest:
        rows.setdefault(entry["ikn"],dict(ikn=entry["ikn"],tur=entry.get("tur"),kategori=entry.get("kategori_yolu",entry["kategori"]),
            tarih=entry.get("tarih"),miktar=entry.get("miktar"),birim=entry.get("birim"),fiyat=entry.get("fiyat"),para=entry.get("para"),
            ulke="TR",kdv=None,fiyat_turu="sözleşme toplamı",kalite=entry.get("kalite","İlan referansı"),
            kaynak=entry["url"],teknik={},yeni=True))
    if not Path(pool).is_file():
        return indices,[rows[key] for key in sorted(rows)]
    with closing(sqlite3.connect(Path(pool).resolve().as_uri()+'?mode=ro',uri=True)) as db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='kayit'").fetchone():
            db.row_factory=sqlite3.Row
            for raw in db.execute("SELECT * FROM kayit"):
                row=dict(raw)
                if row["ikn"] not in archive:
                    info=meta.get(row["ikn"],{})
                    row.update(tur=info.get("tur"),kategori=info.get("kategori_yolu",row["kategori"]),
                               teknik={},kdv=None,yeni=True)
                    rows[row["ikn"]]=row
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='kullanici_emsalleri'").fetchone():
            for raw, in db.execute("SELECT veri FROM kullanici_emsalleri"):
                row=json.loads(raw)
                old=rows.get(row["ikn"])
                if not old or old.get("kalite")!="URUN_DOGRULANDI":
                    rows[row["ikn"]]=row
    return indices,[rows[key] for key in sorted(rows)]

def equal(a,b):
    if a is None or b is None:
        return False
    return number(a)==number(b) if number(a) is not None and number(b) is not None else str(a).strip().casefold()==str(b).strip().casefold()

def calculate(doc, rule, pool=None):
    indices,rows=read(pool or POOL,rule["endeks"])
    if doc.get("ek_bilgiler",{}).get("kdv_esasi")=="hariç":
        from alim_emsal import adaylar
        indexed={r["ikn"]:r for r in rows}
        for r in adaylar(rule):
            old=indexed.get(r["ikn"])
            if old and (old.get("kdv") not in (None,"belirsiz") or
                        any(old.get(k) and not equal(old[k],r[k]) for k in ("tarih","miktar","birim","fiyat","para"))):
                continue
            if old and old.get("kdv_belgesi"):
                r["kdv_belgesi"]=old["kdv_belgesi"]
            indexed[r["ikn"]]=r
        rows=[indexed[k] for k in sorted(indexed)]
    review_file=ROOT/"kagit_kosullu_emsaller.json"
    review=json.loads(review_file.read_text(encoding="utf-8-sig")) if review_file.exists() else {}
    version=sha256(json.dumps([indices,rows,rule,review],sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:16]
    out=dict(durum="Yetersiz veri",emsaller=[],emsal_ayrinti=[],haric=[],yeni_kayit=0,
             veri_surumu=version,yontem=METHOD,aday_sayisi=len(rows),dislanan=[],secim_emsalleri=[])
    if not indices or len(doc["kalemler"])!=1:
        return out
    item=doc["kalemler"][0]
    tech=item["teknik"]
    if not all(equal(tech.get(key),value) for key,value in rule["hedef"].items()):
        out["neden"]="Teknik profil eksik veya doğrulanmış emsal kapsamı dışında."
        out["haric"]=[[row["ikn"],out["neden"]] for row in rows]
        out["dislanan"]=[dict(ikn=row["ikn"],neden=out["neden"],grup="inceleme") for row in rows]
        return out
    target=doc.get("ek_bilgiler",{})
    expanded=target.get("emsal_kapsami")=="genis"
    out["emsal_kapsami"]="genis" if expanded else "dogrulanmis"
    vat=target.get("kdv_esasi") or "belirsiz"
    currency=target.get("para_birimi") or "TRY"
    country=target.get("ulke") or "TR"
    month=max(indices)
    canonical=rule["birim"]
    target_factor=number(tech.get(rule["carpan"])) if item["birim"]==rule["ambalaj"] else (
        Decimal(1) if item["birim"] in (canonical,"top") else None)
    target_quantity=number(item.get("miktar"))
    if target_quantity and target_factor and target_factor==target_factor.to_integral_value():
        out["standart_miktar"]=str(target_quantity*target_factor)
    excluded=set(target.get("rapor_haric",[]))
    prices=[]
    scenarios=[]
    for row in rows:
        ikn=row["ikn"]
        amount, price=number(row.get("miktar")),number(row.get("fiyat"))
        original_month=(row.get("tarih") or "")[:7]
        unit=row.get("birim")
        factor=number(row["teknik"].get(rule["carpan"])) if unit==rule["ambalaj"] else (
            Decimal(1) if unit in (canonical,"top") else None)
        evidence=review.get(ikn) if row["kalite"]=="KOSULLU" and not row["yeni"] else None
        conditional=bool(evidence and expanded and equal(row["teknik"].get("Paketteki yaprak sayısı"), 500)
                         and rule["hedef"].get("Gramaj (g/m²)")=="80"
                         and rule["hedef"].get("Boyut")=="A4")
        reason=None
        if ikn==str(target.get("ikn","")).strip():
            reason="Hedef ihalenin kendi sonucu"
        elif not amount or not price:
            reason="Karşılaştırılabilir sözleşme fiyatı veya miktar eksik"
        elif row["kategori"]!=doc["kategori"] or row["tur"]!=doc["ihale_turu"]:
            reason="Tür veya kategori farklı"
        elif not conditional and row["kalite"] not in ("URUN_DOGRULANDI","Kullanıcı kaynak doğrulaması","Veri seti · iç tutarlı"):
            reason="Teknik doğrulama eksik: "+row["kalite"]
        elif not all(equal(row["teknik"].get(a),v) or (conditional and a in ("Gramaj (g/m²)","Boyut"))
                     for a,v in rule["hedef"].items()):
            reason="Teknik kapsam farklı veya eksik"
        elif row["para"]!=currency or row["ulke"]!=country or country!="TR" or currency!="TRY":
            reason="Ülke, para birimi veya endeks kapsamı farklı"
        elif (row["kdv"] or "belirsiz")!=vat:
            reason="KDV esası farklı veya belirsiz"
        elif not factor or (factor!=1 and factor!=factor.to_integral_value()):
            reason="Doğrulanmış birim dönüşümü yok"
        elif original_month not in indices:
            reason="Fiyat tarihi C17 kapsamı dışında"
        if reason:
            out["haric"].append([ikn,reason])
            group="seçim" if ikn in excluded else "kapsam" if (
                ikn==str(target.get("ikn","")).strip() or
                row["kategori"]!=doc["kategori"] or row["tur"]!=doc["ihale_turu"] or
                row["ulke"]!=country or row["para"]!=currency
            ) else "inceleme"
            out["dislanan"].append(dict(ikn=ikn,neden=reason,grup=group))
            continue
        multiplier=Decimal(indices[month])/Decimal(indices[original_month])
        unit_price=(price/amount if row["fiyat_turu"]=="sözleşme toplamı" else price)/factor
        converted=unit_price*multiplier
        normalized_quantity=amount*factor
        raw_unit=price/amount if row["fiyat_turu"]=="sözleşme toplamı" else price
        detail=dict(ikn=ikn,kaynak=row["kaynak"],tarih=row["tarih"],birim=unit,
            fiyat=str(price),fiyat_turu=row["fiyat_turu"],miktar=str(amount),kdv=row["kdv"],yeni=row["yeni"],
            seri=rule["endeks"],kaynak_ay=original_month,hedef_ay=month,
            kaynak_endeks=indices[original_month],hedef_endeks=indices[month],
            tarih_carpani=str(multiplier),birim_carpani=str(factor),donusturulmus=str(round(converted,2)),
            ham_birim=str(round(raw_unit,2)),ham_paket=str(round(unit_price,2)),paket_miktari=str(normalized_quantity),
            kosul=evidence if conditional else None)
        if row.get("kdv_belgesi") and row["kdv"]=="hariç":
            detail.update(tier=rule.get("preferred_comparability_tier","TIER1"),kdv_belgesi=row["kdv_belgesi"])
        if "satir" in row:
            detail.update(kaynak_sinifi=row["kalite"],satir=row["satir"],dosya_sha256=row["dosya_sha256"],
                          teknik=row["teknik"],alan_kaynaklari=row["alan_kaynaklari"],
                          yuklenici=row.get("yuklenici"),yuklenici_kaynagi=row.get("yuklenici_kaynagi"))
        if ikn in excluded:
            reason="Rapor seçiminden çıkarıldı"
            out["haric"].append([ikn,reason])
            out["dislanan"].append(dict(ikn=ikn,neden=reason,grup="seçim"))
            out["secim_emsalleri"].append(detail)
            continue
        prices.append(converted)
        scenarios.append((row["tarih"],normalized_quantity,converted))
        out["emsaller"].append([ikn,row["tarih"],str(round(converted,2))])
        out["emsal_ayrinti"].append(detail)
    out.update(ay=month,birim=canonical,kdv=vat,yeni_kayit=sum(x["yeni"] for x in out["emsal_ayrinti"]))
    tier_ids=[r["ikn"] for r in out["emsal_ayrinti"] if r.get("tier")=="TIER1"]
    minimum=rule.get("minimum_comparables",20)
    out.update(tier1_ikn=tier_ids,tier1_sayisi=len(tier_ids),tier1_hedefi=minimum,
               tier1_hedef_karsilandi=len(tier_ids)>=minimum,
               kategori_adayi=sum(row["kategori"]==doc["kategori"] and row["tur"]==doc["ihale_turu"] for row in rows))
    if out["tier1_hedef_karsilandi"]:
        chosen=set(tier_ids)
        for row in out["emsal_ayrinti"]:
            if row["ikn"] not in chosen:
                reason="Tier1 hedefi karşılandığı için genişletilmiş referans dışında bırakıldı"
                out["haric"].append([row["ikn"],reason])
                out["dislanan"].append(dict(ikn=row["ikn"],neden=reason,grup="kapsam"))
        prices=[price for price,row in zip(prices,out["emsal_ayrinti"]) if row["ikn"] in chosen]
        scenarios=[scenario for scenario,row in zip(scenarios,out["emsal_ayrinti"]) if row["ikn"] in chosen]
        out["emsaller"]=[row for row in out["emsaller"] if row[0] in chosen]
        out["emsal_ayrinti"]=[row for row in out["emsal_ayrinti"] if row["ikn"] in chosen]
        out["yeni_kayit"]=sum(x["yeni"] for x in out["emsal_ayrinti"])
    out["kosullu_sayisi"]=sum(bool(x["kosul"]) for x in out["emsal_ayrinti"])
    if len(prices)>=3:
        center=median(prices)
        out.update(durum="Emsal temelli tahmin",medyan=str(round(center,2)),
                   alt=str(round(min(prices),2)),ust=str(round(max(prices),2)))
        total=None
        if target_quantity and target_factor and target_factor==target_factor.to_integral_value():
            total=center*target_quantity*target_factor
            out["toplam"]=str(round(total,2))
        rate=Decimal(0) if str(target.get("kdv_orani")) in ("0","0.0") else number(target.get("kdv_orani"))
        if rate is not None and rate<=100:
            tax=1+rate/100
            choices=[]
            for basis in (("hariç","dahil") if vat=="belirsiz" else (vat,)):
                net=center if basis=="hariç" else center/tax
                gross=center*tax if basis=="hariç" else center
                choices.append(dict(esas=basis,haric=str(round(net,2)),dahil=str(round(gross,2)),
                    toplam_haric=str(round(total if basis=="hariç" else total/tax,2)) if total is not None else None,
                    toplam_dahil=str(round(total*tax if basis=="hariç" else total,2)) if total is not None else None))
            out["kdv_senaryolari"]=choices
        def scenario(label, values):
            return dict(ad=label,n=len(values),fiyat=str(round(median(values),2)) if len(values)>=3 else None)
        out["kontroller"]=[scenario("Yalnız "+year,[x[2] for x in scenarios if x[0][:4]==year])
                            for year in sorted({x[0][:4] for x in scenarios})]
        if total is not None:
            near=sorted(scenarios,key=lambda x:abs(x[1]-target_quantity*target_factor))[:3]
            out["kontroller"].append(scenario("Miktara en yakın üç emsal",[x[2] for x in near]))
        if len(prices)>3:
            checks=[median(prices[:i]+prices[i+1:]) for i in range(len(prices))]
            out["tek_cikarma"]=[str(round(min(checks),2)),str(round(max(checks),2))]
    else:
        out.update(durum="Yalnız emsal referansı" if prices else "Yetersiz veri",
                   neden="Tahmin için en az üç uygun emsal gerekli.")
    return out


