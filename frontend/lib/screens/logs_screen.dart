import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/trading_provider.dart';

class LogsScreen extends StatelessWidget {
  const LogsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final provider = Provider.of<TradingProvider>(context);

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
                    icon: const Icon(Icons.sync_rounded, color: Colors.cyanAccent),
                    onPressed: () => provider.fetchLogs(),
                  ),
                ],
              ),

              SliverPadding(
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 20),
                sliver: provider.signals.isEmpty
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
                            final log = provider.signals[index];
                            return _buildCyberLogTile(log);
                          },
                          childCount: provider.signals.length,
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
                          Text(
                            '${log['signal'] ?? 'SIGNAL'} - ${log['symbol'] ?? 'NIFTY'}',
                            style: const TextStyle(fontWeight: FontWeight.w900, color: Colors.white, fontSize: 16, letterSpacing: 0.5),
                          ),
                          Text(
                            log['timestamp'] != null 
                              ? "${DateTime.fromMillisecondsSinceEpoch(log['timestamp'] is int ? log['timestamp'] : int.tryParse(log['timestamp'].toString()) ?? 0).hour.toString().padLeft(2,'0')}:${DateTime.fromMillisecondsSinceEpoch(log['timestamp'] is int ? log['timestamp'] : int.tryParse(log['timestamp'].toString()) ?? 0).minute.toString().padLeft(2,'0')}"
                              : 'NOW',
                            style: const TextStyle(color: Colors.white12, fontSize: 9, fontWeight: FontWeight.bold),
                          ),
                        ],
                      ),
                      const SizedBox(height: 16),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          _buildMiniBadge('PRICE', '₹${log['entry'] ?? '0.0'}', Colors.cyanAccent),
                          _buildMiniBadge('SL', '${log['sl'] ?? '0.0'}', Colors.redAccent),
                          _buildMiniBadge('TP', '${log['tp'] ?? '0.0'}', Colors.greenAccent),
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
                                style: const TextStyle(color: Colors.white38, fontSize: 10, fontWeight: FontWeight.w500, height: 1.4),
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
}
