# Part 6 — BLE Model Window Pipeline + ML Evidence Personalization Fusion Report

## 1. Amaç
HealthAlert ML modelini canlı BLE 50Hz ham veri pencereleriyle güvenli biçimde karar akışına dahil etmek.

## 2. Neden 1Hz Summary Packet Yetmedi?
1Hz özet paketler modelin eğitimde kullandığı zaman serisi çözünürlüğünü taşımaz; 200 sample/4 saniye pencereli inference ile hizalı değildir.

## 3. Neden BLE 50Hz Raw Stream Seçildi?
Modelin eğitim varsayımıyla birebir uyum için 50Hz ham IMU+PPG akışı gerekir. BLE düşük gecikmeli canlı akış sağlar.

## 4. Firmware BLE 50Hz Raw Sample Tasarımı
Firmware tarafında 1Hz summary hattı korunurken ayrı BLE raw sample notify hattı eklendi; kontrol karakteristiği ile stream/mode/rate yönetimi yapıldı.

## 5. Host Bridge 200 Sample Window Collector
Host bridge ham örnekleri cihaz bazında buffer’layıp 200 sample’ı tamamlayınca model-ready pencereye dönüştürür ve kalite özeti üretir.

## 6. Backend /ingest/model-window Endpoint
Backend yeni endpoint ile pencereyi doğrular, kullanıcı eşlemesi yapar, ML inference çalıştırır, fusion uygulayıp final skoru günceller.

## 7. Model Window Validation
Shape, örnek sayısı, örnekleme hızı, pencere süresi ve kalite şartları doğrulanır; geçersiz payload 422 döner.

## 8. Offline Training Alignment
Canlı eğitim yoktur. Model-window export formatı offline fine-tuning/retrain için hazırlanmıştır.

## 9. Model-Window Export Formatı
`windows.jsonl`, `labels.jsonl`, `summary.json` formatı ile hashlenmiş kimlikler ve kalite/çıktı metadata’sı tutulur. Varsayılan export kapalıdır.

## 10. Statistical Personalization’ın ML Window ile Güncellenmesi
Profil katmanına ML evidence sayaçları, ortalama/std, disagreement ve son pencere metrikleri eklendi.

## 11. ML Evidence Score Formülü
`ml_evidence_score = 0.40*fall_prob + 0.25*instability_prob + 0.25*ml_risk_score + 0.10*(1-ppg_quality_score)`

## 12. ML Evidence Fusion Mantığı
ML katkısı güven kapıları (model_ready, confidence, sample_rate, ml_available) sonrası bounded adjustment olarak uygulanır.

## 13. final_risk_score Yeni Akışı
global heuristic risk -> personal baseline -> adaptive personalization -> bounded ML evidence adjustment -> final_risk_score

## 14. Neden ML Tek Başına Karar Vermiyor?
Güvenlik, açıklanabilirlik ve kişisel bağlam sürekliliği için ML yalnızca sınırlı katkı katmanıdır.

## 15. Neden ML Artık Final Skora Etki Ediyor?
Shadow moddan çıkıp canlı pencereden gelen gerçek kanıtı, üst limitle final skora dahil ederek pratik fayda sağlar.

## 16. Mobile Tek Final Skor Gösterimi
Mobilde tek final risk görünür; ML katkısı opsiyonel breakdown satırlarıyla açıklanır.

## 17. Test Sonuçları
Yeni ve regresyon backend testleri geçti. Host bridge window testleri geçti. Dry-run akışı doğrulandı.

## 18. Kalan Riskler
BLE binary chunk/CRC optimizasyonu ileri fazlarda geliştirilebilir. Flutter tarafında proje genelinde mevcut analyzer uyarı borcu sürmektedir.

## 19. Verdict
PARTIAL (Flutter analyze temiz değil; backend/host/firmware doğrulamaları başarılı)

Bu faz sonunda ML modeli yalnızca ayrı bir shadow çıktı olmaktan çıkarılmış; BLE üzerinden gelen gerçek 50Hz / 200 sample / 4 saniyelik model pencerelerini analiz eden, istatistiksel kişiselleştirme profilini besleyen ve final_risk_score’a güvenlik kapılı, sınırlı ve açıklanabilir katkı veren bir katman haline getirilmiştir.
