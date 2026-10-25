; M48-P (D-087): Türkçe metinler, tools\installer\r3hd_setup.iss için (Inno Setup'ın Languages\Turkish.isl dosyasıyla
; birlikte). Anahtarlar r3hd_en.isl ile birebir aynı olmalıdır. Ajan tarafından yazıldı: anadil konuşanının gözden
; geçirmesi bekleniyor. Settings penceresi İngilizcedir; onun düğme ve sayfa adları özgün hâliyle tırnak içinde yazılır.

[Messages]
WelcomeLabel2=Bu kurulum, Xbox 360 oyununun kendi kopyanızdan oluşturulan yerel Windows sürümü Rayman 3 HD Recompiled'ı kurar.%n%nGerekenler:%n  - konsolunuzdan kopyaladığınız kendi Rayman 3 HD Xbox 360 paketiniz (özgün Xbox Live Arcade sürümü, başlık güncellemesi olmadan);%n  - Microsoft Visual C++ 2015-2022 (x64) yeniden dağıtılabilir paketi kurulu Windows 10 veya 11 (64 bit);%n  - yaklaşık 2,3 GB boş alan.%n%nPaketiniz yalnızca okunur, hiçbir zaman değiştirilmez ve her oyun dosyası denetlenir. Yönetici izni gerekmez.
FinishedLabel=Rayman 3 HD Recompiled kuruldu.%n%nOyunu masaüstünden ya da Başlat menüsünden başlatabilirsiniz.

[CustomMessages]
TaskGroup=Kısayollar:
TaskDesktop=&Masaüstü kısayolu oluştur (Oyna)
TaskSettings=&Ayarlar için masaüstü kısayolu oluştur (ekran, grafik, klavye)
PlayComment=Kayıtlı ayarlarınızla oynayın
SettingsComment=Ekran, grafik, klavye ve oyun profili
RunPlay=Rayman 3 HD Recompiled'ı başlat
RunSettings=Ayarları aç

EngineFailed=Kurulum motoru başarısız oldu (çıkış kodu %1).
EtaEstimating=kalan süre hesaplanıyor...
EtaUnderMinute=bir dakikadan az kaldı
EtaMinute=yaklaşık bir dakika kaldı
EtaMinutes=yaklaşık %1 dakika kaldı
Step_payload=Uygulama kopyalanıyor
Step_extract=Oyun dosyaları paketinizden çıkarılıyor
Step_check=Oyun dosyalarınız denetleniyor
Step_copy=Oyun dosyalarınız kopyalanıyor
Step_verify=Çıkarılan her oyun dosyası denetleniyor
Step_commit=Kurulum tamamlanıyor
Preparing=Hazırlanıyor
Cancelling=İptal ediliyor... şimdiye kadar hazırlanan dosyalar siliniyor; hiçbir şey değiştirilmiyor.
CancelConfirm=Kurulum iptal edilsin mi?%n%nKurulum klasöründe hiçbir şey değişmez; şimdiye kadar hazırlanan dosyalar silinir.
DetailFiles=%1 / %2 dosya
DetailMB=%1 / %2 MB
VcMissing=Microsoft Visual C++ 2015-2022 (x64) yeniden dağıtılabilir paketi eksik.%nMicrosoft'tan kurun (aka.ms/vs/17/release/vc_redist.x64.exe), ardından bu kurulumu yeniden çalıştırın.
PayloadFailed=Kurulumun kendi dosyaları açılamadı.

PackageTitle=Oyun paketiniz
PackageDesc=Kendi Rayman 3 HD Xbox 360 paketinizi seçin.
PackageText=Gözat ile konsolunuzdan kopyaladığınız tek Xbox 360 Xbox Live Arcade paket dosyasını seçin: Content\0000000000000000\5841123F\000D0000\... Dosyanın adı genellikle uzun bir onaltılık dizidir ve uzantısı yoktur. Klasörü, ISO veya ZIP arşivini ya da oyunun PC sürümünü değil, dosyanın kendisini seçin. Kurulum, desteklenen Rayman 3 HD paketi olduğunu denetler ve oyun dosyalarını çıkarır; özgün dosyanız değişmez. Güncelleme veya onarımda kurulu oyun dosyaları sağlamsa bu alanı boş bırakabilirsiniz.
PackageLabel=Paket dosyası:
PackageFilter=Tüm dosyalar|*.*
VerifyBox=Kurulu her oyun dosyasını denetle (onarım; yaklaşık bir dakika)
PackageNeeded=Rayman 3 HD paketinizi seçin: oyun dosyaları ondan çıkarılır.
PackageUnusable=Bu paket kullanılamıyor.

