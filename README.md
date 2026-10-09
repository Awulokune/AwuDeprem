# AwuDeprem — Windows

AwuDeprem AFAD'ın deprem kayıtlarını takip eder, seçilen il merkezine göre mesafe ve minimum büyüklük filtreleri uygular, yeni uygun olayları Windows bildirimiyle duyurur. **Deprem tahmini yapmaz ve garantili erken uyarı sistemi değildir.** AFAD verisinin yayınlanma ve iletim gecikmeleri olabilir; acil durumlarda resmi AFAD duyurularını izleyin.

## Uygulamayı çalıştırma

### Kurulu Python ile

1. Windows 10/11 ve Python 3.10+ gerekir.
2. `install.bat` dosyasını çalıştırın.
3. `run.bat` dosyasını çalıştırın.

### Kurulum paketi ile

`dist\AwuDeprem-Setup.msi` paketini çalıştırın. MSI, uygulamayı kullanıcıya özel programlar dizinine ve Başlat menüsüne ekler. Paket kurulu Python gerektirmez.

## Ayarlar

- İl listesi aranabilir; bir il seçildiğinde merkez koordinatları otomatik yazılır. Varsayılan İstanbul koordinatları **41.0082, 28.9784** olarak sabitlenmiştir.
- Minimum büyüklük listesi M1.0'dan M7.0'a 0.1 artar (varsayılan M3.5).
- Maksimum uzaklık listesi 5, 10, 20, 30, 50, 75, 100, 150, 200, 300, 500 km'dir (varsayılan 100 km).
- Gelişmiş seçeneği koordinatları elle düzenlemeyi açar. Enlem -90..90, boylam -180..180 dışında kabul edilmez.
- **Ayarları kaydet** seçimleri `config.json` dosyasına kaydeder.

Kullanıcı ayarları, yinelenme kayıtları ve günlük Windows `%APPDATA%\AwuDeprem` dizinine kaydedilir; kurulu uygulama klasörüne yazma izni gerekmez. Log dosyası `awudeprem.log` adını taşır.

İl merkez koordinatları `city_coordinates.json` içinde uygulamaya eklenmiştir. Değerler yaklaşık merkez koordinatlarıdır ve [Türkiye Haritası'nın 81 il koordinat listesine](https://www.turkiyeharitasi.tr/koordinat-bulma) dayanır. İstanbul için kullanıcı tarafından belirlenen varsayılan değer korunmuştur.

## Gerçek AFAD bildirimleri

Uç nokta: `https://deprem.afad.gov.tr/apiv2/event/filter`. İstemci son 10 dakika için zaman, JSON biçimi, büyüklük ve sıralama parametreleri gönderir. Yanıtın JSON dizi ve her olayın AFAD şemasındaki `eventID`, `date`, `latitude`, `longitude`, `depth`, `type`, `magnitude`, `location` alanlarını içerdiği doğrulanır. Beklenmeyen biçim bildirim işleme alınmadan hata kaydına yazılır. AFAD'ın parametreleri [resmi Event Web Service sayfasında](https://deprem.afad.gov.tr/event-service) belgelenmiştir.

Her kaydın uzaklığı Haversine formülüyle yerel olarak hesaplanır. Büyüklük minimum değere eşit veya daha büyük, uzaklık yarıçap içinde olmalıdır. İki koşuldan birini sağlamayan kayıt bildirilmez. Gerçek AFAD `eventID` değerleri `%APPDATA%\AwuDeprem\seen_events.json` içinde tutulur; aynı kimlik tekrar bildirilmez ve uygulama yeniden başlatıldığında tekrar bastırılır. Bildirim başarısızsa kimlik saklanmaz ve sonraki kontrolde yeniden denenir.

Kontrol 30 saniyede bir yapılır; **Şimdi kontrol et** elle tetikler. Windows toast için `winotify` kullanılır; ses kutusu kapatılabilir. Hatalar `%APPDATA%\AwuDeprem\awudeprem.log` dosyasına kaydedilir.

Canlı AFAD isteği HTTP 200 ile yanıt verdi; gerçek JSON olay dizisinden 3 kayıt uygulamanın şema doğrulamasından geçti. İstek `minmag=0` ile yapıldı ve örnek yanıtlardaki sayısal koordinat/büyüklük/derinlik alanlarının metin olarak gelebileceği doğrulandı; uygulama bunları sayıya çevirerek filtreliyor.

## DEMO / test modu

**Demo bildirimi gönder** AFAD isteği yapmadan örnek Windows toast bildirimi ve etkinse ses üretir. Başlıkta ve gövdede **“DEMO — gerçek deprem değil”** yazar. Örnek M4.2, 12 km, İstanbul açıklarıdır. Bu bir simülasyondur.

Demo yolu AFAD verisini çekmez, AFAD kimliği oluşturmaz, olay kimlik kayıtlarını okumaz/yazmaz ve gerçek olay yinelenme kontrolüne katılmaz.

## MSI oluşturma

Kaynak projede `build_installer.bat` çalıştırın. Betik Python 3.10+ ve `pip` kontrolü yapar, PyInstaller bağımlılığını kurar, tek dosya EXE'yi üretir ve WiX 3.14 `candle.exe`/`light.exe` ile MSI oluşturur. WiX'in taşınabilir ikili dosyaları `work\wix3` altında veya `PATH` içinde olmalıdır. Resmi araç arşivi: [WiX v3 releases](https://github.com/wixtoolset/wix3/releases). Başarıyla tamamlanırsa çıktı **`dist\AwuDeprem-Setup.msi`** olur. Başlat menüsü kısayolu bulunur ve Python kurulu olmayan Windows bilgisayarda çalışır. Masaüstü kısayolu isteğe bağlıdır: `msiexec /i dist\AwuDeprem-Setup.msi CREATE_DESKTOP_SHORTCUT=1`.

Bu teslimde oluşturulmuş MSI: **`dist\AwuDeprem-Setup.msi`**.

## Testler ve sorun giderme

Proje klasöründe:

```powershell
python -m unittest discover -s tests -v
```

- Toast gelmiyorsa Windows bildirim ayarlarını ve uygulama bildirim izinlerini kontrol edin; `install.bat`'i yeniden çalıştırıp `winotify` kurulumunu doğrulayın.
- AFAD bağlantı/şema hataları `%APPDATA%\AwuDeprem\awudeprem.log` içine yazılır.
- MSI derlemesi eksik WiX veya paketleme bağımlılığını `build_installer.bat` çıktısında açıkça belirtir.
