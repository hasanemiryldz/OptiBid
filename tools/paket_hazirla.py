"""Kişisel çalışma dosyaları olmadan çalıştırılabilir OptiBid paketi."""
import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

APP = Path(__file__).resolve().parents[1]
MAIN = (
    'ajan.py alim_emsal.py app.js arastirma.js arastirma.py arastirma_ayar.json asistan.py '
    'ayarlar.js arsiv_profilleri.json Baslat.bat baslat.sh baslat.py baslatma.json belge_indeksi.py belge_indeksi.json birim_sozlugu.json calisma.js '
    'calisma-v6.css calisma-v10.css calisma-v20.css calistir.py catalog.json DEGERLENDIRME.md DEMO_AKISI.md '
    'dosya-fiyatlari.js dosya_fiyat_kategorileri.json dosya_fiyatlari.py ekap_sayfalari.py ekap_veri.py '
    'emsal.js emsal.py excel.py fiyat_referansi.py gecmis.js gozlenen_fiyatlar.py havuz.py '
    'hesap_araclari.py ihale_semasi.json index.html kagit_kosullu_emsaller.json kagit_ornegi.json '
    'karar-v6.js karar-v10.js kategori_endeks.json kayitlar.py kaynaklar.json Kurulum.bat '
    'mcp_hesap.py mcp_server.py MIMARI.md motor.py ollama_ayar.py ornek_danismanlik.json '
    'ornek_hizmet.json ornek_senaryolar.json ornek_yapim.json profiller.json rapor.js requirements.txt '
    'sartname.js sartname.py sartname_alanlari.py sartname_profili.json senaryo.py standart.py sunum.js SUNUM_NOTLARI.md '
    'tasarim.css tuik_endeks.py urun_ayarlari.json urun_ayarlari.py veri_alim.py VERI_KARTI.md '
    'veri_kokleri.json veri_merkezi.py veri_yollari.py tools/paket_hazirla.py'
).split()
PUBLIC_PATTERNS = (
    'static/brand/*.webp','static/brand/*.png','static/brand/*.css','static/fonts/*.ttf','static/fonts/OFL-*.txt',
    'data/alim/*/alim.sqlite','data/ekap/gozlemler.json','data/ekap/sayfa_kanitlari.json',
    'data/ekap/sonuclar/*.png','data/ekap/incelenen_yeni_sonuclar/*.json',
    'data/ekap/belge_paketleri/ihale_dokumani_*.zip','data/tuik/yi_ufe.json',
)
ARCHIVE_FILES = ('optibid.db','OptiBid_Emsal_Tam_Veri_genisletilmis.json')


def hazirla(output, app=APP):
    app = Path(app).resolve()
    output = Path(output).resolve()
    entries = [(app/name,'IhaleAsistani/'+name) for name in MAIN]
    for pattern in PUBLIC_PATTERNS:
        entries.extend((path,'IhaleAsistani/'+path.relative_to(app).as_posix())
                       for path in sorted(app.glob(pattern)) if path.is_file())
    entries.extend((app.parent/name,name) for name in ARCHIVE_FILES)
    entries = [(path,'OptiBid/'+target) for path,target in entries]
    for path,_ in entries:
        if not path.is_file() or not path.resolve().is_relative_to(app.parent):
            raise ValueError(f'Paket kaynağı eksik veya proje dışında: {path.name}')
    output.parent.mkdir(parents=True,exist_ok=True)
    with ZipFile(output,'x',compression=ZIP_DEFLATED,compresslevel=6) as zip_file:
        for path,target in entries:
            zip_file.write(path,target)
        zip_file.writestr('OptiBid/BASLANGIC.txt','OptiBid\n\nWindows\n'
            '1. OptiBid klasörünü bütün olarak çıkartın.\n'
            '2. IhaleAsistani\\Kurulum.bat dosyasını çalıştırın.\n'
            '3. IhaleAsistani\\Baslat.bat dosyasını çalıştırın.\n\n'
            'Linux ve macOS\nIhaleAsistani dizininde Python sanal ortamı oluşturup requirements.txt '
            'bağımlılıklarını kurun. sh baslat.sh ile açın.\n\n'
            'Yerel model varsayılanı qwen3:8b. Kurulum ortamına özel hazırlıklar, sohbetler ve yüklenen '
            'şartnameler bu paylaşım paketinde yer almaz.\n')
    return len(entries)+1


if __name__ == '__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('zip',type=Path)
    args=cli.parse_args()
    print(f'{hazirla(args.zip)} paket girdisi · {args.zip.resolve()}')
