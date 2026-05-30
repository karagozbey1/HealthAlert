# Final Decision — Dataset-Trained Model + Statistical Personalization Fusion Report

## 1. Amaç
Bu raporun amacı, HealthAlert için son karar mimarisinin veri politikası, canlı karar akışı, kişiselleştirme füzyonu, mobil görünürlük ve doğrulama sonuçlarını tek yerde kapatmaktır.

## 2. Final Mimari Özeti
Bu son mimaride HealthAlert modeli, açık/kapsamlı veri setlerinden çıkarılan 4 saniyelik zaman pencereleriyle offline olarak eğitilir; canlı sensör verisi eğitim için kullanılmaz, yalnızca inference ve kişisel istatistiksel kalibrasyon için kullanılır. Son kullanıcıya ve karar katmanlarına tek bir `final_risk_score` sunulur; eğitim metrikleri yalnızca raporlama ve model değerlendirme amacı taşır.

## 3. Karar Kuralları
- Sensörlerden canlı veri toplayıp model eğitimi yapılmaz.
- Model eğitimi internetten veya açık kaynaklardan bulunan kapsamlı veri setleriyle yürütülür.
- Zaman serileri 4 saniyelik pencerelere bölünür.
- Karar hattında tek otorite skor `final_risk_score` olur.
- Eğitim doğruluk, F1 ve benzeri metrikler canlı final skora doğrudan katılmaz.

## 4. Durum Tablosu
| Bölüm | Durum | Kanıt Dosyaları | Yapılan Aksiyon |
|---|---|---|---|
| Backend fusion servisi | Tamamlandı | `backend/services/risk_fusion_service.py`, `backend/routers/model_window_router.py` | ML taban skoru ile istatistiksel kişiselleştirmeyi tek final skorda birleştiren akış etkinleştirildi. |
| Model-window canlı yol | Tamamlandı | `backend/services/ml_inference_service.py`, `backend/routers/model_window_router.py` | 4 saniyelik pencere inference çıktıları normalize edilip aktif karar yoluna bağlandı. |
| Şema ve canlı durum görünürlüğü | Tamamlandı | `backend/models.py`, `backend/database.py`, `backend/schemas.py`, `backend/repositories/sqlite/repos.py` | Fusion breakdown alanları veri tabanı korumaları ve live response içine taşındı. |
| Offline dataset windowing | Tamamlandı | `healthalert_final_ai/src/data/windowing.py`, `healthalert_final_ai/scripts/build_windowed_training_dataset.py` | Açık veri setlerinden 4 saniyelik pencere üretimi ve normalizasyon hattı eklendi. |
| Smoke training | Tamamlandı | `healthalert_final_ai/scripts/train_window_model.py` | Export edilen window dataset üzerinde hafif smoke eğitim ve metadata üretimi sağlandı. |
| AI testleri | Tamamlandı | `healthalert_final_ai/tests/test_window_pipeline.py` | 4 saniye/200 sample, normalizasyon ve metadata üretimi test edildi. |
| Backend fusion regresyonu | Tamamlandı | `backend/tests/module7/test_26_model_personalization_fusion.py` | İstenen fusion kontratları için yeni testler eklendi ve regresyon paketi geçirildi. |
| Mobile final skor görünümü | Tamamlandı | `mobile/lib/core/models/live_status.dart`, `mobile/lib/ui/screens/dashboard_screen.dart` | Final risk ve fusion breakdown alanları dashboard'a eklendi. |
| Flutter analyzer temizliği | Kısmi | `mobile/lib/ui/screens/dashboard_screen.dart` | Dokunulan dosyadaki iki uyarı temizlendi; proje genelinde 274 mevcut analyzer issue kaldı. |

## 5. Neden Canlı Eğitim Yok?
Canlı sensör akışını eğitim verisine katmak veri sızıntısı, kalite tutarsızlığı ve cihaz/kişi bazlı aşırı uyum riski oluşturur. Bu nedenle canlı akış yalnızca inference, pencere doğrulama ve kişisel istatistik güncellemesi için kullanılır.

## 6. Eğitim Veri Kaynakları
Son mimaride eğitim tarafı `HIFD`, `WEDA_FALL` ve `BUT_PPG` veri setlerine bağlandı. Dataset metadata kayıtları `healthalert_final_ai/config/datasets.yaml` altında toplandı ve her kayıt için kaynak tipi, örnekleme hızı, etiket eşlemesi ve sensör sütunları tanımlandı.

## 7. 4 Saniyelik Pencere Standardı
Pencereleme mantığı `healthalert_final_ai/src/data/windowing.py` içinde açık şekilde tanımlandı. 50Hz için 4 saniye tam olarak 200 sample kabul edilir; 25Hz gibi daha yavaş kaynaklar eğitim formatına normalize edilir; 1Hz gibi akışlar hızlı model yerine yalnızca yavaş/istatistiksel kullanım için işaretlenir.

## 8. Window Kalitesi ve Normalizasyon
`segment_timeseries_to_windows`, `normalize_window_shape`, `assign_window_label` ve `compute_window_quality` fonksiyonları ile her pencerenin eğitim uygunluğu, sample sayısı ve kalite bayrakları belirlenir. Böylece eğitim ve canlı inference aynı pencere varsayımını paylaşır.

## 9. Offline Window Dataset Builder
`healthalert_final_ai/scripts/build_windowed_training_dataset.py` script'i dataset registry'den yükleme yapıp standart kayıtlardan subject-aware split ile window dataset üretir. CLI seviyesinde `--dry-run`, `--window-sec`, `--stride-sec`, `--output-dir` ve `--max-records-per-dataset` desteklenir.

