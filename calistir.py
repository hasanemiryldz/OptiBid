"""OptiBid yerel sunucusu. Python 3, ek paket gerektirmez."""
import json
import logging
import kayitlar
from concurrent.futures import Future
from decimal import Decimal
import sqlite3
from excel import excel
import motor
import havuz
import emsal
import os
import re
import shutil
import subprocess
import threading
from urllib.request import urlopen
from urllib.parse import unquote
import ajan
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("OPTIBID_HAZIRLIK_DB", ROOT / "data" / "hazirliklar.db"))

if "OPTIBID_HAZIRLIK_DB" not in os.environ:
    os.environ["OPTIBID_HAZIRLIK_DB"]=str(DATA)

ANALYSES = {}
ANALYSIS_LOCK = threading.Lock()

def analyze_once(doc):
    key = json.dumps(doc, sort_keys=True, ensure_ascii=False)
    with ANALYSIS_LOCK:
        future = ANALYSES.get(key)
        owner = future is None
        if owner:
            future = ANALYSES[key] = Future()
    if not owner:
        return future.result(timeout=92)
    try:
        result = ajan.analiz(doc)
        future.set_result(result)
        return result
    except Exception as error:
        future.set_exception(error)
        raise
    finally:
        with ANALYSIS_LOCK:
            del ANALYSES[key]

def _rapor_sayilari(report):
    def alanlar(row, keys):
        return {k: str(Decimal(str(row[k])).normalize()) if row.get(k) is not None else None
                for k in keys}

    scenarios = report.get('kdv_senaryolari') or {}
    return {
        **alanlar(report, ('medyan', 'alt', 'ust', 'toplam', 'standart_miktar')),
        'ay': report.get('ay'),
        'birim': report.get('birim'),
        'para_birimi': report.get('para_birimi'),
        'kdv': report.get('kdv'),
        'kaynak_politikasi': report.get('source_policy'),
        'kalem_sayilari': [{**_rapor_sayilari(row['sonuc']), 'id':row['id'],'mukerrer':row['mukerrer']}
                        for row in report.get('kalem_sonuclari',[])],
        'emsaller': {r[0]: alanlar({'birim_fiyat':r[2]}, ('birim_fiyat',)) for r in report.get('emsaller', [])},
        'nominal': {r['ikn']: {**alanlar(r, ('fiyat',)),
            'ozgun': alanlar(r.get('turetilmis_birim') or {}, ('tutar',)),
            'endeksli': alanlar(r.get('endeksli_birim') or {}, ('tutar',))}
            for r in report.get('nominal', [])},
        'ayri_sozlesmeler':[{**alanlar(row,('tutar',)),
                             **{k:row.get(k) for k in ('ikn','sira','para','tarih','konum','url','kdv')}}
                            for row in report.get('ayri_sozlesmeler',[])],
        'kosullu': {str([r['birim'], r['kdv'], r['ay']]): alanlar(r, ('sayi','alt','medyan','ust'))
                    for r in report.get('kosullu_ozetler', [])},
        'uygun_senaryolar': {k: {
            'ufuk_ici': alanlar(scenarios[k]['ufuk_ici'], ('sayi', 'alt', 'medyan', 'ust')),
            'duyarlilik': alanlar(scenarios[k]['duyarlilik'], ('sayi', 'alt', 'medyan', 'ust')),
            'satirlar': {r['ikn']: alanlar(r, ('ozgun_birim', 'kaynak_tarihinde_haric', 'ortak_ayda_haric'))
                         for r in scenarios[k]['satirlar']}}
            for k in ('haric_varsayimi', 'dahil_varsayimi') if k in scenarios}
    }


