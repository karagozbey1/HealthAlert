import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/models/enums.dart';
import 'package:mobile/core/services/recommendation_service.dart';

void main() {
  group('RecommendationService', () {
    test('returns richer guidance for higher severity', () {
      final service = RecommendationService();
      final watch = service.forSeverity(AlertSeverity.watch);
      final critical = service.forSeverity(AlertSeverity.critical);

      expect(watch.isNotEmpty, true);
      expect(critical.isNotEmpty, true);
      expect(critical.length >= watch.length, true);
    });
  });
}
