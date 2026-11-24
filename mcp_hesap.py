"""HTTP işçileri için ortak ve yeniden bağlanabilen MCP stdio oturumu."""
import asyncio
import atexit
import json
import logging
import os
from concurrent.futures import Future
from contextlib import AsyncExitStack
from pathlib import Path
import sys
import threading
import time

from urun_ayarlari import oku

TOOLS = frozenset({'maliyet_senaryosu_hesapla', 'birim_donustur', 'fiyat_endeksle',
                   'endeks_durumu', 'fiyat_tahmin_et', 'analiz_durumu_getir',
                   'dosya_fiyatlarini_incele', 'internet_ihale_ara', 'internet_kaynagini_oku',
                   'standart_belge_uret', 'ilgili_dosya_kayitlarini_ara', 'belge_ara'})
ENV = ('PYTHONPATH', 'OPTIBID_TUIK_VERI', 'OPTIBID_HAVUZ', 'OPTIBID_HAZIRLIK_DB',
       'OPTIBID_HOME','OPTIBID_ARSIV_DB','OPTIBID_KULLANICI_DIZINI','OPTIBID_BELGE_INDEKSI','OPTIBID_LLM',
       'BRAVE_SEARCH_API_KEY', 'OPTIBID_ARASTIRMA_DB', 'PYTHONUTF8', 'PYTHONDONTWRITEBYTECODE')


class AracHatasi(ValueError):
    pass


class Oturum:
    def __init__(self, ayar):
        self.ayar = ayar
        self.hazir = threading.Event()
        self.bagli = False
        self.thread = threading.Thread(target=lambda: asyncio.run(self._serve()),
                                       name='OptiBid MCP', daemon=True)
        self.thread.start()
        if not self.hazir.wait(2):
            raise TimeoutError('MCP işçisi başlatılamadı.')

    def gonder(self, name, args, timeout):
        if name is not None and name not in TOOLS:
            raise AracHatasi('Bu hesap aracı izinli değil.')
        aralik = self.ayar['sonraki_zaman_asimi_sn'] if self.bagli else self.ayar['ilk_zaman_asimi_sn']
        budget = timeout if timeout is not None else aralik + self.ayar['sonraki_zaman_asimi_sn']
        future = Future()
        self.loop.call_soon_threadsafe(self.queue.put_nowait,
                                       (name, args, time.monotonic() + budget, future))
        return future, budget

    async def _serve(self):
        self.loop = asyncio.get_running_loop()
        self.queue = asyncio.Queue()
        self.hazir.set()
        stack = AsyncExitStack()
        client = None
        failures, retry_at, generation = 0, 0, 0
        try:
            while (job := await self.queue.get()) is not None:
                name, args, deadline, future = job
                if not future.set_running_or_notify_cancel():
                    continue
                if time.monotonic() < retry_at:
                    future.set_exception(ConnectionError('MCP bağlantısı geçici olarak duraklatıldı.'))
                    continue
                start = time.monotonic()
                error = TimeoutError('MCP çağrısının bekleme süresi doldu.')
                for attempt in range(1 + self.ayar['yeniden_deneme']):
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    cold = client is None
                    limit = min(remaining, self.ayar['ilk_zaman_asimi_sn' if cold else 'sonraki_zaman_asimi_sn'])
                    try:
                        # stdio ve ClientSession aynı işçi görevi içinde açılır ve kapanır.
                        # Yalnız protokol işlemlerine süre sınırı uygulanır.
                        if cold:
                            from mcp import ClientSession, StdioServerParameters
                            from mcp.client.stdio import stdio_client

                            cfg = StdioServerParameters(command=sys.executable,
                                args=['-X', 'utf8', '-B', str(Path(__file__).with_name('mcp_server.py'))],
                                env={k: os.environ[k] for k in ENV if k in os.environ})
                            streams = await stack.enter_async_context(stdio_client(cfg))
                            client = await stack.enter_async_context(ClientSession(*streams))
                            info = await asyncio.wait_for(client.initialize(), timeout=limit)
                            tools = {tool.name for tool in (await asyncio.wait_for(
                                client.list_tools(), timeout=max(0, min(limit, deadline - time.monotonic())))).tools}
                            self.bagli = True
                            generation += 1
                        value = None
                        if name is not None:
                            if name not in tools:
                                raise AracHatasi('Hesap aracı MCP üzerinde bulunamadı.')
                            result = await asyncio.wait_for(client.call_tool(name, args),
                                                           timeout=max(0, min(limit, deadline - time.monotonic())))
                            if result.isError:
                                raise AracHatasi('MCP hesap aracı girdiyi işleyemedi.')
                            value = result.structuredContent or json.loads(result.content[0].text)
                            if not isinstance(value, dict):
                                raise AracHatasi('MCP aracı geçerli hesap çıktısı döndürmedi.')
                            value = value.get('result', value)
                        trace = {'sunucu': info.serverInfo.name, 'arac': name,
                                 'ms': round(1000 * (time.monotonic() - start)),
                                 'oturum': generation, 'deneme': attempt + 1}
                        failures = 0
                        future.set_result((value, trace))
                        break
                    except AracHatasi as exc:
                        future.set_exception(exc)
                        break
                    except Exception as exc:
                        error = exc
                        failures += 1
                        self.bagli = False
                        client = None
                        try:
                            await stack.aclose()
                        except Exception:
                            logging.warning('MCP bağlantısı kapatılırken hata oluştu', exc_info=True)
                        stack = AsyncExitStack()
                        if isinstance(exc, ImportError):
                            failures = self.ayar['kesici_hata_sayisi']
                        if failures >= self.ayar['kesici_hata_sayisi']:
                            retry_at = time.monotonic() + self.ayar['kesici_bekleme_sn']
                            break
                if not future.done():
                    future.set_exception(error)
        finally:
            self.bagli = False
            await stack.aclose()

    def kapat(self):
        if self.thread.is_alive():
            self.loop.call_soon_threadsafe(self.queue.put_nowait, None)
            self.thread.join(2)


_LOCK = threading.Lock()
_OTURUM = None


def durum():
    from importlib.util import find_spec
    return {'kurulu':find_spec('mcp') is not None,
            'bagli':bool(_OTURUM and _OTURUM.bagli)}


def _oturum():
    global _OTURUM
    with _LOCK:
        if _OTURUM is None or not _OTURUM.thread.is_alive():
            _OTURUM = Oturum(oku()['mcp'])
        return _OTURUM


def isit():
    future, _ = _oturum().gonder(None, {}, None)
    def kontrol(done):
        error = done.exception()
        if error:
            logging.warning('MCP başlangıç bağlantısı kurulamadı: %r', error)
    future.add_done_callback(kontrol)


@atexit.register
def kapat():
    if _OTURUM:
        _OTURUM.kapat()


def calistir(name, args, timeout=None):
    future, budget = _oturum().gonder(name, args, timeout)
    try:
        return future.result(timeout=budget)
    except TimeoutError:
        future.cancel()
        raise


async def arac(name, args, timeout=None):
    return await asyncio.to_thread(calistir, name, args, timeout)