def rapor_hesapla(doc):
    from mcp_hesap import calistir
    mcp_numbers = None
    result = None
    try:
        result, trace = calistir('fiyat_tahmin_et', {'hazirlik':doc})
        mcp_numbers = _rapor_sayilari(result)
    except Exception:
        reason = 'MCP doğrulaması yapılamadı'
        logging.exception('MCP fiyat raporu aracı başarısız')
    try:
        expected = motor.analiz(doc)
        local_numbers = _rapor_sayilari(expected)
    except (TypeError, KeyError, ValueError, AttributeError):
        raise
    except Exception:
        logging.exception('Yerel fiyat raporu hesaplanamadı')
        return dict(durum='Kısmi rapor', neden='Raporun fiyat hesabı yerelde doğrulanamadı. Yeniden deneyin.',
                    source_policy='EKAP_ONLY', modul_hatalari={'yerel':'Doğrulama başarısız'},
                    hesap_izi={'mcp_dogrulandi':False,'mcp_sayilari':mcp_numbers,'yerel_sayilari':None})
    if mcp_numbers is not None:
        if mcp_numbers == local_numbers and result.get('veri_surumu') == expected.get('veri_surumu'):
            return dict(result, hesap_izi={**trace, 'mcp_dogrulandi':True})
        reason = 'MCP sonucu yerel hesapla uyuşmadı'
        logging.warning('%s', reason)
    expected['hesap_izi'] = {
        'arac':'yerel_decimal_motoru', 'mcp_dogrulandi':False, 'mod':'yerel',
        'neden':reason, 'mcp_sayilari':mcp_numbers, 'yerel_sayilari':local_numbers
    }
    return expected


def rapor_parametreleri(saved,requested):
    """Raporun açık senaryo alanlarını uygula. Hazırlık ve belge kökeni veritabanından gelir."""
    options=requested.get('ek_bilgiler') or {}
    extra=saved.setdefault('ek_bilgiler',{})
    vat=options.get('kdv_esasi')
    if vat in ('hariç','dahil','belirsiz'):
        extra['kdv_esasi']=vat
    if 'rapor_haric' in options:
        exclusions=options['rapor_haric']
        if not isinstance(exclusions,list) or len(exclusions)>5000 or any(
                not isinstance(v,str) or not 0<len(v)<=64 for v in exclusions):
            raise ValueError('Dışlanan kayıt listesi geçersiz.')
        extra['rapor_haric']=list(dict.fromkeys(exclusions))
    items=requested.get('kalemler')
    if len(saved['kalemler'])==1 and isinstance(items,list) and len(items)==1:
        original,=saved['kalemler']
        proposed,=items
        if original['id']==proposed.get('id'):
            quantity=proposed.get('miktar')
            if quantity is not None and str(quantity)!=str(original.get('miktar')):
                if not re.fullmatch(r'\d{1,15}(?:\.\d{1,6})?',str(quantity)) or Decimal(str(quantity))<=0:
                    raise ValueError('Rapor miktarı geçersiz.')
                original['miktar']=str(quantity)
            key='Kolideki paket sayısı'
            pack=(proposed.get('teknik') or {}).get(key)
            if original.get('birim')=='koli' and pack is not None and str(pack)!=str(original.get('teknik',{}).get(key)):
                if not re.fullmatch(r'[1-9]\d{0,5}',str(pack)):
                    raise ValueError('Rapor paket katsayısı geçersiz.')
                original['teknik'][key]=str(pack)
    return saved


