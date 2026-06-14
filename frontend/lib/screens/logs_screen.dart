import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/trading_provider.dart';

class LogsScreen extends StatefulWidget {
  const LogsScreen({super.key});

  @override
  State<LogsScreen> createState() => _LogsScreenState();
}

class _LogsScreenState extends State<LogsScreen> {
  DateTime? _selectedDate;
  bool _isLoading = false;

  @override
  void initState() {
    super.initState();
    // Auto-fetch logs when screen opens — wakes Render + loads SQLite fallback
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadLogs();
    });
  }

  Future<void> _loadLogs() async {
    setState(() => _isLoading = true);
    final provider = Provider.of<TradingProvider>(context, listen: false);
    await provider.fetchLogs();
    if (mounted) setState(() => _isLoading = false);
  }

  Future<void> _selectDate(BuildContext context) async {
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: _selectedDate ?? DateTime.now(),
      firstDate: DateTime(2025),
      lastDate: DateTime(2030),
      builder: (context, child) {
        return Theme(
          data: Theme.of(context).copyWith(
            colorScheme: const ColorScheme.dark(
              primary: Colors.cyanAccent,
              onPrimary: Colors.black,
              surface: Color(0xFF0F0F1A),
              onSurface: Colors.white,
            ),
            dialogTheme: const DialogThemeData(backgroundColor: Color(0xFF0F0F1A)),
          ),
          child: child!,
        );
      },
    );
    if (picked != null && picked != _selectedDate) {
      setState(() => _selectedDate = picked);
    }
  }

  /// FIX: Date filter now checks BOTH entry timestamp AND exit_time.
  /// Previously only checked entry time — so filtering by the close date
  /// (e.g., trade entered yesterday, closed today) showed nothing.
  bool _matchesDate(dynamic log, DateTime date) {
    bool match(dynamic ts) {
      if (ts == null) return false;
      final ms = _parseTimestamp(ts);
      if (ms == 0) return false;
      final dt = DateTime.fromMillisecondsSinceEpoch(ms);
      return dt.year == date.year && dt.month == date.month && dt.day == date.day;
    }
    return match(log['timestamp']) || match(log['exit_time']);
  }

  /// Format millisecond timestamp → "DD/MM/YYYY  HH:MM"
  String _formatDT(dynamic ts) {
    if (ts == null) return '--';
    final ms = _parseTimestamp(ts);
    if (ms == 0) return '--';
    final dt = DateTime.fromMillisecondsSinceEpoch(ms);
    final d = dt.day.toString().padLeft(2, '0');
    final mo = dt.month.toString().padLeft(2, '0');
    final h = dt.hour.toString().padLeft(2, '0');
    final mi = dt.minute.toString().padLeft(2, '0');
    return '$d/$mo/${dt.year}  $h:$mi';
  }

  int _parseTimestamp(dynamic ts) {
    if (ts == null) return 0;
    if (ts is num) return ts.toInt();
    return double.tryParse(ts.toString())?.toInt() ?? 0;
  }

  @override
  Widget build(BuildContext context) {
    final provider = Provider.of<TradingProvider>(context);

    // Filter logs by selected date (entry OR exit matches)
    final filteredLogs = provider.signals.where((log) {
      if (_selectedDate == null) return true;
      return _matchesDate(log, _selectedDate!);
    }).toList();

    // Sort: latest (by exit_time if closed, else entry time) first
    filteredLogs.sort((a, b) {
      final aT = _parseTimestamp(a['exit_time'] ?? a['timestamp'] ?? 0);
      final bT = _parseTimestamp(b['exit_time'] ?? b['timestamp'] ?? 0);
      return bT.compareTo(aT);
    });

    return Scaffold(
      backgroundColor: const Color(0xFF040408),
      body: Stack(
        children: [
          _buildMeshBackground(),
          if (_isLoading)
            const Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  CircularProgressIndicator(color: Colors.cyanAccent, strokeWidth: 2),
                  SizedBox(height: 16),
                  Text(
                    'FETCHING MISSION LOGS...',
                    style: TextStyle(
                      color: Colors.white24,
                      fontSize: 10,
                      fontWeight: FontWeight.w900,
                      letterSpacing: 3,
                    ),
                  ),
                ],
              ),
            )
          else
          CustomScrollView(
            physics: const BouncingScrollPhysics(),
            slivers: [
              // ── AppBar ───────────────────────────────────────────────
              SliverAppBar(
                expandedHeight: 120,
                floating: true,
                pinned: true,
                elevation: 0,
                backgroundColor: Colors.transparent,
                flexibleSpace: ClipRRect(
                  child: BackdropFilter(
                    filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
                    child: FlexibleSpaceBar(
                      title: const Text(
                        'MISSION LOGS',
                        style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: 4, fontSize: 14),
                      ),
                      background: Container(color: Colors.black.withValues(alpha: 0.3)),
                    ),
                  ),
                ),
                actions: [
                  IconButton(
                    icon: Icon(
                      Icons.calendar_today_rounded,
                      color: _selectedDate != null ? Colors.cyanAccent : Colors.white60,
                    ),
                    tooltip: 'Filter by Date',
                    onPressed: () => _selectDate(context),
                  ),
                  if (_selectedDate != null)
                    IconButton(
                      icon: const Icon(Icons.clear_rounded, color: Colors.redAccent),
                      tooltip: 'Clear Filter',
                      onPressed: () => setState(() => _selectedDate = null),
                    ),
                  IconButton(
                    icon: const Icon(Icons.sync_rounded, color: Colors.cyanAccent),
                    tooltip: 'Sync',
                    onPressed: () async {
                      await _loadLogs();
                    },
                  ),
                ],
              ),

              // ── Active filter chip ────────────────────────────────────
              if (_selectedDate != null)
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(20, 16, 20, 0),
                    child: Row(
                      children: [
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                          decoration: BoxDecoration(
                            color: Colors.cyanAccent.withValues(alpha: 0.1),
                            borderRadius: BorderRadius.circular(12),
                            border: Border.all(color: Colors.cyanAccent.withValues(alpha: 0.3)),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              const Icon(Icons.date_range_rounded, color: Colors.cyanAccent, size: 13),
                              const SizedBox(width: 8),
                              Text(
                                'Filter: ${_selectedDate!.day.toString().padLeft(2, '0')}/${_selectedDate!.month.toString().padLeft(2, '0')}/${_selectedDate!.year}'
                                '  •  ${filteredLogs.length} trade${filteredLogs.length == 1 ? '' : 's'}',
                                style: const TextStyle(
                                  color: Colors.cyanAccent,
                                  fontSize: 11,
                                  fontWeight: FontWeight.bold,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ),

              // ── Log list ──────────────────────────────────────────────
              SliverPadding(
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 20),
                sliver: filteredLogs.isEmpty
                    ? SliverFillRemaining(
                        child: Center(
                          child: Column(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              const Icon(Icons.search_off_rounded, color: Colors.white10, size: 48),
                              const SizedBox(height: 16),
                              Text(
                                _selectedDate != null
                                    ? 'NO TRADES ON\n'
                                        '${_selectedDate!.day.toString().padLeft(2, '0')}/'
                                        '${_selectedDate!.month.toString().padLeft(2, '0')}/'
                                        '${_selectedDate!.year}'
                                    : 'NO MISSION DATA DETECTED',
                                textAlign: TextAlign.center,
                                style: const TextStyle(
                                  color: Colors.white10,
                                  fontWeight: FontWeight.w900,
                                  letterSpacing: 4,
                                  fontSize: 10,
                                ),
                              ),
                            ],
                          ),
                        ),
                      )
                    : SliverList(
                        delegate: SliverChildBuilderDelegate(
                          (context, index) => _buildLogTile(filteredLogs[index]),
                          childCount: filteredLogs.length,
                        ),
                      ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  // ── Log Tile ─────────────────────────────────────────────────────────────

  Widget _buildLogTile(dynamic log) {
    final isBuy    = log['signal'] == 'BUY';
    final isClosed = log['status'] == 'CLOSED';
    final Color accentColor = isBuy ? Colors.greenAccent : Colors.redAccent;
    final pnl      = (log['pnl'] ?? 0.0) as num;
    final isProfit = pnl >= 0;

    return Container(
      margin: const EdgeInsets.only(bottom: 18),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: accentColor.withValues(alpha: 0.18)),
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(22),
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
          child: Container(
            color: accentColor.withValues(alpha: 0.025),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [

                // ── Header: symbol / side / PnL ─────────────────────────
                Padding(
                  padding: const EdgeInsets.fromLTRB(18, 18, 18, 12),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.center,
                    children: [
                      // Side icon circle
                      Container(
                        padding: const EdgeInsets.all(10),
                        decoration: BoxDecoration(
                          color: accentColor.withValues(alpha: 0.12),
                          shape: BoxShape.circle,
                        ),
                        child: Icon(
                          isBuy ? Icons.trending_up_rounded : Icons.trending_down_rounded,
                          color: accentColor,
                          size: 18,
                        ),
                      ),
                      const SizedBox(width: 14),

                      // Symbol + tags
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              log['symbol'] ?? 'NIFTY',
                              style: const TextStyle(
                                fontWeight: FontWeight.w900,
                                color: Colors.white,
                                fontSize: 16,
                                letterSpacing: 0.4,
                              ),
                              overflow: TextOverflow.ellipsis,
                            ),
                            const SizedBox(height: 4),
                            Row(
                              children: [
                                _pill(log['signal'] ?? 'SIGNAL', accentColor),
                                const SizedBox(width: 6),
                                if (log['qty'] != null)
                                  _pill('QTY ${log['qty']}', Colors.white38),
                                if (log['instrument_type'] != null) ...[
                                  const SizedBox(width: 6),
                                  _pill(log['instrument_type'].toString(), Colors.purpleAccent),
                                ],
                              ],
                            ),
                          ],
                        ),
                      ),

                      // Right: result badge + PnL
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          if (isClosed) ...[
                            _buildResultBadge(log['result'] ?? 'CLOSED'),
                            const SizedBox(height: 5),
                            Text(
                              '${isProfit ? '+' : ''}₹${pnl.toStringAsFixed(2)}',
                              style: TextStyle(
                                color: isProfit ? Colors.greenAccent : Colors.redAccent,
                                fontSize: 15,
                                fontWeight: FontWeight.w900,
                              ),
                            ),
                          ] else
                            _pill('● OPEN', Colors.cyanAccent),
                        ],
                      ),
                    ],
                  ),
                ),

                // ── Thin divider ─────────────────────────────────────────
                Divider(color: Colors.white.withValues(alpha: 0.05), height: 1),

                // ── Price row: Entry | Exit/SL | TP/Charges ─────────────
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 13),
                  child: Row(
                    children: isClosed
                        ? [
                            Expanded(child: _badge('ENTRY', '₹${log['entry'] ?? '-'}', Colors.cyanAccent)),
                            _vLine(),
                            Expanded(child: _badge('EXIT', '₹${log['exit_price'] ?? '-'}', Colors.orangeAccent)),
                            _vLine(),
                            Expanded(
                              child: _badge(
                                'CHARGES',
                                log['charges'] != null
                                    ? '₹${(log['charges'] as num).toStringAsFixed(2)}'
                                    : '--',
                                Colors.white38,
                              ),
                            ),
                          ]
                        : [
                            Expanded(child: _badge('ENTRY', '₹${log['entry'] ?? '-'}', Colors.cyanAccent)),
                            _vLine(),
                            Expanded(child: _badge('STOP LOSS', '${log['sl'] ?? '-'}', Colors.redAccent)),
                            _vLine(),
                            Expanded(child: _badge('TARGET', '${log['tp'] ?? '-'}', Colors.greenAccent)),
                          ],
                  ),
                ),

                // ── Thin divider ─────────────────────────────────────────
                Divider(color: Colors.white.withValues(alpha: 0.05), height: 1),

                // ── Date/Time row ─────────────────────────────────────────
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
                  child: Row(
                    children: [
                      // Entry date + time
                      Expanded(
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Icon(Icons.login_rounded, color: Colors.white24, size: 13),
                            const SizedBox(width: 6),
                            Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Text(
                                  'ENTRY',
                                  style: TextStyle(color: Colors.white24, fontSize: 8, fontWeight: FontWeight.w900, letterSpacing: 1),
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  _formatDT(log['timestamp']),
                                  style: const TextStyle(color: Colors.white60, fontSize: 10, fontWeight: FontWeight.bold),
                                ),
                              ],
                            ),
                          ],
                        ),
                      ),

                      // Closed date + time (only for closed trades)
                      if (isClosed)
                        Expanded(
                          child: Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Icon(Icons.logout_rounded, color: Colors.white24, size: 13),
                              const SizedBox(width: 6),
                              Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  const Text(
                                    'CLOSED',
                                    style: TextStyle(color: Colors.white24, fontSize: 8, fontWeight: FontWeight.w900, letterSpacing: 1),
                                  ),
                                  const SizedBox(height: 2),
                                  Text(
                                    _formatDT(log['exit_time']),
                                    style: TextStyle(
                                      color: log['result'] == 'TARGET'
                                          ? Colors.greenAccent.withValues(alpha: 0.85)
                                          : log['result'] == 'STOPLOSS'
                                              ? Colors.redAccent.withValues(alpha: 0.85)
                                              : Colors.white60,
                                      fontSize: 10,
                                      fontWeight: FontWeight.bold,
                                    ),
                                  ),
                                ],
                              ),
                            ],
                          ),
                        ),
                    ],
                  ),
                ),

                // ── AI Reason (collapsible if too long) ───────────────────
                if (log['reason'] != null && log['reason'].toString().isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(18, 0, 18, 16),
                    child: Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(11),
                      decoration: BoxDecoration(
                        color: Colors.white.withValues(alpha: 0.025),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Icon(Icons.psychology_outlined, color: Colors.white24, size: 12),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              log['reason'].toString(),
                              style: const TextStyle(
                                color: Colors.white54,
                                fontSize: 10,
                                fontWeight: FontWeight.w500,
                                height: 1.5,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  // ── Helper widgets ────────────────────────────────────────────────────────

  Widget _pill(String text, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(
        text,
        style: TextStyle(color: color, fontSize: 9, fontWeight: FontWeight.w900, letterSpacing: 0.5),
      ),
    );
  }

  Widget _vLine() {
    return Container(
      width: 1,
      height: 28,
      color: Colors.white.withValues(alpha: 0.06),
      margin: const EdgeInsets.symmetric(horizontal: 8),
    );
  }

  Widget _badge(String label, String value, Color color) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: const TextStyle(color: Colors.white24, fontSize: 8, fontWeight: FontWeight.w900, letterSpacing: 0.8)),
        const SizedBox(height: 3),
        Text(value, style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.bold)),
      ],
    );
  }

  Widget _buildResultBadge(String result) {
    final Color c;
    final String label;
    switch (result) {
      case 'TARGET':
        c = Colors.greenAccent; label = '🎯 TARGET'; break;
      case 'STOPLOSS':
        c = Colors.redAccent;   label = '🛡 STOPLOSS'; break;
      case 'SQUARE_OFF':
        c = Colors.orangeAccent; label = '⚡ SQ.OFF'; break;
      default:
        c = Colors.white54;     label = result;
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: c.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: c.withValues(alpha: 0.25)),
      ),
      child: Text(
        label,
        style: TextStyle(color: c, fontSize: 9, fontWeight: FontWeight.w900, letterSpacing: 0.5),
      ),
    );
  }

  Widget _buildMeshBackground() {
    return Stack(
      children: [
        Positioned(top: 100, right: -50,   child: _orb(300, Colors.redAccent.withValues(alpha: 0.05))),
        Positioned(bottom: 200, left: -100, child: _orb(400, Colors.cyanAccent.withValues(alpha: 0.05))),
      ],
    );
  }

  Widget _orb(double size, Color color) => Container(
    width: size, height: size,
    decoration: BoxDecoration(
      shape: BoxShape.circle,
      boxShadow: [BoxShadow(color: color, blurRadius: 100, spreadRadius: 50)],
    ),
  );
}