## 10. Smoke Trainer
`healthalert_final_ai/scripts/train_window_model.py` export edilen dataset üzerinde hafif bir smoke eğitim çalıştırır ve `healthalert_window_model.pt` ile `model_metadata.json` üretir. Bu aşama eğitim kalitesini garantilemek için değil, pipeline'ın uçtan uca çalıştığını göstermek için eklendi.

## 11. Eğitim Metriklerinin Karar Skorundaki Rolü
Eğitimden çıkan accuracy, precision, recall veya F1 değerleri çalışma zamanında `final_risk_score` hesabına sokulmaz. Bu kural hem tasarımda hem de `backend/tests/module7/test_26_model_personalization_fusion.py` içinde korundu.

## 12. Backend Fusion Yapısı
`backend/services/risk_fusion_service.py`, üç kaynağı aynı yerde toplar: model taban skoru, baseline/heuristic risk ve adaptif kişiselleştirme çıktıları. Sonuç olarak şu breakdown alanları üretilir: `ml_base_score`, `heuristic_risk_score`, `baseline_adjusted_risk`, `personalized_risk_score`, `personal_adjustment`, `quality_adjustment`, `safety_adjustment`, `final_risk_score`, `fusion_mode`, `fusion_reason`, `model_version`.

## 13. ML Mevcutken ve Yokken Davranış
ML hazır olduğunda base skor doğrudan `ml_risk_score` olur ve `fusion_mode=model_plus_personalization` seçilir. ML hazır değilse sistem `fallback_personalization_only` moduna geçer ve kişiselleştirilmiş risk skoru güvenli geri dönüş tabanı olarak kullanılır.

## 14. Kişiselleştirme Limitleri
Pozitif kişisel düzeltme üst sınırı `+0.20` ile sınırlandı. Negatif düzeltme varsayılan olarak kapalı bırakıldı. Final skor her durumda `0..1` aralığına clamp edilir.

## 15. Model-Window Canlı Karar Akışı
`backend/routers/model_window_router.py` içinde canlı 4 saniyelik pencere alındığında ML inference normalize edilir, mevcut baseline ve personalization çıktıları toplanır, ardından aktif final karar `risk_fusion_service` ile hesaplanır. Önceki `ml_evidence` yolu geriye dönük uyumluluk için bırakılmış, ancak ana skor hattı yeni fusion servisine çevrilmiştir.

## 16. Veri Tabanı ve API Yansımaları
`ModelWindowLog` genişletildi; SQLite şema korumaları yeni kolonlar için eklendi; `LiveStatusResponse` ve SQLite live repo enrich katmanı fusion breakdown alanlarını mobil istemciye taşır. Bu sayede ayrı tablo göçü yapmadan son live durumda model versiyonu ve güven bilgisi görülebilir.

## 17. Mobile Tek Final Skor Sunumu
Mobilde `live_status.dart` ile yeni alanlar parse edilir ve `dashboard_screen.dart` üstünde tek ana skor olarak `Final risk skoru` gösterilir. İsteğe bağlı breakdown satırlarında `Model skoru`, `Kişisel düzeltme`, `Güven/kalite`, `Fusion modu` ve `Model sürümü` yer alır.

## 18. Doğrulama Sonuçları
Backend tarafında istenen regresyon paketi şu komutla çalıştırıldı: `python -m pytest tests/module7/test_16_baseline_mvp.py tests/module7/test_17_ml_shadow_mode.py tests/module7/test_20_final_integration_e2e.py tests/module7/test_23_adaptive_personalization.py tests/module7/test_25_full_system_live_integration.py tests/module7/test_26_model_personalization_fusion.py -v --tb=short` ve sonuç `188 passed, 153 warnings` oldu. AI tarafında `healthalert_final_ai/tests/test_window_pipeline.py` içindeki 4 test geçti.

## 19. Veri Seti ve Smoke Pipeline Kanıtları
Dry-run çıktılarına göre HIFD, WEDA_FALL ve BUT_PPG üzerinden toplam 11188 pencere sayıldı; smoke build senaryosunda train/val/test split ile 1297 pencere üretildi. Smoke eğitim artefaktları `outputs/models_smoke/healthalert_window_model.pt` ve `outputs/models_smoke/model_metadata.json` olarak yazıldı.

## 20. Flutter Analyze Durumu
`flutter analyze` yeniden çalıştırıldı ve sonuç `274 issues found` olarak döndü. Dokunulan dashboard dosyasındaki kullanılmayan import ve gereksiz null-aware ifade temizlendi; kalan issue'lar proje genelindeki mevcut analyzer/deprecation borcudur ve bu iş kapsamında topluca yeniden yazılmadı.

## 21. Verdict
Son karar mimarisi, kullanıcının koyduğu kısıtlara uyacak şekilde uygulanmıştır: eğitim açık veri setlerinden türetilmiş 4 saniyelik pencerelerle offline yapılır, canlı akış yalnızca inference ve istatistiksel kişiselleştirme için kullanılır, nihai karar tek bir `final_risk_score` ile verilir ve mobil/backend görünürlüğü bu skora göre hizalanır. Kapanış durumu `COMPLETE WITH EXISTING ANALYZER DEBT` olarak değerlendirilebilir; fonksiyonel backend ve AI doğrulamaları geçmiştir, Flutter tarafında ise repo genelinde önceden var olan 274 analyzer issue kalmaktadır.