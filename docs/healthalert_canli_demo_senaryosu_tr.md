# HealthAlert Canli Demo Senaryosu (Turkce)

Bu dokuman, sunum sirasinda adim adim uygulanacak canli gosterim akisini tanimlar.

## 1) Demo Hedefi

Canli demoda su 3 hedef gosterilir:
- SELF kullanicinin canli verisi uretimi ve goruntulenmesi
- DOCTOR ve RELATIVE rollerinin bagli hastayi gorebilmesi
- Yetkisiz erisimin 403 ile engellenmesi

## 2) Demo On Kosullari

- Backend ayakta
- Mobil uygulama backend URL ile acilmis
- Demo hesaplar hazir:
  - self@demo.com / demo1234
  - relative@demo.com / demo1234
  - doctor@demo.com / demo1234
- Device ID: ha-esp32-001
- Firmware config referansi: [firmware/include/ha_config.h](firmware/include/ha_config.h)

## 3) Sunum Akisi (Dakika Bazli)

### Adim 1 - Sistem Acilisi (1-2 dk)

- Kisa mimari ozeti verilir
- Endpoint grubu belirtilir:
  - /patients/accessible
  - /patients/{id}/live
  - /patients/{id}/summary

Beklenen mesaj:
- Veri tekil endpointlerden degil, rol bazli erisim katmanindan okunur.

### Adim 2 - SELF Girisi (2 dk)

- SELF kullanici ile login
- Kendi canli veri kartlari gosterilir (BPM, SpO2, risk, hareket)

Beklenen sonuc:
- SELF sadece kendine ait veriyi gorur.

### Adim 3 - DOCTOR Girisi (2-3 dk)

- DOCTOR kullanici ile login
- Hasta listesi acilir (accessible patients)
- Secilen hasta icin:
  - Live endpoint cagrisi
  - Summary endpoint cagrisi

Beklenen sonuc:
- Doktor bagli hastayi gorebilir.
- Ozet kartta risk seviyesi ve son gorulme bilgisi gorunur.

### Adim 4 - RELATIVE Girisi (2-3 dk)

- RELATIVE kullanici ile login
- Bagli hastayi listede goruntuleme
- Canli ve ozet veriyi acma

Beklenen sonuc:
- Hasta yakini sadece iliskili hastayi gorur.

### Adim 5 - ACL Kaniti (2 dk)

- RELATIVE ile iliskisiz bir user_id icin /patients/{id}/live cagrisi

Beklenen sonuc:
- 403 Forbidden
- "Access denied" davranisi

### Adim 6 - Kapanis (1 dk)

- Cikti ozeti:
  - Rol bazli hasta goruntuleme calisiyor
  - ACL endpoint seviyesinde uygulanmis
  - Mobil fallback uyumlulugu korunmus

## 4) Teknik Kontrol Listesi

Sunum oncesi:
- Backend route kaydi aktif mi?
- Demo seed hesaplar olustu mu?
- Mobil backend URL dogru mu?
- Device packet akisinda data var mi?

Sunum sirasinda:
- Hasta listesi bos gelirse önce /patients/accessible kontrol edilir
- Live alanlari bossa paket kaynagi kontrol edilir
- ACL testi icin kasitli yetkisiz id kullanilir

## 5) Olası Sorunlar ve Hizli Cozumler

- Sorun: Backend import/module path hatasi
  - Cozum: Uygun app-dir veya backend cwd ile calistirma

- Sorun: Live quality alanlari null geliyor
  - Cozum: DevicePacketLog uretimi ve ingest akisinin aktifligini dogrula

- Sorun: Mobilde role gore liste bos
  - Cozum: /patients/accessible cevabi ve relation seed kayitlarini kontrol et

## 6) Demo Cikti Metni (Kisa)

"HealthAlert sisteminde SELF, RELATIVE ve DOCTOR rolleri icin veri gorunurlugu net olarak ayrilmistir. Doktor ve hasta yakini sadece iliskili hastayi gorebilir. Yetkisiz erisimler 403 ile engellenir. Bu yapi hem guvenlik hem de operasyonel izlenebilirlik gereksinimlerini karsilar."

## 7) Ilgili Dokumanlar

- Yonetici ozeti: [docs/healthalert_yonetici_ozeti_tr.md](docs/healthalert_yonetici_ozeti_tr.md)
- Kapsamli teknik rapor: [docs/healthalert_kapsamli_proje_raporu_tr.md](docs/healthalert_kapsamli_proje_raporu_tr.md)
- Sunum paketi index: [docs/healthalert_sunum_paketi_tr.md](docs/healthalert_sunum_paketi_tr.md)
