# PAMAP2 Repair Decision Note

- PAMAP2 parser and loader were completed successfully, including real raw-data parsing and sensor-variant support.
- The best PAMAP2 sensor variant in repair experiments was `ankle`.
- The best combined Activity v2 repair result reached macro_f1 = 0.7935.
- The accepted UCI-HAR-only Activity v2 baseline remains stronger at macro_f1 = 0.8826.
- Because the best multisource result stayed materially below the accepted single-source baseline, the PAMAP2 multisource model is not accepted.
- PAMAP2 status: `integrated_but_not_accepted`.
- Current evidence does not show broken label mapping; the main issue is sensor placement / domain mismatch.
- MobiAct or another waist-aligned second ADL source is still recommended if multisource Activity v2 remains a target.

Runtime note:
- RiskFusion uses Activity v2 only as an `activity_context` provider.
- Activity v2 does not emit standalone alerts.
- Activity v2 is not a critical trigger source.
- Runtime activity source limitation: UCI-HAR-only accepted baseline.