class Handler(BaseHTTPRequestHandler):
    def local_request(self):
        port=self.server.server_port
        hosts=(f'127.0.0.1:{port}',f'localhost:{port}')
        origin=self.headers.get('Origin')
        return self.headers.get('Host') in hosts and (not origin or origin in tuple('http://'+x for x in hosts))

    def send_data(self, code, data, mime="application/json"):
        raw = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", mime + "; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if not self.local_request():
            return self.send_data(403,{'hata':'OptiBid işlemleri yerel uygulamadan yapılır.'})
        if self.path.startswith('/api/sartname-sayfalari/'):
            from sartname import sayfalar
            try:
                with kayitlar.connection(DATA) as db:
                    pages, name = sayfalar(db,self.path.rsplit('/',1)[-1])
            except (ValueError, FileNotFoundError) as error:
                return self.send_data(404, {'hata':str(error)})
            return self.send_data(200, {'sayfalar':pages, 'ad':name})
        if self.path == '/api/ornekler':
            examples=motor.oku('ornek_senaryolar.json')
            return self.send_data(200,[{k:v for k,v in row.items() if k!='dosya'} for row in examples])
        if self.path.startswith('/api/ornek/'):
            key=self.path.rsplit('/',1)[-1]
            row=next((r for r in motor.oku('ornek_senaryolar.json') if r['id']==key),None)
            return self.send_data(200,motor.oku(row['dosya'])) if row else self.send_data(404,{'hata':'Örnek bulunamadı.'})
        if self.path == '/api/arastirma-durumu':
            from arastirma import durum
            return self.send_data(200,durum())
        if self.path.startswith('/api/standart/'):
            try:
                key=str(UUID(self.path.rsplit('/',1)[-1]))
                with kayitlar.connection(DATA) as db:
                    row=db.execute('SELECT doc FROM hazirliklar WHERE id=? AND id NOT IN (SELECT id FROM silinen_hazirliklar)',(key,)).fetchone()
                if not row:return self.send_data(404,{'hata':'Hazırlık bulunamadı.'})
                from standart import disari_aktar
                return self.send_data(200,disari_aktar(json.loads(row[0])))
            except ValueError:return self.send_data(400,{'hata':'Hazırlık kimliği geçersiz.'})
        if self.path == "/api/ayarlar":
            from ollama_ayar import durum
            return self.send_data(200,durum())
        if self.path == "/api/saglik":
            from baslat import SETTINGS
            from mcp_hesap import durum as mcp_durumu
            from ollama_ayar import durum as ollama_durumu
            return self.send_data(200,{"uygulama":"OptiBid","surum":"v20-genel-arastirma","source_policy":"EKAP_ONLY","index_source_policy":"TUIK_OFFICIAL",
                                      "gelistirme_gorevi":"v17","asama":"M4","uygulama_koku":str(ROOT),
                                      "proje_koku":str(ROOT.parent),"veritabani":str(DATA),
                                      "uygulama_kimligi":SETTINGS['kimlik'],"port":self.server.server_port,
                                      "pid":os.getpid(),"mcp":mcp_durumu(),"ollama":ollama_durumu(timeout=.3)})
        if self.path.startswith("/api/rapor-senaryolari/"):
            try:
                key=str(UUID(self.path.rsplit("/",1)[-1]))
                with kayitlar.connection(DATA) as db:
                    snap=kayitlar.snapshot(db,key)
                    if not snap:
                        return self.send_data(404,{"hata":"Rapor bulunamadı."})
                    entries=[json.loads(s) for s, in db.execute(
                        "SELECT veri FROM rapor_senaryolari WHERE rapor_id=? AND rapor_tarihi=? ORDER BY kayit_tarihi",
                        (key,snap["tarih"]))]
                return self.send_data(200,{"tarih":snap["tarih"],"senaryolar":entries})
            except ValueError:
                return self.send_data(400,{"hata":"Rapor kimliğini kontrol edin."})
        from ekap_veri import POLICY
        if self.path=="/api/kaynak-denetimi":
            from ekap_veri import snapshot
            rows,_,meta=snapshot()
            raw=json.dumps({"kapsam":meta,"kayitlar":rows},ensure_ascii=False,indent=2).encode()
            self.send_response(200)
            self.send_header("Content-Type","application/json; charset=utf-8")
            self.send_header("Content-Disposition",'attachment; filename="OptiBid-EKAP-denetimi.json"')
            self.send_header("Content-Length",str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        if self.path.startswith(("/api/ekap-dayanagi/","/api/ekap-goruntu/")):
            from ekap_veri import DATA as EVIDENCE_DIR,verified
            key=self.path.split("/",3)[-1]
            row=verified().get(key)
            if not row:
                return self.send_data(404,{"hata":"Doğrulanmış EKAP dayanağı bulunamadı."})
            image=(row.get('sonuc') or {}).get('dosya')
            if self.path.startswith("/api/ekap-goruntu/"):
                if not image:
                    return self.send_data(404,{"hata":"Bu kaydın kanıtı EKAP metin sayfasıdır."})
                return self.send_data(200,(EVIDENCE_DIR/"sonuclar"/image).read_bytes(),"image/png")
            return self.send_data(200,{**row,"goruntu":"/api/ekap-goruntu/"+key if image else None})
        if self.path in ('/api/dosya-fiyatlari','/api/dosya-fiyatlari.xlsx','/api/dosya-fiyat-ozeti'):
            from dosya_fiyatlari import envanter
            inventory=envanter()
            if self.path=='/api/dosya-fiyat-ozeti':return self.send_data(200,inventory['ozet'])
            if self.path.endswith('.xlsx'):
                from excel import dosya_fiyat_excel
                return self.send_data(200,dosya_fiyat_excel(inventory),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            return self.send_data(200,inventory)
        if self.path.startswith('/api/dosya-fiyat-dayanagi/'):
            from urllib.parse import unquote
            from dosya_fiyatlari import envanter
            key=unquote(self.path.removeprefix('/api/dosya-fiyat-dayanagi/'))
            rows=[r for r in envanter()['kayitlar'] if r['ikn']==key]
            return self.send_data(200 if rows else 404,{'kayitlar':rows,'resmi_ekap_teyidi_uretmez':True})
        if self.path == "/api/hazirliklar":
            with kayitlar.connection(DATA) as db:
                return self.send_data(200,kayitlar.list_records(db))
        if self.path.startswith("/api/rapor-kaydi/"):
            try:
                with kayitlar.connection(DATA) as db:
                    saved=kayitlar.snapshot(db,self.path.rsplit("/",1)[-1])
                    if saved and saved["sonuc"].get("source_policy")!=POLICY:
                        saved={"onceki_politika":True,"tarih":saved["tarih"]}
                    return self.send_data(200,saved)
            except ValueError:
                return self.send_data(400,{"hata":"Kayıt kimliği geçersiz."})
        if self.path == "/api/emsal":
            from ekap_veri import verified
            return self.send_data(200,len(verified()))
        if self.path.split("?",1)[0] == "/api/havuz":
            from urllib.parse import urlsplit,parse_qs
            from veri_merkezi import ara
            args=parse_qs(urlsplit(self.path).query)
            try:
                offset=int(args.get("baslangic",["0"])[0])
                status=args.get('durum',['ekap'])[0]
                if offset<0 or status not in ('tumu','ekap','bekliyor','karantina'): raise ValueError
            except ValueError:
                return self.send_data(400,{"hata":"Sayfa başlangıcı geçersiz."})
            return self.send_data(200,ara(args.get("q",[""])[0][:200],offset,status))
        assets = {"/": ("index.html","text/html"), "/app.js": ("app.js","text/javascript"), "/rapor.js": ("rapor.js","text/javascript"), "/tasarim.css": ("tasarim.css","text/css"), "/emsal.js": ("emsal.js","text/javascript"),
                  "/kagit_ornegi.json": ("kagit_ornegi.json","application/json"), "/sunum.js": ("sunum.js","text/javascript"), "/catalog.json": ("catalog.json","application/json")}
        local_assets={
            '/calisma.js':('calisma.js','text/javascript'),
            '/ihale_semasi.json':('ihale_semasi.json','application/json'),
            '/birim_sozlugu.json':('birim_sozlugu.json','application/json'),
            '/arastirma.js':('arastirma.js','text/javascript'),
            '/calisma-v20.css':('calisma-v20.css','text/css'),
            '/sartname.js':('sartname.js','text/javascript'),
            '/dosya-fiyatlari.js':('dosya-fiyatlari.js','text/javascript'),
            "/gecmis.js":("gecmis.js","text/javascript"),
            "/calisma-v6.css":("calisma-v6.css","text/css"),
            "/karar-v10.js":("karar-v10.js","text/javascript"),
            "/ayarlar.js":("ayarlar.js","text/javascript"),
            "/calisma-v10.css":("calisma-v10.css","text/css"),
            "/static/brand/optibid-logo.webp":("static/brand/optibid-logo.webp","image/webp"),
            "/static/brand/ob.webp":("static/brand/ob.webp","image/webp"),
            "/static/brand/ob-32.png":("static/brand/ob-32.png","image/png"),
            "/static/brand/ob-192.png":("static/brand/ob-192.png","image/png"),
            "/static/brand/renkler.css":("static/brand/renkler.css","text/css"),
            "/static/fonts/montserrat.ttf":("static/fonts/montserrat.ttf","font/ttf"),
            "/static/fonts/plex.ttf":("static/fonts/plex.ttf","font/ttf"),
        }
        assets.update(local_assets)
        if self.path not in assets:
            return self.send_data(404, None)
        name, mime = assets[self.path]
        self.send_data(200, (ROOT/name).read_bytes(), mime)

    def do_POST(self):
        if not self.local_request():
            return self.send_data(403,{"hata":"OptiBid işlemleri yerel uygulamadan yapılır."})
        if self.path == '/api/sartname-yukle':
            return self.sartname_yukle()
        if self.path not in ("/api/hazirliklar","/api/soru","/api/analiz","/api/rapor-hesap","/api/emsal-ekle","/api/kayit-sil","/api/kayit-geri-al","/api/karar-asistani","/api/senaryo-kaydet","/api/rapor-excel","/api/ayarlar","/api/yardim","/api/arastirma","/api/kaynak-oku","/api/rapor-json") or self.headers.get_content_type() != "application/json":
            return self.send_data(400, None)
        try:
            size = int(self.headers["Content-Length"])
            if size > 1000000:
                return self.send_data(413,{'hata':'JSON isteği 1 MB sınırını aşıyor.'})
            if size <= 0:
                raise ValueError
            doc = json.loads(self.rfile.read(size))
            if not isinstance(doc,dict):raise ValueError
            if self.path in ('/api/arastirma','/api/kaynak-oku'):
                from mcp_hesap import calistir
                from arastirma import bul,oku
                try:
                    name='internet_ihale_ara' if self.path=='/api/arastirma' else 'internet_kaynagini_oku'
                    args={'sorgu':doc.get('sorgu')} if name=='internet_ihale_ara' else {'url':doc.get('url')}
                    try:
                        value,trace=calistir(name,args,timeout=24)
                    except Exception:
                        value=bul(args['sorgu']) if name=='internet_ihale_ara' else oku(args['url'])
                        trace={'arac':name,'mod':'yerel','mcp_dogrulandi':False}
                    return self.send_data(200,dict(value,iz=trace))
                except (ValueError,TypeError) as error:
                    return self.send_data(400,{'hata':str(error)})
            if self.path=="/api/ayarlar":
                from ollama_ayar import kaydet
                try:
                    return self.send_data(200,{"secili":kaydet(doc.get("model"))})
                except ValueError as error:
                    return self.send_data(400,{"hata":str(error)})
            if self.path=="/api/yardim":
                import senaryo
                question=doc.get("soru")
                if not isinstance(question,str) or not 0<len(question.strip())<=900:
                    return self.send_data(400,{"hata":"Sorunuzu 900 karakter içinde yazın."})
                context=doc.get('baglam')
                verified_context=False
                if isinstance(context,dict) and context.get('id'):
                    with kayitlar.connection(DATA) as db:
                        row=db.execute("SELECT rev,doc FROM hazirliklar WHERE id=? AND id NOT IN (SELECT id FROM silinen_hazirliklar)",
                                       (str(UUID(context['id'])),)).fetchone()
                    if not row or row[0]!=context.get('rev'):
                        return self.send_data(409,{'hata':'Çalışma değişti. Güncel kaydı açın.'})
                    context=json.loads(row[1])
                    verified_context=True
                return self.send_data(200,senaryo.cevap(None,question,adim=doc.get("adim"),context=context if isinstance(context,dict) else None,
                                                       history=doc.get("gecmis") if isinstance(doc.get("gecmis"),list) else None,
                                                       context_verified=verified_context))
            if self.path in ("/api/karar-asistani","/api/senaryo-kaydet"):
                import senaryo
                from ekap_veri import POLICY
                with kayitlar.connection(DATA) as db:
                    snap=kayitlar.snapshot(db,doc["id"])
                if not snap or doc.get("rev")!=snap["belge"]["rev"] or doc.get("tarih")!=snap["tarih"]:
                    return self.send_data(409,{"hata":"Rapor değişti. Güncel raporu açın."})
                if snap["sonuc"].get("source_policy")!=POLICY:
                    return self.send_data(409,{"hata":"Bu raporu EKAP politikasıyla yeniden hesaplayın."})
                if self.path=="/api/senaryo-kaydet":
                    try:
                        with kayitlar.connection(DATA,write=True) as db:
                            current=kayitlar.snapshot(db,doc["id"])
                            if not current or current["tarih"]!=snap["tarih"]:
                                return self.send_data(409,{"hata":"Rapor değişti. Güncel raporu açın."})
                            value=senaryo.kaydet(db,current,doc.get("girdiler"))
                        return self.send_data(200,value)
                    except (ValueError,TypeError):
                        return self.send_data(400,{"hata":"Senaryo girdilerini ve KDV esasını kontrol edin."})
                question=doc.get("soru")
                if not isinstance(question,str) or not 0<len(question.strip())<=900:
                    return self.send_data(400,{"hata":"Sorunuzu 900 karakter içinde yazın."})
                try:
                    return self.send_data(200,senaryo.cevap(snap,question,history=doc.get("gecmis") if isinstance(doc.get("gecmis"),list) else None))
                except (OSError,TimeoutError,ValueError,ImportError):
                    return self.send_data(503,{"hata":"Senaryo aracı yanıt vermedi. Tekrar deneyin."})
            if self.path in ("/api/kayit-sil","/api/kayit-geri-al"):
                try:
                    with kayitlar.connection(DATA,write=True) as db:
                        result=kayitlar.mark_deleted(db,doc) if self.path=="/api/kayit-sil" else {"adet":kayitlar.undo(db,doc["grup"])}
                    return self.send_data(200,result)
                except (ValueError,KeyError,TypeError,AttributeError) as exc:
                    return self.send_data(400,{"hata":str(exc)})
            if self.path == "/api/emsal-ekle":
                try:
                    return self.send_data(201, emsal.add(doc))
                except (ValueError, TypeError, KeyError, AttributeError) as error:
                    return self.send_data(400, {"hata": str(error)})
            if self.path in ("/api/rapor-excel","/api/rapor-json"):
                from excel import rapor_excel
                with kayitlar.connection(DATA) as db:
                    snapshot=kayitlar.snapshot(db,doc["id"])
                    selection=doc.get("ekler",[])
                    if not isinstance(selection,list) or len(selection)>30 or not all(isinstance(k,str) for k in selection):
                        return self.send_data(400,{"hata":"Senaryo ekleri geçersiz."})
                    scenarios=[json.loads(s) for k,s in db.execute(
                        "SELECT id,veri FROM rapor_senaryolari WHERE rapor_id=? AND rapor_tarihi=?",(doc["id"],doc.get("tarih"))) if k in selection]
                if not snapshot or snapshot["tarih"]!=doc.get("tarih") or snapshot["belge"]["rev"]!=doc.get("rev"):
                    return self.send_data(409,{"hata":"Rapor değişti. Güncel raporu açın."})
                if snapshot["sonuc"].get("source_policy")!="EKAP_ONLY":
                    return self.send_data(409,{"hata":"Excel için raporu EKAP politikasıyla yeniden hesaplayın."})
                if self.path=='/api/rapor-json':
                    from standart import disari_aktar
                    return self.send_data(200,{'calisma':disari_aktar(snapshot['belge']),
                                               'rapor':snapshot['sonuc'],'senaryolar':scenarios,'rapor_tarihi':snapshot['tarih']})
                return self.send_data(200,rapor_excel(snapshot,scenarios),"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            if self.path == "/api/soru":
                return self.send_data(200, motor.soru(doc))
            if self.path == "/api/rapor-hesap":
                try:
                    saving=self.headers.get("X-OptiBid-Rapor")=="kaydet"
                    attachment=None
                    if saving:
                        requested=doc
                        with kayitlar.connection(DATA) as db:
                            current=db.execute('SELECT rev,doc FROM hazirliklar WHERE id=?',(str(UUID(doc['id'])),)).fetchone()
                            if not current or current[0]!=doc.get('rev'):
                                return self.send_data(409,{'hata':'Hazırlık değişti. Güncel kaydı açın.'})
                            doc=rapor_parametreleri(json.loads(current[1]),requested)
                            attachment=doc.get('ek_bilgiler',{}).get('sartname')
                            if attachment:
                                from sartname import cikarim_oku,taslak_kanitlari
                                if extracted:=cikarim_oku(db,attachment['sha']):
                                    taslak_kanitlari(doc,extracted,json.loads(current[1]))
                    result=rapor_hesapla(doc)
                    if attachment:
                        result['sartname_durumu']={k:attachment.get(k) for k in
                            ('sha','belge_adi','okuma','inceleme_tamamlandi','kanitlar','model_durumu','islem_id')}
                    if saving:
                        with kayitlar.connection(DATA,write=True) as db:
                            when=kayitlar.save_report(db,doc,result)
                        if when is None:
                            return self.send_data(409,{"hata":"Hazırlık değişti veya silindi. Güncel kaydı açın."})
                        result["kayit_tarihi"]=when
                    return self.send_data(200,result)
                except (TypeError, KeyError, ValueError, AttributeError):
                    return self.send_data(400,{"hata":"Rapor girdilerini kontrol edin."})
            if self.path == "/api/analiz":
                try:
                    report = analyze_once(doc)
                    trace = report.get("ajan", {})
                    self.log_message("Analiz %s rev=%s: %s", trace.get("run_id"), doc.get("rev"), trace.get("mod"))
                except (ValueError, KeyError, TypeError, AttributeError):
                    return self.send_data(400, {"hata": "Hazırlık verileri geçersiz. Hazırlığı açıp alanları kontrol edin."})
                except Exception:
                    logging.exception("OptiBid analizi tamamlanamadı")
                    return self.send_data(500, {"hata": "Analiz sunucuda tamamlanamadı. Tekrar deneyin."})
                return self.send_data(200, report)
            key = str(UUID(doc["id"]))
            rev = doc["rev"]
            if type(rev) is not int or rev < 0:
                raise ValueError
        except (ValueError, TypeError, KeyError):
            return self.send_data(400, None)
        with kayitlar.connection(DATA,write=True) as db:
            if db.execute("SELECT 1 FROM silinen_hazirliklar WHERE id=?",(key,)).fetchone():
                return self.send_data(409,{"hata":"Bu kayıt silindi."})
            row = db.execute("SELECT rev,doc FROM hazirliklar WHERE id=?", (key,)).fetchone()
            if rev != (row[0] if row else 0):
                return self.send_data(409, {"hata": "Başka bir sekmede daha yeni bir kayıt var."})
            extra = doc.get('ek_bilgiler')
            attachment = extra.get('sartname') if isinstance(extra,dict) else None
            prior=json.loads(row[1]) if row else {}
            if prior.get('ek_bilgiler',{}).get('sartname') and not attachment:
                return self.send_data(409,{'hata':'Bu hazırlığın şartname bağlantısı eksik. Hazırlığı tekrar açın.'})
            if attachment:
                from sartname import DIGEST, cikarim_oku, taslak_kanitlari
                digest = attachment.get('sha') if isinstance(attachment,dict) else None
                if not isinstance(digest,str) or not DIGEST.fullmatch(digest):
                    return self.send_data(400, {'hata':'Şartname kimliği geçersiz.'})
                linked = db.execute('SELECT sha FROM sartname_baglari WHERE hazirlik=?',(key,)).fetchone()
                stored=db.execute('SELECT ad FROM sartname_dosyalari WHERE sha=?',(digest,)).fetchone()
                if (linked and linked[0]!=digest) or not stored:
                    return self.send_data(409, {'hata':'Şartname bulunamadı veya bu hazırlıkta değişti.'})
                attachment['belge_adi']=stored[0]
                db.execute('INSERT OR IGNORE INTO sartname_baglari VALUES (?,?)',(key,digest))
                if extracted:=cikarim_oku(db,digest):
                    taslak_kanitlari(doc,extracted,prior)
                else:
                    for field in ('kanitlar','okuma','inceleme_tamamlandi'):
                        attachment.pop(field,None)
            doc["rev"] = rev + 1
            db.execute("INSERT OR REPLACE INTO hazirliklar VALUES (?,?,?)",
                       (key, rev+1, json.dumps(doc, ensure_ascii=False)))
        self.send_data(200, rev+1)

    def sartname_yukle(self):
        from sartname import MAX_BYTES, oku, sakla, cikarim_oku, cikarim_sakla
        from sartname_alanlari import cikar
        if self.headers.get_content_type() != 'application/octet-stream':
            return self.send_data(415, {'hata':'Dosyayı ham PDF, DOCX veya UTF-8 TXT olarak gönderin.'})
        try:
            size = int(self.headers.get('Content-Length') or '0')
        except ValueError:
            size = 0
        if size > MAX_BYTES:
            return self.send_data(413, {'hata':'Dosya en fazla 25 MB olabilir.'})
        if size <= 0:
            return self.send_data(400, {'hata':'Boş dosya yüklenemez.'})
        try:
            self.connection.settimeout(12)
            expected=self.headers.get('X-OptiBid-Bicim')
            if expected not in (None,'pdf','docx','txt'):
                raise ValueError('Desteklenen belge biçimleri PDF, DOCX ve UTF-8 TXT.')
            digest, ext, pages, contents = oku(self.rfile,size,expected)
            supplied=unquote(self.headers.get('X-OptiBid-Dosya','')[:1024]).replace('\\','/').rsplit('/',1)[-1]
            supplied=''.join(c for c in supplied if c.isprintable()).strip()
            filename=supplied if 0<len(supplied)<=180 and supplied.lower().endswith(ext) else None
            version=motor.oku('sartname_profili.json')['surum']
            with contents, kayitlar.connection(DATA,write=True) as db:
                sakla(db,digest,ext,pages,contents,filename)
                name,raw_pages=db.execute('SELECT ad,sayfalar FROM sartname_dosyalari WHERE sha=?',(digest,)).fetchone()
                pages=json.loads(raw_pages)
                result=cikarim_oku(db,digest,version)
            if not result:
                result=cikar(pages,digest,ext[1:])
                result['islem_id']=str(uuid4())
                with kayitlar.connection(DATA,write=True) as db:
                    cikarim_sakla(db,digest,version,result)
                    logging.info('Şartname işlemi %s, bölüm %s, okunamayan %s',result['islem_id'],
                                 result['okuma']['toplam'],len(result['okuma']['okunamayan']))
        except (ValueError, OSError) as error:
            return self.send_data(422, {'hata':str(error) if isinstance(error,ValueError) else 'Dosya yüklemesi tamamlanmadı.'})
        except Exception:
            logging.exception('Şartname işlenemedi')
            return self.send_data(422, {'hata':'Belge okunamadı. Geçerli bir PDF veya DOCX kopyası deneyin.'})
        return self.send_data(200, {**result, 'sha':digest,'belge_adi':name,'bicim':ext[1:],'sayfalar':pages})

if __name__ == "__main__":
    DATA.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(DATA) as db:
        db.execute("CREATE TABLE IF NOT EXISTS hazirliklar(id TEXT PRIMARY KEY, rev INTEGER, doc TEXT)")
        kayitlar.init(db)
        kayitlar.purge(db)

    def temizle():
        while not stop.wait(1):
            try:
                if kayitlar.temizlenecek(DATA):
                    with kayitlar.connection(DATA,write=True) as db:
                        kayitlar.purge(db)
            except sqlite3.Error:
                logging.exception("Silinen kayıtların temizliği tamamlanamadı")

    stop=threading.Event()
    from baslat import port as configured_port
    port=configured_port()
    try:
        listener=ThreadingHTTPServer(("127.0.0.1",port),Handler)
    except OSError as error:
        raise SystemExit(f"OptiBid {port} portunu açamadı. {error}") from error
    url=f"http://127.0.0.1:{listener.server_port}/"

    def chrome_ac():
        try:
            with urlopen(url, timeout=5) as response:
                if response.status != 200:
                    return
            paths = [shutil.which("chrome")]
            paths.extend(Path(os.environ[k]) / "Google/Chrome/Application/chrome.exe"
                         for k in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")
                         if k in os.environ)
            chrome = next((str(p) for p in paths if p and Path(p).is_file()), None)
            if chrome:
                subprocess.Popen([chrome, url])
            else:
                import webbrowser
                webbrowser.open(url)
        except OSError as error:
            print(f"Chrome açılamadı: {error}. Adres: {url}")

    with listener as server:
        print(f"OptiBid {url} adresinde açık. Kapatmak için Ctrl+C.")
        import mcp_hesap
        mcp_hesap.isit()
        if not os.environ.get("OPTIBID_NO_BROWSER"):
            threading.Thread(target=chrome_ac, daemon=True).start()
        threading.Thread(target=temizle,daemon=True).start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            stop.set()






