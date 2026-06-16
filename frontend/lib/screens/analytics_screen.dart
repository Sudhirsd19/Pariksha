import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:fl_chart/fl_chart.dart';
import '../providers/trading_provider.dart';
import 'stock_scanner_screen.dart';

class AnalyticsScreen extends StatelessWidget {
  const AnalyticsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final provider = Provider.of<TradingProvider>(context);
    final analytics = provider.analyticsData ?? {};
    
    final winRate = analytics['win_rate']?.toDouble() ?? 0.0;
    final profitFactor = analytics['profit_factor']?.toDouble() ?? 0.0;
    final avgWinner = analytics['avg_winner']?.toDouble() ?? 0.0;
    final avgLoser = analytics['avg_loser']?.toDouble() ?? 0.0;
    final maxDrawdown = analytics['max_drawdown']?.toDouble() ?? 0.0;
    final totalTrades = analytics['total_trades']?.toInt() ?? 0;
    final pnlHistoryList = analytics['pnl_history'] as List<dynamic>? ?? [];
    final pnlHistory = pnlHistoryList.map((e) => (e as num).toDouble()).toList();

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
                actions: [
                  IconButton(
                    icon: const Icon(Icons.radar_rounded, color: Colors.cyanAccent),
                    tooltip: "Stock Radar",
                    onPressed: () {
                      Navigator.push(
                        context,
                        MaterialPageRoute(builder: (context) => const StockScannerScreen()),
                      );
                    },
                  ),
                  const SizedBox(width: 8),
                ],
                flexibleSpace: ClipRRect(
                  child: BackdropFilter(
                    filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
                    child: FlexibleSpaceBar(
                      title: const Text('INTELLIGENCE HUB', style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: 4, fontSize: 14)),
                      background: Container(color: Colors.black.withValues(alpha: 0.3)),
                    ),
                  ),
                ),
              ),

              SliverPadding(
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 20),
                sliver: SliverList(
                  delegate: SliverChildListDelegate([
                    _buildPerformanceGauge(winRate, totalTrades),
                    const SizedBox(height: 30),
                    
                    const Text('GROWTH TRAJECTORY', style: TextStyle(color: Colors.white24, fontWeight: FontWeight.w900, letterSpacing: 2, fontSize: 10)),
                    const SizedBox(height: 16),
                    _buildGrowthChart(pnlHistory),
                    
                    const SizedBox(height: 30),
                    const Text('CORE ANALYTICS', style: TextStyle(color: Colors.white24, fontWeight: FontWeight.w900, letterSpacing: 2, fontSize: 10)),
                    const SizedBox(height: 16),
                    
                    GridView.count(
                      crossAxisCount: 2,
                      shrinkWrap: true,
                      physics: const NeverScrollableScrollPhysics(),
                      crossAxisSpacing: 16,
                      mainAxisSpacing: 16,
                      childAspectRatio: 1.4,
                      children: [
                        _buildStatCard("PROFIT FACTOR", "$profitFactor", Icons.auto_graph_rounded, Colors.purpleAccent),
                        _buildStatCard("MAX DRAWDOWN", "${maxDrawdown.toStringAsFixed(2)}%", Icons.waterfall_chart_rounded, Colors.redAccent),
                        _buildStatCard("AVG WINNER", "₹${avgWinner.toStringAsFixed(0)}", Icons.north_east_rounded, Colors.greenAccent),
                        _buildStatCard("AVG LOSER", "₹${avgLoser.toStringAsFixed(0)}", Icons.south_west_rounded, Colors.deepOrangeAccent),
                      ],
                    ),
                    const SizedBox(height: 30),
                    const Text('CONDITION WIN-RATES', style: TextStyle(color: Colors.white24, fontWeight: FontWeight.w900, letterSpacing: 2, fontSize: 10)),
                    const SizedBox(height: 16),
                    _buildConditionWinRates(provider),
                    const SizedBox(height: 100),
                  ]),
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
        Positioned(top: 400, right: -50, child: _buildOrb(300, Colors.cyanAccent.withValues(alpha: 0.05))),
        Positioned(top: 100, left: -100, child: _buildOrb(400, Colors.deepPurpleAccent.withValues(alpha: 0.05))),
      ],
    );
  }

  Widget _buildOrb(double size, Color color) {
    return Container(
      width: size, height: size,
      decoration: BoxDecoration(shape: BoxShape.circle, boxShadow: [BoxShadow(color: color, blurRadius: 100, spreadRadius: 50)]),
    );
  }

  Widget _buildPerformanceGauge(double winRate, int totalTrades) {
    final Color color = winRate >= 50 ? Colors.greenAccent : Colors.redAccent;
    
    return Container(
      padding: const EdgeInsets.all(30),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.02),
        borderRadius: BorderRadius.circular(32),
        border: Border.all(color: color.withValues(alpha: 0.1)),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('CORE ACCURACY', style: TextStyle(color: Colors.white24, fontSize: 10, fontWeight: FontWeight.w900, letterSpacing: 2)),
              const SizedBox(height: 16),
              Text(
                '${winRate.toStringAsFixed(1)}%',
                style: TextStyle(fontSize: 48, fontWeight: FontWeight.w900, color: Colors.white, letterSpacing: -2, shadows: [Shadow(color: color.withValues(alpha: 0.5), blurRadius: 20)]),
              ),
              const SizedBox(height: 6),
              Text('OVER $totalTrades MISSIONS', style: const TextStyle(color: Colors.white10, fontSize: 10, fontWeight: FontWeight.bold)),
            ],
          ),
          SizedBox(
            width: 90, height: 90,
            child: Stack(
              fit: StackFit.expand,
              children: [
                CircularProgressIndicator(
                  value: winRate / 100,
                  strokeWidth: 8,
                  backgroundColor: Colors.white.withValues(alpha: 0.05),
                  color: color,
                  strokeCap: StrokeCap.round,
                ),
                Center(child: Icon(winRate >= 50 ? Icons.bolt_rounded : Icons.warning_rounded, color: color, size: 32)),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildGrowthChart(List<double> pnlHistory) {
    if (pnlHistory.length < 2) {
      return Container(
        height: 180,
        alignment: Alignment.center,
        decoration: BoxDecoration(color: Colors.white.withValues(alpha: 0.02), borderRadius: BorderRadius.circular(32)),
        child: const Text('AWAITING DATA PACKETS...', style: TextStyle(color: Colors.white10, fontWeight: FontWeight.w900, letterSpacing: 2, fontSize: 10)),
      );
    }

    final spots = pnlHistory.asMap().entries.map((e) => FlSpot(e.key.toDouble(), e.value)).toList();
    final isProfit = pnlHistory.last >= 0;
    final color = isProfit ? Colors.cyanAccent : Colors.redAccent;
    final minY = pnlHistory.reduce((a, b) => a < b ? a : b);
    final maxY = pnlHistory.reduce((a, b) => a > b ? a : b);

    return Container(
      height: 220,
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.02),
        borderRadius: BorderRadius.circular(32),
        border: Border.all(color: Colors.white.withValues(alpha: 0.03)),
      ),
      child: LineChart(
        LineChartData(
          minY: minY - (maxY - minY).abs() * 0.1,
          maxY: maxY + (maxY - minY).abs() * 0.1,
          gridData: const FlGridData(show: false),
          titlesData: const FlTitlesData(show: false),
          borderData: FlBorderData(show: false),
          lineBarsData: [
            LineChartBarData(
              spots: spots,
              isCurved: true,
              color: color,
              barWidth: 3,
              dotData: const FlDotData(show: false),
              belowBarData: BarAreaData(
                show: true,
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [color.withValues(alpha: 0.2), color.withValues(alpha: 0)],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildStatCard(String title, String value, IconData icon, Color color) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.02),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: color.withValues(alpha: 0.1)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(icon, size: 18, color: color),
          const SizedBox(height: 12),
          Text(title, style: const TextStyle(color: Colors.white24, fontSize: 9, fontWeight: FontWeight.w900, letterSpacing: 1)),
          const SizedBox(height: 4),
          Text(value, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w900, color: Colors.white, letterSpacing: -0.5)),
        ],
      ),
    );
  }

  Widget _buildConditionWinRates(TradingProvider provider) {
    final conditions = provider.conditionWinRates;
    if (conditions == null || conditions.isEmpty) {
      return Container(
        padding: const EdgeInsets.all(24),
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.02),
          borderRadius: BorderRadius.circular(24),
        ),
        child: const Center(
          child: Text(
            "Insufficient trade data to calculate condition win rates.",
            style: TextStyle(color: Colors.white30, fontSize: 12),
          ),
        ),
      );
    }

    // Sort by win rate descending
    final entries = conditions.entries.toList()
      ..sort((a, b) {
        final aWr = (a.value['win_rate'] as num).toDouble();
        final bWr = (b.value['win_rate'] as num).toDouble();
        return bWr.compareTo(aWr);
      });

    return ListView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      itemCount: entries.length,
      itemBuilder: (context, index) {
        final key = entries[index].key;
        final data = entries[index].value;
        final winRate = (data['win_rate'] as num).toDouble();
        final trades = data['trades'] as int;

        Color color;
        if (winRate >= 60) {
          color = Colors.greenAccent;
        } else if (winRate >= 40) {
          color = Colors.amberAccent;
        } else {
          color = Colors.redAccent;
        }

        return Container(
          margin: const EdgeInsets.only(bottom: 12),
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: 0.02),
            borderRadius: BorderRadius.circular(24),
            border: Border.all(color: color.withValues(alpha: 0.1)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Expanded(
                    child: Text(
                      key,
                      style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 13),
                    ),
                  ),
                  Text(
                    '${winRate.toStringAsFixed(1)}%',
                    style: TextStyle(color: color, fontWeight: FontWeight.w900, fontSize: 16),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              ClipRRect(
                borderRadius: BorderRadius.circular(4),
                child: LinearProgressIndicator(
                  value: winRate / 100,
                  backgroundColor: Colors.white.withValues(alpha: 0.05),
                  color: color,
                  minHeight: 6,
                ),
              ),
              const SizedBox(height: 12),
              Text(
                '$trades Trades Total',
                style: const TextStyle(color: Colors.white30, fontSize: 10, fontWeight: FontWeight.bold, letterSpacing: 1),
              ),
            ],
          ),
        );
      },
    );
  }
}
