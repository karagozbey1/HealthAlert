# Part 6 — BLE Model Window + ML Evidence Fusion Raporu

## 1. Amaç
Eğitilmiş ML modelini gerçek BLE 50Hz ham sensör pencereleriyle canlıda kullanılabilir hale getirmek ve çıktısını final risk skoruna güvenlik kapılı şekilde entegre etmek.

## 2. Neden 1Hz Summary Packet Yetmedi?
1Hz özet paketler modelin beklediği zaman çözünürlüğünü ve ham sinyal şeklini taşımaz; 50Hz/200 örnek pencerede öğrenilen örüntüler 1Hz özetten güvenilir çıkarılamaz.

## 3. Neden BLE 50Hz Raw Stream Seçildi?
Model eğitim kontratı 50Hz ham IMU+PPG pencereye dayalıdır. BLE notify hattı düşük gecikmeli olarak bu ham örnekleri host bridge’e taşıyabildiği için seçildi.

## 4. Firmware BLE 50Hz Raw Sample Tasarımı
- `ha_config.h` içine model stream sabitleri eklendi.
- BLE GATT’e `raw sample`, `control write`, `status read` karakteristikleri eklendi.
- `model_stream_on/off`, `raw_rate_50/25`, `summary_on/off`, `real_mode/mock_mode` komutları işlendi.
- 1Hz summary hattı korunurken 50Hz raw JSONL notify akışı eklendi.

## 5. Host Bridge 200 Sample Window Collector
- Yeni `host_bridge/ble_model_window_collector.py` eklendi.
- BLE/mock/replay kaynaklarından ham örnek toplayıp 200 örnekte bir model-window üretiyor.
- `quality_summary` hesaplıyor, `--dry-run` modunda sadece doğrulama/log yapıyor.
- Ağ hatalarında retry queue (20 pencere) kullanıyor.

## 6. Backend /ingest/model-window Endpoint
- Yeni `POST /ingest/model-window` endpoint’i eklendi.
- Cihaz eşleşmesi yapılıyor, model-window doğrulanıyor, model inference çağrılıyor.
- Fail-open mantığıyla model yoksa 500 üretmeden akış devam ediyor.

## 7. Model Window Validation
- Şema seviyesinde `sample_count`/uzunluk eşleşmesi, IMU 6 kanal, PPG 1/2 kanal doğrulaması var.
- Adapter servisinde `model_ready` kapısı: 200 örnek, 50Hz, ~4s pencere şartları.
- Uygun olmayan pencerelerde ML katkısı otomatik 0 kalıyor.

## 8. Offline Training Alignment
Canlı eğitim yapılmıyor; ancak backend tarafında model-window ham export (config kapılı) ve AI tarafında yeni loader ile offline fine-tuning hazırlığı sağlandı.

## 9. Model-Window Export Formatı
- `outputs/model_windows/<timestamp>/windows.jsonl`
- `labels.jsonl`
- `summary.json`
- Kimlikler hashlenmiş (`user_id_hash`, `device_id_hash`), ham export varsayılan kapalı.

## 10. Statistical Personalization’ın ML Window ile Güncellenmesi
`PersonalHealthProfile` ML-window metrikleriyle genişletildi (`ml_window_count`, `ml_evidence_mean/std`, disagreement sayaçları vb.).  
`update_profile_from_ml_window(...)` ile her model-window sonrası profil hafızası güncelleniyor.

## 11. ML Evidence Score Formülü
`ml_evidence_score = 0.40*fall_prob + 0.25*instability_prob + 0.25*ml_risk_score + 0.10*(1-ppg_quality_score)`

## 12. ML Evidence Fusion Mantığı
- Config kapıları: enable, min confidence, model_ready şartı, sample-rate şartı.
- `delta = ml_evidence_score - personalized_risk_score`
- Pozitif katkı: `min(delta * weight, +0.15)`
- Negatif katkı default kapalı.

## 13. final_risk_score Yeni Akışı
`global heuristic risk -> personal baseline -> adaptive personalization -> ML evidence bounded adjustment -> final_risk_score`

## 14. Neden ML Tek Başına Karar Vermiyor?
Sistem güvenliği ve açıklanabilirlik için alarm zinciri tek başına ML kararına bırakılmadı; ML sadece bounded evidence katkısı sağlar.

## 15. Neden ML Artık Final Skora Etki Ediyor?
Önceki shadow durumunda operasyonel etkisi yoktu. Bu fazda gerçek model-window inference çıktısı kontrollü biçimde final skora dahil edildi.

## 16. Mobile Tek Final Skor Gösterimi
`LiveStatus` modeli opsiyonel fusion alanlarıyla genişletildi; dashboard’da tek final risk ve ML katkı bilgisi küçük açıklama olarak gösteriliyor.

## 17. Test Sonuçları
Yeni test setleri eklendi:
- `test_26_model_window_pipeline.py`
- `test_27_ml_evidence_fusion.py`
- `test_28_personalization_ml_window_profile.py`

## 18. Kalan Riskler
- Firmware tarafında compact binary + chunk/CRC yerine JSONL debug notify kullanımı devam ediyor.
- Gerçek cihaz/MTU senaryolarında chunk reassembly için ek sertleştirme gerekebilir.

## 19. Verdict
Part 6 çekirdeği (BLE model-window pipeline, backend model-window endpoint, bounded ML fusion, personalization ML memory, offline loader/validator, mobile görünüm) entegre edilmiştir.

“Bu faz sonunda ML modeli yalnızca ayrı bir shadow çıktı olmaktan çıkarılmış; BLE üzerinden gelen gerçek 50Hz / 200 sample / 4 saniyelik model pencerelerini analiz eden, istatistiksel kişiselleştirme profilini besleyen ve final_risk_score’a güvenlik kapılı, sınırlı ve açıklanabilir katkı veren bir katman haline getirilmiştir.”
