import 'package:flutter/material.dart';
import '../../../core/models/clinical_note.dart';
import '../../../core/models/user_profile.dart';
import '../../../core/state/app_scope.dart';
import '../../theme/app_theme.dart';
import '../../widgets/glass_card.dart';
import '../../widgets/gradient_button.dart';
class ClinicalNotesScreen extends StatefulWidget {
  final UserProfile patient;
  const ClinicalNotesScreen({super.key, required this.patient});

  /// Stateful ekran için kullanılacak durum nesnesini oluşturur.
  @override
  State<ClinicalNotesScreen> createState() => _ClinicalNotesScreenState();
}

/// Ekranın yerel durumunu ve kullanıcı etkileşimlerini yönetir.
class _ClinicalNotesScreenState extends State<ClinicalNotesScreen> {
  List<ClinicalNote> _notes = [];
  bool _loading = true;
  bool _adding = false;
  final _noteController = TextEditingController();
  final _recController = TextEditingController();

  /// Ekran açıldığında başlangıç verilerini ve dinleyicileri hazırlar.
  @override
  void initState() {
    super.initState();
    _loadNotes();
  }

  /// Ekran veya servis kapanırken timer, stream ve diğer kaynakları serbest bırakır.
  @override
  void dispose() {
    _noteController.dispose();
    _recController.dispose();
    super.dispose();
  }
  Future<void> _loadNotes({bool isRefresh = false}) async {
    if (!isRefresh || _notes.isEmpty) {
      if (mounted) setState(() => _loading = true);
    }
    try {
      final notes =
          await AppScope.of(context).getClinicalNotes(widget.patient.id);
      if (mounted) _notes = notes;
    } catch (e) {
      debugPrint('[ClinicalNotes] _loadNotes error: $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }
  Future<void> _addNote() async {
    final text = _noteController.text.trim();
    if (text.isEmpty) return;
    setState(() => _adding = true);
    try {
      final app = AppScope.of(context);
      final rec = _recController.text.trim();
      final note = await app.addClinicalNote(
        widget.patient.id,
        text,
        recommendation: rec.isNotEmpty ? rec : null,
      );
      if (mounted && note != null) {
        _noteController.clear();
        _recController.clear();
        await _loadNotes(isRefresh: true);
      }
    } catch (e) {
      debugPrint('[ClinicalNotes] _addNote error: $e');
    } finally {
      if (mounted) setState(() => _adding = false);
    }
  }

  /// Mevcut ekran durumuna göre Flutter arayüzünü oluşturur.
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.background,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        title: Text('Notlar — ${widget.patient.fullName}'),
      ),
      body: Column(
        children: [
          GlassCard(
            margin: const EdgeInsets.all(16),
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Klinik Not Ekle',
                    style: TextStyle(
                        color: Colors.amberAccent,
                        fontWeight: FontWeight.bold,
                        fontSize: 13)),
                const SizedBox(height: 12),
                TextField(
                  controller: _noteController,
                  style: const TextStyle(color: Colors.white),
                  maxLines: 3,
                  decoration: InputDecoration(
                    hintText: 'Klinik gözlemler...',
                    hintStyle: const TextStyle(color: Colors.white30),
                    filled: true,
                    fillColor: Colors.white.withOpacity(0.05),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(10),
                      borderSide: BorderSide.none,
                    ),
                  ),
                ),
                const SizedBox(height: 8),
                TextField(
                  controller: _recController,
                  style: const TextStyle(color: Colors.white),
                  maxLines: 2,
                  decoration: InputDecoration(
                    hintText: 'Öneriler (opsiyonel)...',
                    hintStyle: const TextStyle(color: Colors.white30),
                    filled: true,
                    fillColor: Colors.white.withOpacity(0.05),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(10),
                      borderSide: BorderSide.none,
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                SizedBox(
                  width: double.infinity,
                  child: GradientButton(
                    text: _adding ? 'KAYDEDİLİYOR...' : 'NOTU KAYDET',
                    isLoading: _adding,
                    onPressed: _addNote,
                  ),
                ),
              ],
            ),
          ),
          Expanded(
            child: _loading
                ? const Center(
                    child: CircularProgressIndicator(color: Colors.amberAccent))
                : _notes.isEmpty
                    ? const Center(
                        child: Text('Henüz klinik not yok.',
                            style: TextStyle(color: Colors.white38)))
                    : ListView.separated(
                        padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                        itemCount: _notes.length,
                        separatorBuilder: (_, __) => const SizedBox(height: 10),
                        itemBuilder: (context, i) => _noteCard(_notes[i]),
                      ),
          ),
        ],
      ),
    );
  }
  Widget _noteCard(ClinicalNote note) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppTheme.surface.withOpacity(0.4),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.amberAccent.withOpacity(0.15)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(note.note,
              style: const TextStyle(color: Colors.white, fontSize: 13)),
          if (note.recommendation != null &&
              note.recommendation!.isNotEmpty) ...[
            const SizedBox(height: 8),
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: Colors.amberAccent.withOpacity(0.08),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Icon(Icons.recommend_outlined,
                      size: 14, color: Colors.amberAccent),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      note.recommendation!,
                      style: const TextStyle(
                          color: Colors.amberAccent, fontSize: 12),
                    ),
                  ),
                ],
              ),
            ),
          ],
          const SizedBox(height: 8),
          Text(
            _fmt(note.createdAt),
            style: const TextStyle(color: Colors.white30, fontSize: 10),
          ),
        ],
      ),
    );
  }
  String _fmt(DateTime dt) =>
      '${dt.day.toString().padLeft(2, '0')}/${dt.month.toString().padLeft(2, '0')}/${dt.year} '
      '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
}
