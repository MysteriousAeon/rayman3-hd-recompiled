# Rayman 3 HD Recompiled — Kurulum Rehberi

**Rayman 3 HD Recompiled**, Xbox 360 için yayımlanan Rayman 3 HD'nin Windows'ta emülatör kullanmadan, yerel olarak çalışmasını sağlayan bir projedir.

Oyun dosyaları kurulum paketine dahil değildir. Oyunu çalıştırmak için yasal olarak edindiğiniz Xbox 360 sürümüne ve kendi konsolunuzdan kopyaladığınız oyun paketine ihtiyacınız vardır.

## Sistem gereksinimleri

- Windows 10 veya Windows 11 (64 bit)
- [Microsoft Visual C++ Redistributable 2015–2022 (x64)](https://aka.ms/vs/17/release/vc_redist.x64.exe)
- Direct3D 12 destekli ekran kartı
- Yaklaşık 2,3 GB boş disk alanı
- Rayman 3 HD'nin özgün Xbox Live Arcade sürümü (oyun kimliği: `5841123F`), **başlık güncellemesi uygulanmamış** oyun paketi

Diğer platformların sürümleri ve başlık güncellemesi içeren Xbox 360 paketleri desteklenmez.

## Oyunun kurulumu

1. Rayman 3 HD oyun paketini Xbox 360 konsolunuzdan bilgisayarınıza kopyalayın. Paket, konsolun depolama alanında `Content\0000000000000000\5841123F\000D0000\` klasöründedir.
2. GitHub'daki **Releases** bölümünden `Rayman3HDRecompiled-<sürüm>-setup.exe` dosyasını indirin ve çalıştırın. Yönetici izni gerekmez.
3. Kurulum dilini **Türkçe** olarak seçin.
4. Oyunu kurmak istediğiniz klasörü belirleyin ve Xbox 360 oyun paketinizin dosyasını gösterin.
5. Kurulum programı paketi doğrular, gerekli dosyaları hazırlar ve oyunu kurar. Kaynak oyun paketiniz değiştirilmez.
6. Son ekranda **Rayman 3 HD Recompiled'ı başlat** seçeneğiyle oyunu, **Ayarları aç** seçeneğiyle Settings uygulamasını açabilirsiniz.

Kurulumdan sonra oyuna ve ayarlara Başlat menüsünden veya oluşturmayı seçtiğiniz masaüstü kısayollarından ulaşabilirsiniz.

## Türkçe yama

Kurulum sırasında **Türkçe** seçerseniz Türkçe çeviri modu otomatik olarak kurulur ve etkinleştirilir.

Yama, oyun menülerini, diyalogları, altyazıları ve başarım metinlerini Türkçeleştirir.

Kurulumu İngilizce yaptıysanız da Türkçe yamayı sonradan ekleyebilirsiniz:

1. **Ayarlar → Modlar** bölümünü açın.
2. **.zip yükle** seçeneğine tıklayın.
3. Kurulum klasöründeki `extras\rayman3hd-turkish-1.0.1.zip` dosyasını seçin.
4. Yama kurulduktan sonra etkinleştirin ve oyunu yeniden başlatın.

Tekrar İngilizce oynamak için aynı sayfadan Türkçe yamayı devre dışı bırakabilirsiniz.

Kurulum sırasında seçtiğiniz dil, daha sonra oyunu hangi dilde oynamak zorunda olduğunuzu belirlemez.

Yama hakkında daha fazla bilgi için [Türkçe Yama rehberine](turkce-yama.md) bakabilirsiniz.

## Ayarlar uygulaması

Ayarlar uygulaması hem İngilizce hem Türkçe kullanılabilir.

Pencerenin sağ üst bölümündeki **Arayüz dili / Interface language** seçeneğiyle dili istediğiniz zaman değiştirebilirsiniz.

Yeni kurulumlarda arayüz dili, kurulum sırasında seçtiğiniz dildir. Güncellemelerde mevcut tercihiniz korunur.

**Ayarlar'ın arayüz dili ile oyunun dili birbirinden bağımsızdır.** Örneğin Settings'i İngilizce kullanırken oyunu Türkçe oynayabilirsiniz.

## Oyun profilleri

Ayarlar → Oyun profili bölümünde üç seçenek bulunur:

- **Vanilla:** Xbox 360 sürümünün görsel özelliklerini korur; PC'de çalışması için gerekli uyumluluk düzeltmelerini içerir.
- **HD+:** Vanilla'ya ek olarak Xbox 360 HD sürümündeki bazı görsel hatalara yönelik düzeltmeleri etkinleştirir.
- **Custom:** Düzeltmeleri ayrı ayrı seçmenize olanak tanır.

Oyun profili değiştirildiğinde diğer kişisel ayarlarınız sıfırlanmaz.

## Altyazılar

Oyunun kendi sinematik altyazıları başlangıçta kapalı olabilir. Bunları açmak için oyunun **Seçenekler → Ses → Altyazılar** menüsünü kullanın.

Oynanış sırasında duyulan seslendirmelerin altyazıları için ayrıca **Ayarlar → Düzeltmeler → Oynanış altyazıları** seçeneği bulunur.

Yeni HD+ kurulumlarında oynanış altyazıları açık, yeni Vanilla kurulumlarında kapalı başlar. Sonradan yaptığınız seçim korunur.

## Kontroller

Xbox uyumlu oyun kumandaları, Xbox 360 düğme düzeniyle çalışır.

Klavye için iki hazır düzen bulunur. **Ayarlar → Kontroller** bölümünden tuşları ayrı ayrı değiştirebilirsiniz.

| Eylem | Modern (varsayılan) | Özgün PC (2003) |
|---|---|---|
| Hareket | W A S D | Ok tuşları |
| Yürüme (basılı tut) | Ctrl | Shift |
| Kamera | Ok tuşları | Sayısal tuş takımı veya W A S D |
| Zıplama / helikopter | Boşluk | C |
| Saldırı (doldurmak için basılı tut) | E | Boşluk |
| Kilitlenme / yana hareket | Shift | Ctrl |
| Duraklat | Enter veya P | Esc |
| Geri | Esc veya Backspace | Backspace |

**Yürüme** tuşu, analog çubuğu hafifçe iterek yavaş hareket etme davranışının klavye karşılığıdır. Bu tuşu da değiştirebilir veya atamasını kaldırabilirsiniz.

Oyun kumandası düğmelerinin yeniden atanması henüz desteklenmiyor.

## DualSense özellikleri

Desteklenen fiziksel DualSense kontrolcülerinde ek özellikler kullanılabilir:

- **Dinamik ışık çubuğu:** Bulunduğunuz dünyaya ve kullandığınız güçlendirmeye göre renk değiştirir.
- **Uyarlanabilir R2 tetiği:** Uygun oynanış durumlarında R2 tuşuna direnç uygular.
- **Tetik sertliği ayarı:** Ayarlar → Gelişmiş bölümünden direnci %0 ile %100 arasında değiştirebilirsiniz.

Varsayılan tetik sertliği **%30**'dur. **%0**, direnci tamamen kapatır.

Işık çubuğu ve uyarlanabilir tetik özellikleri birbirinden bağımsız olarak açılıp kapatılabilir. Yeni kurulumlarda ikisi de varsayılan açık gelir; önceden kaydettiğiniz tercihler korunur.

Değişiklikler oyunu bir sonraki başlatışınızda uygulanır.

Steam Input veya sanal kontrolcü uygulamaları bazı DualSense özelliklerinin kullanılmasını engelleyebilir.

## Güncelleme ve onarım

Oyunu güncellemek veya onarmak için kurulum programını yeniden çalıştırın ve **mevcut kurulum klasörünü** seçin.

- Oyun kayıtları korunur.
- Kontrol ve görüntü ayarları korunur.
- Kurulu modlar ve açık/kapalı durumları korunur.
- Discord ve DualSense tercihleriniz korunur.

Kurulu oyun dosyaları sağlamsa Xbox 360 paketini yeniden seçmeniz gerekmez.

## Oyunu kaldırma

Windows **Ayarlar → Uygulamalar** bölümünden veya oyun klasöründeki kaldırıcıdan oyunu kaldırabilirsiniz.

Oyun kayıtları, ayarlar ve modlar, özellikle silmeyi seçmediğiniz sürece korunur.

## Sorun giderme

**Oyun paketim kabul edilmiyor.** Yalnızca başlık güncellemesi olmayan özgün Xbox Live Arcade sürümü desteklenir. Oyun kimliği `5841123F` olmalıdır.

**Eksik bileşen uyarısı alıyorum.** Öncelikle Microsoft Visual C++ Redistributable paketinin kurulu olduğundan emin olun. Sorun sürerse mevcut klasöre onarım kurulumu yapın.

**Sinematiklerde altyazı görünmüyor.** Oyunun kendi Seçenekler → Ses menüsünden Altyazılar seçeneğini açın.

**Tuşlar beklediğim gibi çalışmıyor.** Ayarlar → Kontroller bölümünden etkin klavye düzenini ve kişisel tuş atamalarınızı kontrol edin.

**DualSense ışığı veya tetik efekti çalışmıyor.** İlgili özelliklerin Ayarlar → Gelişmiş bölümünde açık olduğunu kontrol edin. Steam Input veya sanal kontrolcü yazılımları fiziksel DualSense'e doğrudan erişimi engelleyebilir.

**Oyun beklenmedik şekilde kapanıyor.** Kurulum klasöründeki `sessions\<tarih-saat>\` dizininde tanılama kayıtları oluşturulur. Sorun bildirirken ilgili oturumun kayıtlarını paylaşabilirsiniz; paylaşmadan önce kişisel bilgi içermediklerini kontrol edin.

---

**Rayman 3 HD Recompiled**, Ubisoft veya Microsoft tarafından geliştirilmemiş veya onaylanmamış bağımsız bir hayran projesidir. Oyun dosyaları projeyle birlikte dağıtılmaz.