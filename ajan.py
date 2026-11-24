"""Ollama'nın yerel araç seçimini MCP stdio oturumuna bağlar."""
import asyncio
import hashlib
import json
import os
import sqlite3
import sys
import time
from threading import Lock
import uuid
from datetime import datetime, timezone
from urllib.request import Request, urlopen
import motor

from ollama_ayar import secili
OLLAMA_SLOT=Lock()
ANALIZ = {"veri_yeterliligi_kontrol","fiyat_tahmin_et","teklif_karsilastir","belge_ara"}

def canonical(tag):
    if not isinstance(tag,str):
        return None
    return tag.strip().lower().removeprefix('registry.ollama.ai/').removeprefix('library/')


def model_sec(messages, tools, schema=None, *, model=None, timeout=17, num_predict=170):
    if os.environ.get("OPTIBID_LLM","on")=="off":
        raise OSError("Ollama kapalı")
    required=secili()
    if model is not None and canonical(model)!=canonical(required):
        raise ValueError('Yeni Ollama isteğinde qwen3:8b gerekli.')
    settings=motor.oku('belge_indeksi.json')
    payload = dict(model=required,messages=messages,tools=tools,stream=False,think=False,keep_alive='25s',
                   options=dict(temperature=0,num_predict=min(int(num_predict),700),
                                num_ctx=settings['num_ctx'],top_k=settings['llm_top_k']))
    if schema is not None:
        payload["format"]=schema
    request = Request("http://127.0.0.1:11434/api/chat",data=json.dumps(payload).encode(),
                      headers={"Content-Type":"application/json"})
    if not OLLAMA_SLOT.acquire(timeout=min(timeout,12)):
        raise TimeoutError('Yerel qwen3:8b bir başka isteği işliyor.')
    try:
        with urlopen(request,timeout=timeout) as response:
            result=json.load(response)
    finally:
        OLLAMA_SLOT.release()
    actual=result.get('model')
    if canonical(actual)!=canonical(required):
        raise ValueError('Ollama yanıtındaki model qwen3:8b ile eşleşmedi.')
    digest=None
    digest_source=None
    try:
        from ollama_ayar import mevcut_modeller
        matches=[row['digest'] for row in mevcut_modeller(timeout=.6)
                 if canonical(row.get('name'))==canonical(actual) and row.get('digest')]
        if len(set(matches))==1:
            digest=matches[0]
            digest_source='/api/tags etiket eşlemesi'
    except (OSError, ValueError, KeyError, TypeError):
        pass
    trace=dict(requested_model=required,actual_model=actual,num_ctx=payload['options']['num_ctx'],
               canonical_model=canonical(actual),model_digest=digest,digest_kaynagi=digest_source,
               toplam_ms=round(result.get('total_duration',0)/1_000_000),
               baglam_tokeni=result.get('prompt_eval_count'),yanit_tokeni=result.get('eval_count'))
    return {**result['message'],'ollama_izi':trace}

