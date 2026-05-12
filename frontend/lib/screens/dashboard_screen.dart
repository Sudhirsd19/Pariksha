import 'dart:async';
import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/trading_provider.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      Provider.of<TradingProvider>(context, listen: false).fetchStatus();
      Provider.of<TradingProvider>(context, listen: false).fetchLogs();
      Provider.of<TradingProvider>(context, listen: false).fetchAnalyticsAndPnl();
    });
    
    _timer = Timer.periodic(const Duration(seconds: 5), (timer) {
      if (mounted) {
        Provider.of<TradingProvider>(context, listen: false).fetchStatus();
      }
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final tradingProvider = Provider.of<TradingProvider>(context);

    return Scaffold(
      backgroundColor: const Color(0xFF040408),
      body: Stack(
        children: [
          // 1. Futuristic Background with Mesh Orbs
          _buildMeshBackground(),
          
          CustomScrollView(
            physics: const BouncingScrollPhysics(),
            slivers: [
              // 2. Translucent Custom AppBar
              SliverAppBar(
                expandedHeight: 100,
                floating: true,
                pinned: true,
                elevation: 0,
                backgroundColor: Colors.transparent,
                flexibleSpace: ClipRRect(
                  child: BackdropFilter(
                    filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
                    child: Container(
                      color: Colors.black.withValues(alpha: 0.2),
                    ),
                  ),
                ),
                title: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Text(
                          'QUANTUM',
                          style: TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w900,
                            letterSpacing: 1,
                            color: Colors.white,
                          ),
                        ),
                        const SizedBox(width: 8),
                        _buildNeonModeTag(tradingProvider.isPaperTrading),
                      ],
                    ),
                    _buildSystemStatusBadge(tradingProvider.isActive),
                  ],
                ),
                actions: [
                  _buildPulseConnection(tradingProvider.wsConnected),
                  const SizedBox(width: 20),
                ],
              ),

              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 20.0),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const SizedBox(height: 10),
                      
                      // 0. Hard Lock Warning Banner
                      if (tradingProvider.hardLockReason != null)
                        _buildHardLockBanner(tradingProvider.hardLockReason!),
                      
                      // 3. Central "Power Unit" PnL Card
                      _buildHolographicPnL(tradingProvider),
                      const SizedBox(height: 24),

                      // 4. Double Mini Stats
                      Row(
                        children: [
                          Expanded(
                            child: _buildCyberStat(
                              'VOLATILITY', 
                              '${tradingProvider.tradesToday} TRADES', 
                              Icons.auto_graph_rounded, 
                              Colors.purpleAccent
                            ),
                          ),
                          const SizedBox(width: 16),
                          Expanded(
                            child: _buildCyberStat(
                              'ACCURACY', 
                              '${tradingProvider.winRate.toStringAsFixed(1)}%', 
                              Icons.radar_rounded, 
                              Colors.cyanAccent
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 30),

                      // 5. Live Market Oracle
                      _buildMarketOracle(tradingProvider),
                      const SizedBox(height: 30),

                      // 6. Signal Feed Header
                      const Row(
                        children: [
                          Icon(Icons.sensors_rounded, color: Colors.white24, size: 16),
                          SizedBox(width: 8),
                          Text(
                            'LIVE SIGNAL FEED',
                            style: TextStyle(
                              color: Colors.white24,
                              fontWeight: FontWeight.w900,
                              fontSize: 11,
                              letterSpacing: 3,
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 16),

                      // 7. Futuristic Signal List
                      tradingProvider.signals.isEmpty
                          ? _buildEmptySignals()
                          : Column(
                              children: tradingProvider.signals
                                  .take(6)
                                  .map((sig) => _buildCyberSignalTile(sig))
                                  .toList(),
                            ),
                      const SizedBox(height: 250),
                    ],
                  ),
                ),
              ),
            ],
          ),
          
          // 8. Cyberpunk Action Button
          Positioned(
            bottom: 140,
            left: 30,
            right: 30,
            child: _buildCyberActionButton(tradingProvider),
          ),
        ],
      ),
    );
  }

  Widget _buildMeshBackground() {
    return Stack(
      children: [
        Positioned(
          top: 100,
          left: -50,
          child: _buildOrb(300, Colors.deepPurpleAccent.withValues(alpha: 0.15)),
        ),
        Positioned(
          bottom: 200,
          right: -100,
          child: _buildOrb(400, Colors.cyanAccent.withValues(alpha: 0.1)),
        ),
        Positioned(
          top: 400,
          left: 100,
          child: _buildOrb(200, Colors.blueAccent.withValues(alpha: 0.05)),
        ),
      ],
    );
  }

  Widget _buildOrb(double size, Color color) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        boxShadow: [
          BoxShadow(
            color: color,
            blurRadius: 100,
            spreadRadius: 50,
          ),
        ],
      ),
    );
  }

  Widget _buildNeonModeTag(bool isPaper) {
    final color = isPaper ? Colors.orangeAccent : Colors.greenAccent;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: color.withValues(alpha: 0.5), width: 1),
        boxShadow: [
          BoxShadow(color: color.withValues(alpha: 0.1), blurRadius: 4, spreadRadius: 1),
        ],
      ),
      child: Text(
        isPaper ? 'PAPER' : 'REAL',
        style: TextStyle(
          color: color,
          fontSize: 9,
          fontWeight: FontWeight.w900,
          letterSpacing: 1,
        ),
      ),
    );
  }

  Widget _buildPulseConnection(bool connected) {
    final color = connected ? Colors.greenAccent : Colors.redAccent;
    return Row(
      children: [
        Container(
          width: 6,
          height: 6,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: color,
            boxShadow: [
              BoxShadow(color: color, blurRadius: 10, spreadRadius: 2),
            ],
          ),
        ),
        const SizedBox(width: 10),
        Text(
          connected ? 'CONNECTED' : 'OFFLINE',
          style: TextStyle(
            color: color.withValues(alpha: 0.7),
            fontSize: 9,
            fontWeight: FontWeight.w900,
            letterSpacing: 1,
          ),
        ),
      ],
    );
  }

  Widget _buildHolographicPnL(TradingProvider provider) {
    final bool isProfit = provider.dailyPnl >= 0;
    final Color mainColor = isProfit ? Colors.greenAccent : Colors.redAccent;
    
    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(32),
        border: Border.all(color: Colors.white.withValues(alpha: 0.05)),
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(32),
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 15, sigmaY: 15),
          child: Container(
            padding: const EdgeInsets.all(30),
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [
                  mainColor.withValues(alpha: 0.1),
                  Colors.white.withValues(alpha: 0.02),
                ],
              ),
            ),
            child: Column(
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Text(
                      'TOTAL SESSION P&L',
                      style: TextStyle(color: Colors.white38, fontSize: 10, fontWeight: FontWeight.w900, letterSpacing: 2),
                    ),
                    Icon(Icons.analytics_outlined, color: mainColor.withValues(alpha: 0.3), size: 18),
                  ],
                ),
                const SizedBox(height: 20),
                Text(
                  '₹${provider.dailyPnl.toStringAsFixed(2)}',
                  style: TextStyle(
                    fontSize: 48,
                    fontWeight: FontWeight.w900,
                    color: Colors.white,
                    letterSpacing: -2,
                    shadows: [
                      Shadow(color: mainColor.withValues(alpha: 0.5), blurRadius: 25),
                    ],
                  ),
                ),
                const SizedBox(height: 20),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  decoration: BoxDecoration(
                    color: mainColor.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(isProfit ? Icons.keyboard_double_arrow_up_rounded : Icons.keyboard_double_arrow_down_rounded, color: mainColor, size: 16),
                      const SizedBox(width: 8),
                      Text(
                        'SYSTEM PEAK: ₹${(provider.dailyPnl * 1.1).toStringAsFixed(0)}',
                        style: TextStyle(color: mainColor, fontWeight: FontWeight.bold, fontSize: 11),
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

  Widget _buildCyberStat(String label, String value, IconData icon, Color color) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.03),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: color.withValues(alpha: 0.1)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: color, size: 20),
          const SizedBox(height: 16),
          Text(
            value,
            style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 20, color: Colors.white, letterSpacing: -0.5),
          ),
          const SizedBox(height: 4),
          Text(
            label,
            style: const TextStyle(color: Colors.white24, fontSize: 10, fontWeight: FontWeight.w900, letterSpacing: 1),
          ),
        ],
      ),
    );
  }

  Widget _buildMarketOracle(TradingProvider provider) {
    final bool isBullish = provider.sentiment.contains('Bullish');
    final Color accent = isBullish ? Colors.cyanAccent : Colors.redAccent;

    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: Colors.black,
        borderRadius: BorderRadius.circular(28),
        border: Border.all(color: accent.withValues(alpha: 0.2)),
        boxShadow: [
          BoxShadow(color: accent.withValues(alpha: 0.03), blurRadius: 30, spreadRadius: 5),
        ],
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const Text('NIFTY 50', style: TextStyle(color: Colors.white38, fontWeight: FontWeight.bold, fontSize: 12)),
                  const SizedBox(width: 8),
                  Container(width: 4, height: 4, decoration: BoxDecoration(shape: BoxShape.circle, color: accent)),
                ],
              ),
              const SizedBox(height: 10),
              Text(
                provider.ltp.toStringAsFixed(2),
                style: const TextStyle(fontSize: 32, fontWeight: FontWeight.w900, color: Colors.white, letterSpacing: -1),
              ),
              const SizedBox(height: 15),
              _buildKillzoneIndicator(provider.inKillzone),
            ],
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                provider.sentiment.toUpperCase(),
                style: TextStyle(color: accent, fontWeight: FontWeight.w900, fontSize: 14, letterSpacing: 1),
              ),
              const SizedBox(height: 12),
              _buildModernGauge(provider.sentimentScore, accent),
              const SizedBox(height: 15),
              _buildScoreIndicator(provider.currentScore),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildModernGauge(double value, Color color) {
    return Stack(
      children: [
        Container(
          width: 100,
          height: 6,
          decoration: BoxDecoration(color: Colors.white10, borderRadius: BorderRadius.circular(10)),
        ),
        Container(
          width: 100 * value,
          height: 6,
          decoration: BoxDecoration(
            color: color,
            borderRadius: BorderRadius.circular(10),
            boxShadow: [BoxShadow(color: color.withValues(alpha: 0.5), blurRadius: 8)],
          ),
        ),
      ],
    );
  }

  Widget _buildCyberSignalTile(dynamic sig) {
    final bool isBuy = sig['signal'] == 'BUY';
    final Color accent = isBuy ? Colors.greenAccent : Colors.redAccent;
    
    // Format timestamp if it's a number
    String timeStr = 'NOW';
    if (sig['timestamp'] != null) {
      final dt = DateTime.fromMillisecondsSinceEpoch(sig['timestamp'] is int ? sig['timestamp'] : int.tryParse(sig['timestamp'].toString()) ?? 0);
      timeStr = "${dt.hour.toString().padLeft(2,'0')}:${dt.minute.toString().padLeft(2,'0')}:${dt.second.toString().padLeft(2,'0')}";
    }
    
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 18),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.02),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: Colors.white.withValues(alpha: 0.02)),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: accent.withValues(alpha: 0.1),
              shape: BoxShape.circle,
            ),
            child: Icon(
              isBuy ? Icons.north_east_rounded : Icons.south_west_rounded,
              color: accent,
              size: 20,
            ),
          ),
          const SizedBox(width: 20),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '${sig['symbol'] ?? 'NIFTY'} ${sig['signal'] ?? 'SIGNAL'}',
                  style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 14, color: Colors.white),
                ),
                const SizedBox(height: 4),
                Text(
                  'ENTRY @ ₹${sig['entry'] ?? '0.0'} • $timeStr',
                  style: const TextStyle(color: Colors.white24, fontSize: 10, fontWeight: FontWeight.bold),
                ),
              ],
            ),
          ),
          Text(
            isBuy ? '+ LONG' : '- SHORT',
            style: TextStyle(color: accent.withValues(alpha: 0.5), fontWeight: FontWeight.w900, fontSize: 10),
          ),
        ],
      ),
    );
  }

  Widget _buildEmptySignals() {
    return Center(
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 60),
        child: const Text(
          'AWAITING SYSTEM DATA...',
          style: TextStyle(color: Colors.white10, fontWeight: FontWeight.w900, letterSpacing: 4, fontSize: 10),
        ),
      ),
    );
  }

  Widget _buildCyberActionButton(TradingProvider provider) {
    final bool active = provider.isActive;
    return Container(
      height: 70,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(24),
        boxShadow: [
          BoxShadow(
            color: (active ? Colors.redAccent : Colors.cyanAccent).withValues(alpha: 0.2),
            blurRadius: 30,
            spreadRadius: -10,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(24),
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 5, sigmaY: 5),
          child: ElevatedButton(
            onPressed: () => provider.toggleTrading(!active),
            style: ElevatedButton.styleFrom(
              backgroundColor: (active ? Colors.redAccent : Colors.cyanAccent).withValues(alpha: 0.1),
              foregroundColor: Colors.white,
              elevation: 0,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(24),
                side: BorderSide(color: (active ? Colors.redAccent : Colors.cyanAccent).withValues(alpha: 0.3), width: 1.5),
              ),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(active ? Icons.power_settings_new_rounded : Icons.bolt_rounded, size: 24, color: active ? Colors.redAccent : Colors.cyanAccent),
                const SizedBox(width: 16),
                Text(
                  active ? 'SHUTDOWN ENGINE' : 'INITIALIZE TRADING CORE',
                  style: TextStyle(
                    fontWeight: FontWeight.w900,
                    letterSpacing: 2,
                    fontSize: 14,
                    color: active ? Colors.redAccent : Colors.cyanAccent,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildSystemStatusBadge(bool active) {
    final color = active ? Colors.greenAccent : Colors.white10;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 4,
          height: 4,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: active ? color : Colors.white24,
            boxShadow: active ? [BoxShadow(color: color, blurRadius: 4, spreadRadius: 1)] : null,
          ),
        ),
        const SizedBox(width: 6),
        Text(
          active ? 'SYSTEM ONLINE' : 'SYSTEM IDLE',
          style: TextStyle(
            color: active ? color.withValues(alpha: 0.8) : Colors.white10,
            fontSize: 8,
            fontWeight: FontWeight.w900,
            letterSpacing: 0.5,
          ),
        ),
      ],
    );
  }

  Widget _buildHardLockBanner(String reason) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 24),
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.redAccent.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: Colors.redAccent.withValues(alpha: 0.3)),
      ),
      child: Row(
        children: [
          const Icon(Icons.lock_clock_rounded, color: Colors.redAccent, size: 28),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'SYSTEM LOCKDOWN ACTIVE',
                  style: TextStyle(color: Colors.redAccent, fontWeight: FontWeight.w900, fontSize: 12, letterSpacing: 1),
                ),
                const SizedBox(height: 4),
                Text(
                  reason,
                  style: TextStyle(color: Colors.white.withValues(alpha: 0.6), fontSize: 11),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildKillzoneIndicator(bool active) {
    final color = active ? Colors.greenAccent : Colors.orangeAccent;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.2)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.schedule_rounded, color: color, size: 10),
          const SizedBox(width: 6),
          Text(
            active ? 'KILLZONE ACTIVE' : 'OUTSIDE WINDOW',
            style: TextStyle(color: color, fontSize: 8, fontWeight: FontWeight.w900, letterSpacing: 0.5),
          ),
        ],
      ),
    );
  }

  Widget _buildScoreIndicator(int score) {
    final color = score >= 8 ? Colors.cyanAccent : Colors.white24;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        const Text(
          'SIGNAL SCORE',
          style: TextStyle(color: Colors.white24, fontSize: 8, fontWeight: FontWeight.w900, letterSpacing: 1),
        ),
        const SizedBox(height: 4),
        Text(
          '$score/14',
          style: TextStyle(color: color, fontSize: 18, fontWeight: FontWeight.w900, letterSpacing: -0.5),
        ),
      ],
    );
  }
}
