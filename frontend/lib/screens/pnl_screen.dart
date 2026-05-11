import 'dart:ui';
import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/trading_provider.dart';

class PnLScreen extends StatefulWidget {
  const PnLScreen({super.key});

  @override
  State<PnLScreen> createState() => _PnLScreenState();
}

class _PnLScreenState extends State<PnLScreen> with SingleTickerProviderStateMixin {
  late TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 3, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF040408),
      body: Stack(
        children: [
          _buildMeshBackground(),
          
          NestedScrollView(
            headerSliverBuilder: (context, innerBoxIsScrolled) => [
              SliverAppBar(
                expandedHeight: 180,
                floating: true,
                pinned: true,
                elevation: 0,
                backgroundColor: Colors.transparent,
                flexibleSpace: ClipRRect(
                  child: BackdropFilter(
                    filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
                    child: FlexibleSpaceBar(
                      centerTitle: true,
                      titlePadding: const EdgeInsets.only(bottom: 60),
                      title: const Text('PERFORMANCE HUB', style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: 4, fontSize: 14)),
                      background: Container(color: Colors.black.withValues(alpha: 0.3)),
                    ),
                  ),
                ),
                bottom: PreferredSize(
                  preferredSize: const Size.fromHeight(50),
                  child: Container(
                    margin: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
                    decoration: BoxDecoration(
                      color: Colors.white.withValues(alpha: 0.05),
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: TabBar(
                      controller: _tabController,
                      indicator: BoxDecoration(
                        borderRadius: BorderRadius.circular(12),
                        color: Colors.cyanAccent.withValues(alpha: 0.1),
                        border: Border.all(color: Colors.cyanAccent.withValues(alpha: 0.5)),
                      ),
                      labelColor: Colors.cyanAccent,
                      unselectedLabelColor: Colors.white24,
                      indicatorSize: TabBarIndicatorSize.tab,
                      dividerColor: Colors.transparent,
                      tabs: const [
                        Tab(text: 'DAILY'),
                        Tab(text: 'WEEKLY'),
                        Tab(text: 'MONTHLY'),
                      ],
                    ),
                  ),
                ),
              ),
            ],
            body: Consumer<TradingProvider>(
              builder: (context, provider, _) {
                return TabBarView(
                  controller: _tabController,
                  children: [
                    _buildPnLView(context, provider, 'daily'),
                    _buildPnLView(context, provider, 'weekly'),
                    _buildPnLView(context, provider, 'monthly'),
                  ],
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildMeshBackground() {
    return Stack(
      children: [
        Positioned(top: 200, left: -50, child: _buildOrb(300, Colors.blueAccent.withValues(alpha: 0.1))),
        Positioned(bottom: 100, right: -100, child: _buildOrb(400, Colors.purpleAccent.withValues(alpha: 0.05))),
      ],
    );
  }

  Widget _buildOrb(double size, Color color) {
    return Container(
      width: size, height: size,
      decoration: BoxDecoration(shape: BoxShape.circle, boxShadow: [BoxShadow(color: color, blurRadius: 100, spreadRadius: 50)]),
    );
  }

  Widget _buildPnLView(BuildContext context, TradingProvider provider, String period) {
    final records = provider.dailyPnlRecords;
    List<Map<String, dynamic>> filtered;
    String title;
    double totalPnl;

    if (period == 'daily') {
      final today = DateTime.now().toUtc().toIso8601String().substring(0, 10);
      filtered = records.where((r) => r['date'] == today).toList();
      title = 'TODAY\'S REVENUE';
      totalPnl = provider.todayPnl;
    } else if (period == 'weekly') {
      filtered = _getThisWeekRecords(records);
      title = 'WEEKLY REVENUE';
      totalPnl = provider.weeklyPnl;
    } else {
      filtered = _getThisMonthRecords(records);
      title = 'MONTHLY REVENUE';
      totalPnl = provider.monthlyPnl;
    }

    final isProfit = totalPnl >= 0;
    final color = isProfit ? Colors.greenAccent : Colors.redAccent;
    final chartSpots = _buildChartSpots(filtered, period);

    return SingleChildScrollView(
      physics: const BouncingScrollPhysics(),
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _buildHeroPnLCard(title, totalPnl, isProfit, color, filtered),
          const SizedBox(height: 24),
          
          const Text('GROWTH ANALYTICS', style: TextStyle(color: Colors.white24, fontWeight: FontWeight.w900, letterSpacing: 2, fontSize: 10)),
          const SizedBox(height: 16),
          _buildChartContainer(chartSpots, isProfit, color),
          
          const SizedBox(height: 30),
          const Text('SYSTEM METRICS', style: TextStyle(color: Colors.white24, fontWeight: FontWeight.w900, letterSpacing: 2, fontSize: 10)),
          const SizedBox(height: 16),
          _buildStatsGrid(filtered),

          if (period != 'daily' && filtered.isNotEmpty) ...[
            const SizedBox(height: 30),
            const Text('DAILY BREAKDOWN', style: TextStyle(color: Colors.white24, fontWeight: FontWeight.w900, letterSpacing: 2, fontSize: 10)),
            const SizedBox(height: 16),
            ...filtered.map((r) => _buildDayTile(r)),
          ],
          const SizedBox(height: 40),
        ],
      ),
    );
  }

  Widget _buildHeroPnLCard(String title, double pnl, bool isProfit, Color color, List<Map<String, dynamic>> records) {
    int totalTrades = records.fold(0, (s, r) => s + ((r['total_trades'] as num?)?.toInt() ?? 0));
    int wins = records.fold(0, (s, r) => s + ((r['wins'] as num?)?.toInt() ?? 0));
    double winRate = totalTrades > 0 ? (wins / totalTrades * 100) : 0.0;

    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(32),
        border: Border.all(color: color.withValues(alpha: 0.1)),
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
                colors: [color.withValues(alpha: 0.15), Colors.white.withValues(alpha: 0.02)],
              ),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: const TextStyle(color: Colors.white38, fontSize: 10, fontWeight: FontWeight.w900, letterSpacing: 2)),
                const SizedBox(height: 16),
                Text(
                  '${isProfit ? '+' : ''}₹${pnl.toStringAsFixed(2)}',
                  style: TextStyle(
                    fontSize: 42,
                    fontWeight: FontWeight.w900,
                    color: Colors.white,
                    letterSpacing: -1,
                    shadows: [Shadow(color: color.withValues(alpha: 0.5), blurRadius: 20)],
                  ),
                ),
                const SizedBox(height: 24),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    _miniStat('SESSIONS', '$totalTrades', Colors.white70),
                    _miniStat('ACCURACY', '${winRate.toStringAsFixed(1)}%', Colors.cyanAccent),
                    _miniStat('STATUS', isProfit ? 'SURGE' : 'DIP', color),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _miniStat(String label, String value, Color color) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: const TextStyle(color: Colors.white24, fontSize: 9, fontWeight: FontWeight.w900, letterSpacing: 1)),
        const SizedBox(height: 4),
        Text(value, style: TextStyle(color: color, fontWeight: FontWeight.w900, fontSize: 14)),
      ],
    );
  }

  Widget _buildChartContainer(List<FlSpot> spots, bool isProfit, Color color) {
    if (spots.length < 2) return _buildNoDataChart();
    
    final minY = spots.map((s) => s.y).reduce((a, b) => a < b ? a : b) - 200;
    final maxY = spots.map((s) => s.y).reduce((a, b) => a > b ? a : b) + 200;

    return Container(
      height: 240,
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.02),
        borderRadius: BorderRadius.circular(32),
        border: Border.all(color: Colors.white.withValues(alpha: 0.03)),
      ),
      child: LineChart(
        LineChartData(
          minY: minY, maxY: maxY,
          gridData: const FlGridData(show: false),
          borderData: FlBorderData(show: false),
          titlesData: const FlTitlesData(show: false),
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

  Widget _buildNoDataChart() {
    return Container(
      height: 120,
      alignment: Alignment.center,
      decoration: BoxDecoration(color: Colors.white.withValues(alpha: 0.02), borderRadius: BorderRadius.circular(32)),
      child: const Text('AWAITING DATA PACKETS...', style: TextStyle(color: Colors.white10, fontWeight: FontWeight.w900, letterSpacing: 2, fontSize: 10)),
    );
  }

  Widget _buildStatsGrid(List<Map<String, dynamic>> records) {
    double charges = records.fold(0.0, (s, r) => s + ((r['charges'] as num?)?.toDouble() ?? 0.0));
    int wins = records.fold(0, (s, r) => s + ((r['wins'] as num?)?.toInt() ?? 0));
    int losses = records.fold(0, (s, r) => s + ((r['losses'] as num?)?.toInt() ?? 0));

    return GridView.count(
      crossAxisCount: 2,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      childAspectRatio: 1.8,
      mainAxisSpacing: 16,
      crossAxisSpacing: 16,
      children: [
        _cyberStatCard('WIN TRADES', '$wins', Colors.greenAccent),
        _cyberStatCard('LOSS TRADES', '$losses', Colors.redAccent),
        _cyberStatCard('SYSTEM FEES', '₹${charges.toStringAsFixed(0)}', Colors.orangeAccent),
        _cyberStatCard('NET VOLUME', '${wins + losses}', Colors.cyanAccent),
      ],
    );
  }

  Widget _cyberStatCard(String label, String value, Color color) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.02),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: color.withValues(alpha: 0.1)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text(label, style: const TextStyle(color: Colors.white24, fontSize: 9, fontWeight: FontWeight.w900, letterSpacing: 1)),
          const SizedBox(height: 6),
          Text(value, style: TextStyle(color: color, fontWeight: FontWeight.w900, fontSize: 18)),
        ],
      ),
    );
  }

  Widget _buildDayTile(Map<String, dynamic> record) {
    final pnl = (record['total_pnl'] as num?)?.toDouble() ?? 0.0;
    final isProfit = pnl >= 0;
    final color = isProfit ? Colors.greenAccent : Colors.redAccent;
    
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 18),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.02),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text((record['date'] ?? '').toString(), style: const TextStyle(color: Colors.white70, fontWeight: FontWeight.w900, fontSize: 14)),
              Text('${record['total_trades'] ?? 0} SESSIONS', style: const TextStyle(color: Colors.white10, fontSize: 10, fontWeight: FontWeight.bold)),
            ],
          ),
          Text(
            '${isProfit ? '+' : ''}₹${pnl.toStringAsFixed(2)}',
            style: TextStyle(color: color, fontWeight: FontWeight.w900, fontSize: 16),
          ),
        ],
      ),
    );
  }

  List<Map<String, dynamic>> _getThisWeekRecords(List<Map<String, dynamic>> all) {
    final now = DateTime.now().toUtc();
    final weekStart = now.subtract(Duration(days: now.weekday - 1));
    final cutoff = DateTime(weekStart.year, weekStart.month, weekStart.day);
    return all.where((r) {
      final d = DateTime.tryParse(r['date'] ?? '');
      return d != null && !d.isBefore(cutoff);
    }).toList();
  }

  List<Map<String, dynamic>> _getThisMonthRecords(List<Map<String, dynamic>> all) {
    final now = DateTime.now().toUtc();
    final monthKey = '${now.year}-${now.month.toString().padLeft(2, '0')}';
    return all.where((r) => (r['month'] ?? '') == monthKey).toList();
  }

  List<FlSpot> _buildChartSpots(List<Map<String, dynamic>> records, String period) {
    final ordered = records.reversed.toList();
    double cumPnl = 0;
    final spots = <FlSpot>[];
    for (int i = 0; i < ordered.length; i++) {
      cumPnl += (ordered[i]['total_pnl'] as num?)?.toDouble() ?? 0.0;
      spots.add(FlSpot(i.toDouble(), cumPnl));
    }
    return spots;
  }
}