async def yurutecek(doc, run):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    from mcp_hesap import ENV
    settings = StdioServerParameters(command=sys.executable,args=[str(motor.ROOT/"mcp_server.py")], env={key:os.environ[key] for key in ENV if key in os.environ})
    results = {}
    messages = [{"role":"system","content":
        "OptiBid karar ajanısın. Araç seç. Fiyat için önce veri yeterliliğini denetle. "
        "Yeterliyse fiyatı hesaplat. Eksik teknik profil için ilgili geçmiş belgeyi arayabilirsin. "
        "Teklifler varsa karşılaştır. Geçmiş belge hedefin şartı değildir. Tutar uydurma."},
        {"role":"user","content":json.dumps({"tur":doc["ihale_turu"],"kategori":doc["kategori"],
             "kalemler":[{"ad":k["ad"],"teknik":k["teknik"]} for k in doc["kalemler"]],
             "teklif_sayisi":len(doc.get("teklifler",[]))}, ensure_ascii=False)}]
    async with stdio_client(settings) as (reader, writer):
        async with ClientSession(reader,writer) as client:
            info = await client.initialize()
            discovered = {t.name:t for t in (await client.list_tools()).tools if t.name in ANALIZ}
            run.update(mod="MCP stdio",sunucu=info.serverInfo.name,kesfedilen=list(discovered))

            async def call(name, args, origin):
                started=time.monotonic()
                event=dict(arac=name,secim=origin,baslangic=datetime.now(timezone.utc).isoformat(),durum="hata")
                run["olaylar"].append(event)
                try:
                    response=await client.call_tool(name,args)
                    if response.isError:
                        raise ValueError("MCP araç hatası")
                    value=response.structuredContent
                    if value is None:
                        value=json.loads(response.content[0].text)
                    if isinstance(value,dict) and list(value)==["result"]:
                        value=value["result"]
                    results[name]=value
                    event.update(durum="başarılı",kaynaklar=([x["ikn"] for x in value] if isinstance(value,list)
                                 else [x[0] if isinstance(x,list) else x for x in value.get("emsaller",[])]))
                    return value
                finally:
                    event["ms"]=round((time.monotonic()-started)*1000)

            for _ in range(3):
                allowed = set(discovered)-set(results)
                check=results.get("veri_yeterliligi_kontrol",{})
                if not (check.get("uygun") or check.get("hesap_yapilabilir")):
                    allowed.discard("fiyat_tahmin_et")
                if not doc.get("teklifler"):
                    allowed.discard("teklif_karsilastir")
                if not allowed: break
                tools=[]
                for name in sorted(allowed):
                    schema=discovered[name].inputSchema if name=="belge_ara" else {"type":"object","properties":{}}
                    tools.append({"type":"function","function":dict(name=name,description=discovered[name].description,parameters=schema)})
                try:
                    answer=await asyncio.to_thread(model_sec,messages,tools,model=run["model"])
                    run['ollama_istekleri'].append(answer['ollama_izi'])
                    calls=answer.get("tool_calls") or []
                    if not calls: break
                    function=calls[0]["function"]
                    name=function["name"]
                    if name not in allowed: break
                    messages.append({"role":"assistant","content":"","tool_calls":[calls[0]]})
                    args=function.get("arguments",{}) if name=="belge_ara" else {"hazirlik":doc}
                    value=await call(name,args,"Ollama native tool calling")
                    summary={k:value[k] for k in ('uygun','hesap_yapilabilir','kosullu_referans_sayisi','durum','emsal_sayisi','neden','medyan') if k in value} if isinstance(value,dict) else value
                    messages.append({"role":"tool","tool_name":name,"content":json.dumps(summary,ensure_ascii=False)[:3500]})
                except (OSError,ValueError,KeyError,TypeError) as exc:
                    run["hatalar"].append(type(exc).__name__)
                    break
            if "veri_yeterliligi_kontrol" not in results:
                await call("veri_yeterliligi_kontrol",{"hazirlik":doc},"Program kuralı")
            if (results["veri_yeterliligi_kontrol"]["uygun"] or results["veri_yeterliligi_kontrol"].get("hesap_yapilabilir")) and "fiyat_tahmin_et" not in results:
                await call("fiyat_tahmin_et",{"hazirlik":doc},"Program kuralı")
            if doc.get("teklifler") and "teklif_karsilastir" not in results:
                await call("teklif_karsilastir",{"hazirlik":doc},"Program kuralı")
            if "belge_ara" not in results and results["veri_yeterliligi_kontrol"]["uygun"]:
                await call("belge_ara",{"sorgu":doc["kalemler"][0]["ad"]},"Rapor dayanağı")
    result = results.get("fiyat_tahmin_et") or results["veri_yeterliligi_kontrol"]["referans"]
    result.setdefault("teklifler",[])
    result.update(results.get("teklif_karsilastir",{}))
    result["belgeler"]=results.get("belge_ara",[])
    if result.get("medyan"):
        references=[x["ikn"] for x in result["emsal_ayrinti"]]
        captions={"endeks":result["yontem"],
                  "medyan":"Emsal referansı uygun birim fiyatların ortancasıdır.",
                  "kapsam":"Sonuç teknik profili ve fiyat esası karşılaştırılabilen kayıtları kapsar."}
        schema={"type":"object","properties":{"ikn":{"type":"string","enum":references},
                 "odak":{"type":"string","enum":list(captions)}},"required":["ikn","odak"],
                 "additionalProperties":False}
        try:
            explanation=await asyncio.to_thread(model_sec,[
                {"role":"system","content":"Hesaplanmış sonucu açıklamak için verilen İKN ve odaklardan birini seç."},
                {"role":"user","content":json.dumps({"iknler":references,"odaklar":list(captions),
                 "medyan":result["medyan"],"yontem":result["yontem"]},ensure_ascii=False)}
            ],[],schema,model=run["model"])
            run['ollama_istekleri'].append(explanation['ollama_izi'])
            selection=json.loads(explanation["content"])
            if selection["ikn"] in references and selection["odak"] in captions:
                result["aciklama"]=captions[selection["odak"]]+" Örnek dayanak İKN "+selection["ikn"]+"."
        except (OSError,ValueError,KeyError,TypeError) as exc:
            run["hatalar"].append("Ollama açıklaması: "+type(exc).__name__)
    return result

def analiz(doc):
    fingerprint=hashlib.sha256(json.dumps(doc,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    run=dict(run_id=str(uuid.uuid4()),hazirlik=doc.get("id"),rev=doc.get("rev"),profil=fingerprint,
             kategori=doc["kategori"], model=secili(),prompt_surumu="1",veri_surumu=None,
             olaylar=[],hatalar=[],ollama_istekleri=[])
    try:
        result=asyncio.run(asyncio.wait_for(yurutecek(doc,run),timeout=85))
    except Exception as exc:
        run.update(mod="Yerel Python yedek modu")
        run["hatalar"].append(type(exc).__name__)
        result=motor.analiz(doc)
    run["veri_surumu"]=result.get("veri_surumu")
    result["ajan"]=run
    with sqlite3.connect(os.environ.get("OPTIBID_AJAN_DB", motor.ROOT/"data/ajan.db")) as db:
        db.execute("CREATE TABLE IF NOT EXISTS calismalar(id TEXT PRIMARY KEY,iz TEXT NOT NULL)")
        db.execute("INSERT INTO calismalar VALUES(?,?)",(run["run_id"],json.dumps(run,ensure_ascii=False)))
    return result