PresetTitle=Oyun profili
PresetDesc=Oyun nasıl görünsün? Bunu Rayman 3 HD ayarlarında istediğiniz zaman değiştirebilirsiniz.
PresetText=Tam ekran ve işleme çözünürlüğü gibi ekran ve grafik seçenekleri kurulumdan sonra Rayman 3 HD ayarlarında belirlenir; şimdi bunlarla ilgili bir şey seçmeniz gerekmez.
PresetVanilla=Vanilla - PC'de gereken düzeltmelerle Xbox 360 sürümü
PresetHdplus=HD+ (Önerilen) - Vanilla ile birlikte Xbox 360 sürümündeki görüntü hatalarının düzeltmeleri
PresetCustom=Custom - her düzeltmeyi daha sonra Rayman 3 HD ayarlarında kendiniz seçin
PresetKeep=Geçerli ayarlarımı koru (var olan kurulum)

ProgressTitle=Kuruluyor
ProgressDesc=Rayman 3 HD Recompiled kuruluyor. Oyun dosyaları paketinizden çıkarılıyor ve her dosya denetleniyor.
CancelInstallButton=Kurulumu &iptal et
InstallCancelled=Kurulum iptal edildi. Kurulum klasöründe hiçbir şey değiştirilmedi.
CancelTooLate=İptal ettiğinizde kurulum son adımına ulaşmıştı; bu yüzden tamamlandı.
NothingChanged=Kurulum klasöründe hiçbir şey değiştirilmedi.
FinishedBase=Rayman 3 HD Recompiled kuruldu.%n%nOyunu masaüstünden ya da Başlat menüsünden başlatabilirsiniz.

MemoFolder=Kurulum klasörü:
MemoExisting=(var olan kurulum: güncelleme / onarım; kayıtlar ve ayarlar korunur)
MemoGameFiles=Oyun dosyaları:
MemoChecked=(denetlendi; kurulum sırasında her dosya yeniden denetlenir)
MemoKeepFiles=kurulu oyun dosyalarını koru
MemoProfile=Oyun profili:
MemoDisplay=Ekran ve grafik:
MemoDisplayLater=istediğiniz zaman Rayman 3 HD ayarlarında değiştirin
MemoSpace=Gereken alan: yaklaşık 2,3 GB (oyun dosyaları 2,1 GB, uygulama 70 MB).

UninstallRefused=Rayman 3 HD Recompiled şu anda kaldırılamıyor. Hiçbir şey silinmedi.
UninstallUserData=Kayıtlarınız, ayarlarınız, modlarınız ve oturum günlükleriniz de silinsin mi?%n%nSaklamak için Hayır'ı seçin (önerilir): aynı klasöre daha sonra yapılan bir kurulum bunları yeniden kullanır.
UninstallPartial=Bazı dosyalar silinmedi: %1

; --- yalnızca iki dilli kurulum (BundledMod) ---
LangPageTitle=Kurulum dili
LangPageDesc=Bu kurulumun dilini seçin.
LangSwitchFailed=Kurulum diğer dilde başlatılamadı (%1). Bu dilde devam edebilirsiniz.

TurkishNoteFreshTr=Türkçe çeviri kurulur ve açılır.
TurkishNoteFreshEn=Oyun İngilizce kurulur.
TurkishNoteUpgrade=Şu an kurulu: %1 sürümü (%2). Bu kurulumun sürümüne güncellenir; durumu (%2) ve mod listenizdeki yeri korunur.
TurkishNoteSame=Türkçe çevirinin bu sürümü zaten kurulu (%1); olduğu gibi kalır.
TurkishNoteNewer=Daha yeni bir Türkçe sürüm (%1) kurulu; korunur, değiştirilmez.
TurkishNoteDifferent=Bu Türkçe sürümün başka bir kopyası kurulu; korunur, değiştirilmez.
TurkishNoteAbsent=Bu kurulumda Türkçe çeviri yok ve şimdi de eklenmez. "Rayman 3 HD Recompiled - Settings" > Mods > Install .zip ile ekleyebilirsiniz (dosya, kurulum klasöründeki extras klasöründedir).
TurkishNoteUnknown=Bu klasördeki kurulu modlar okunamadı; Türkçe çeviri olduğu gibi bırakılır.
TurkishNotInstalled=Türkçe çeviri kurulmadı. Oyun özgün İngilizce metni gösterir.
StateOn=açık
StateOff=kapalı
MemoTurkish=Türkçe çeviri:
StepTurkish=Türkçe çeviri ekleniyor...
StepSubs=Altyazı ayarı kaydediliyor...
TurkishFailed=Oyun kuruldu, ancak Türkçe çeviri eklenemedi: %1
TurkishDoneOn=Türkçe çeviri %1 kuruldu ve açıldı. İngilizce oynamak için "Rayman 3 HD Recompiled - Settings" > Mods bölümünden kapatın.
TurkishDoneOff=Türkçe çeviri %1 kuruldu ve sizin bıraktığınız gibi kapalı kaldı. "Rayman 3 HD Recompiled - Settings" > Mods bölümünden açabilirsiniz.
SubsFailed=Altyazı ayarı kaydedilemedi: %1
SubsDoneOn=Oynanış altyazıları açık. İlk oyundan önce oyunun seçeneklerini (Audio) açıp Subtitles ayarını açın: yeni bir oyun profili bu ayar kapalı başlar.
SubsDoneOff=Oynanış altyazıları kapalı (ara sahne altyazıları oyunun kendi Subtitles ayarına uyar).
