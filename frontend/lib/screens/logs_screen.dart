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
            dialogTheme: const DialogThemeData(
              backgroundColor: Color(0xFF0F0F1A),
            ),
          ),
          child: child!,
        );
      },
    );
    if (picked != null && picked != _selectedDate) {
      setState(() {
        _selectedDate = picked;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final provider = Provider.of<TradingProvider>(context);

    // Filter logs by selected date if set
    final filteredLogs = provider.signals.where((log) {
      if (_selectedDate == null) return true;
      final timestamp = log['timestamp'];
      if (timestamp == null) return false;
      final dt = DateTime.fromMillisecondsSinceEpoch(_parseTimestamp(timestamp));
      return dt.year == _selectedDate!.year &&
             dt.month == _selectedDate!.month &&
             dt.day == _selectedDate!.day;
    }).toList();

    // Sort: Latest closed or open trades at the top (using exit_time or entry timestamp)
    filteredLogs.sort((a, b) {
      final aTime = a['exit_time'] ?? a['timestamp'] ?? 0;
      final bTime = b['exit_time'] ?? b['timestamp'] ?? 0;
      return _parseTimestamp(bTime).compareTo(_parseTimestamp(aTime));
    });

    return Scaffold(
      backgroundColor: const Color(0xFF040408),
      body: Stack(
        children: [
          _buildMeshBackground(),
          
          CustomScrollView(
            physics: const BouncingScrollPhysics(),
            slivers: [
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
                      title: const Text('MISSION LOGS', style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: 4, fontSize: 14)),
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
                    onPressed: () => _selectDate(context),
                  ),
                  if (_selectedDate != null)
                    IconButton(
                      icon: const Icon(Icons.clear_rounded, color: Colors.redAccent),
                      tooltip: "Clear Filter",
                      onPressed: () {
                        setState(() {
                          _selectedDate = null;
                        });
                      },
                    ),
                  IconButton(
                    icon: const Icon(Icons.sync_rounded, color: Colors.cyanAccent),
                    onPressed: () => provider.fetchLogs(),
                  ),
                ],
              ),

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
                              const Icon(Icons.date_range_rounded, color: Colors.cyanAccent, size: 14),
                              const SizedBox(width: 8),
                              Text(
                                "Date: ${_selectedDate!.day.toString().padLeft(2, '0')}/${_selectedDate!.month.toString().padLeft(2, '0')}/${_selectedDate!.year}",
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

              SliverPadding(
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 20),
                sliver: filteredLogs.isEmpty
                    ? const SliverFillRemaining(
                        child: Center(
                          child: Text(
                            'NO MISSION DATA DETECTED',
                            style: TextStyle(color: Colors.white10, fontWeight: FontWeight.w900, letterSpacing: 4, fontSize: 10),
                          ),
                        ),
                      )
                    : SliverList(
                        delegate: SliverChildBuilderDelegate(
                          (context, index) {
                            final log = filteredLogs[index];
                            return _buildCyberLogTile(log);
                          },
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


  Widget _buildMeshBackground() {
    return Stack(
      children: [
        Positioned(top: 100, right: -50, child: _buildOrb(300, Colors.redAccent.withValues(alpha: 0.05))),
        Positioned(bottom: 200, left: -100, child: _buildOrb(400, Colors.cyanAccent.withValues(alpha: 0.05))),
      ],
    );
  }

  Widget _buildOrb(double size, Color color) {
    return Container(
      width: size, height: size,
      decoration: BoxDecoration(shape: BoxShape.circle, boxShadow: [BoxShadow(color: color, blurRadius: 100, spreadRadius: 50)]),
    );
  }

  Widget _buildCyberLogTile(dynamic log) {
    final isBuy = log['signal'] == 'BUY';
    final Color color = isBuy ? Colors.greenAccent : Colors.redAccent;
    final bool isClosed = log['status'] == 'CLOSED';
    
    return Container(
      margin: const EdgeInsets.only(bottom: 20),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: color.withValues(alpha: 0.1)),
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(24),
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
          child: Container(
            padding: const EdgeInsets.all(24),
            color: color.withValues(alpha: 0.02),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: color.withValues(alpha: 0.1),
                    shape: BoxShape.circle,
                  ),
                  child: Icon(
                    isBuy ? Icons.bolt_rounded : Icons.shield_rounded,
                    color: color,
                    size: 20,
                  ),
                ),
                const SizedBox(width: 20),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Expanded(
                            child: Text(
                              '${log['signal'] ?? 'SIGNAL'} - ${log['symbol'] ?? 'NIFTY'}',
                              style: const TextStyle(fontWeight: FontWeight.w900, color: Colors.white, fontSize: 16, letterSpacing: 0.5),
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                          const SizedBox(width: 8),
                          if (isClosed) ...[
                            _buildResultBadge(log['result'] ?? 'CLOSED'),
                            const SizedBox(width: 8),
                          ],
                          Text(
                            log['timestamp'] != null 
                              ? "${DateTime.fromMillisecondsSinceEpoch(_parseTimestamp(log['timestamp'])).hour.toString().padLeft(2,'0')}:${DateTime.fromMillisecondsSinceEpoch(_parseTimestamp(log['timestamp'])).minute.toString().padLeft(2,'0')}"
                              : 'NOW',
                            style: const TextStyle(color: Colors.white60, fontSize: 9, fontWeight: FontWeight.bold),
                          ),
                        ],
                      ),
                      const SizedBox(height: 16),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: isClosed
                            ? [
                                Expanded(child: _buildMiniBadge('ENTRY', '₹${log['entry'] ?? '0.0'}', Colors.cyanAccent)),
                                const SizedBox(width: 8),
                                Expanded(child: _buildMiniBadge('EXIT', '₹${log['exit_price'] ?? '0.0'}', Colors.orangeAccent)),
                                const SizedBox(width: 8),
                                Expanded(
                                  child: _buildMiniBadge(
                                    'PNL', 
                                    '${((log['pnl'] ?? 0.0) as num) >= 0 ? '+' : ''}₹${((log['pnl'] ?? 0.0) as num).toStringAsFixed(2)}', 
                                    ((log['pnl'] ?? 0.0) as num) >= 0 ? Colors.greenAccent : Colors.redAccent
                                  ),
                                ),
                              ]
                            : [
                                Expanded(child: _buildMiniBadge('PRICE', '₹${log['entry'] ?? '0.0'}', Colors.cyanAccent)),
                                const SizedBox(width: 8),
                                Expanded(child: _buildMiniBadge('SL', '${log['sl'] ?? '0.0'}', Colors.redAccent)),
                                const SizedBox(width: 8),
                                Expanded(child: _buildMiniBadge('TP', '${log['tp'] ?? '0.0'}', Colors.greenAccent)),
                              ],
                      ),
                      const SizedBox(height: 16),
                      Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: Colors.white.withValues(alpha: 0.02),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Row(
                          children: [
                            const Icon(Icons.psychology_outlined, color: Colors.white24, size: 14),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                (log['reason'] ?? 'AI PROTOCOL EXECUTION').toString(),
                                style: const TextStyle(color: Colors.white60, fontSize: 10, fontWeight: FontWeight.w500, height: 1.4),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildResultBadge(String result) {
    Color badgeColor;
    if (result == 'TARGET') {
      badgeColor = Colors.greenAccent;
    } else if (result == 'STOPLOSS') {
      badgeColor = Colors.redAccent;
    } else {
      badgeColor = Colors.white54;
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: badgeColor.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: badgeColor.withValues(alpha: 0.2)),
      ),
      child: Text(
        result,
        style: TextStyle(
          color: badgeColor,
          fontSize: 8,
          fontWeight: FontWeight.w900,
          letterSpacing: 0.5,
        ),
      ),
    );
  }

  Widget _buildMiniBadge(String label, String value, Color color) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: const TextStyle(color: Colors.white10, fontSize: 8, fontWeight: FontWeight.w900, letterSpacing: 1)),
        const SizedBox(height: 2),
        Text(value, style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.bold)),
      ],
    );
  }

  int _parseTimestamp(dynamic ts) {
    if (ts == null) return 0;
    if (ts is num) return ts.toInt();
    return double.tryParse(ts.toString())?.toInt() ?? 0;
  }
}
