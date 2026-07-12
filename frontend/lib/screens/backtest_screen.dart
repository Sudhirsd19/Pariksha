import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';

// ─── Config ─────────────────────────────────────────────────────────────────
const String _kBaseUrl = String.fromEnvironment(
  'BACKEND_URL',
  defaultValue: 'https://quantumindex.onrender.com',
);

// ─── Data Models ─────────────────────────────────────────────────────────────
class BacktestResult {
  final String symbol;
  final int days;
  final Map<String, dynamic> metrics;
  final List<double> equityCurve;
  final List<Map<String, dynamic>> trades;

  BacktestResult({
    required this.symbol,
    required this.days,
    required this.metrics,
    required this.equityCurve,
    required this.trades,
  });

  factory BacktestResult.fromJson(Map<String, dynamic> json) {
    return BacktestResult(
      symbol: json['symbol'] ?? '',
      days: json['days'] ?? 0,
      metrics: Map<String, dynamic>.from(json['metrics'] ?? {}),
      equityCurve: (json['equity_curve'] as List<dynamic>? ?? [])
          .map((e) => (e as num).toDouble())
          .toList(),
      trades: (json['trades'] as List<dynamic>? ?? [])
          .map((e) => Map<String, dynamic>.from(e))
          .toList(),
    );
  }
}

// ─── Screen ──────────────────────────────────────────────────────────────────
class BacktestScreen extends StatefulWidget {
  const BacktestScreen({super.key});

  @override
  State<BacktestScreen> createState() => _BacktestScreenState();
}

class _BacktestScreenState extends State<BacktestScreen>
    with SingleTickerProviderStateMixin {
  // Input state
  final _symbolController = TextEditingController(text: 'RELIANCE');
  int _selectedDays = 60;
  double _capital = 100000;
  int _minScore = 60;

  // Result state
  bool _isLoading = false;
  String? _error;
  BacktestResult? _result;

  // Tab controller for results
  late TabController _tabController;

  // Popular stocks for quick pick
  final List<String> _quickPicks = [
    'RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'ICICIBANK',
    'SBIN', 'WIPRO', 'ADANIPORTS', 'BAJFINANCE', 'TATASTEEL',
    'MARUTI', 'SUNPHARMA', 'TITAN', 'AXISBANK', 'LT',
  ];

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
  }

  @override
  void dispose() {
    _symbolController.dispose();
    _tabController.dispose();
    super.dispose();
  }

  // ── API Call ───────────────────────────────────────────────────────────────
  Future<void> _runBacktest() async {
    final sym = _symbolController.text.trim().toUpperCase();
    if (sym.isEmpty) return;

    setState(() {
      _isLoading = true;
      _error = null;
      _result = null;
    });

    try {
      final uri = Uri.parse('$_kBaseUrl/api/backtest/run').replace(
        queryParameters: {
          'symbol': sym,
          'days': _selectedDays.toString(),
          'capital': _capital.toStringAsFixed(0),
          'min_score': _minScore.toString(),
        },
      );
      final response = await http.post(uri).timeout(const Duration(minutes: 3));

      if (response.statusCode == 200) {
        final json = jsonDecode(response.body) as Map<String, dynamic>;
        if (json['status'] == 'success') {
          setState(() => _result = BacktestResult.fromJson(json));
        } else {
          setState(() => _error = json['error'] ?? 'Unknown error');
        }
      } else {
        setState(() => _error = 'Server error: ${response.statusCode}');
      }
    } catch (e) {
      setState(() => _error = 'Connection error: $e');
    } finally {
      setState(() => _isLoading = false);
    }
  }

  // ─────────────────────────────────────────────────────────────────────────
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF040408),
      body: Stack(
        children: [
          _buildBackground(),
          CustomScrollView(
            physics: const BouncingScrollPhysics(),
            slivers: [
              _buildAppBar(),
              SliverToBoxAdapter(child: _buildInputCard()),
              if (_isLoading) SliverToBoxAdapter(child: _buildLoader()),
              if (_error != null) SliverToBoxAdapter(child: _buildError()),
              if (_result != null) ...[
                SliverToBoxAdapter(child: _buildMetricsGrid()),
                SliverToBoxAdapter(child: _buildEquityChart()),
                SliverToBoxAdapter(child: _buildTradeLog()),
              ],
              const SliverToBoxAdapter(child: SizedBox(height: 120)),
            ],
          ),
        ],
      ),
    );
  }

  // ── Background ─────────────────────────────────────────────────────────────
  Widget _buildBackground() {
    return Positioned.fill(
      child: CustomPaint(painter: _BacktestBgPainter()),
    );
  }

  // ── AppBar ─────────────────────────────────────────────────────────────────
  Widget _buildAppBar() {
    return SliverAppBar(
      expandedHeight: 110,
      floating: true,
      pinned: true,
      elevation: 0,
      backgroundColor: Colors.transparent,
      flexibleSpace: ClipRRect(
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
          child: FlexibleSpaceBar(
            title: const Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.history_edu_rounded,
                    color: Colors.purpleAccent, size: 18),
                SizedBox(width: 8),
                Text(
                  'BACKTEST ENGINE',
                  style: TextStyle(
                    fontWeight: FontWeight.w900,
                    letterSpacing: 3,
                    fontSize: 13,
                    color: Colors.white,
                  ),
                ),
              ],
            ),
            background:
                Container(color: Colors.black.withValues(alpha: 0.3)),
          ),
        ),
      ),
    );
  }

  // ── Input Card ─────────────────────────────────────────────────────────────
  Widget _buildInputCard() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 0),
      child: _glassCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Title
            Row(
              children: [
                Container(
                  width: 4,
                  height: 20,
                  decoration: BoxDecoration(
                    color: Colors.purpleAccent,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
                const SizedBox(width: 10),
                const Text(
                  'STRATEGY PARAMETERS',
                  style: TextStyle(
                    color: Colors.white70,
                    fontSize: 11,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 2,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 20),

            // Symbol Input
            _labelText('SYMBOL'),
            const SizedBox(height: 6),
            TextField(
              controller: _symbolController,
              textCapitalization: TextCapitalization.characters,
              style: const TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.w700,
                  fontSize: 18),
              decoration: InputDecoration(
                hintText: 'e.g. RELIANCE',
                hintStyle: const TextStyle(color: Colors.white24, fontSize: 16),
                prefixIcon:
                    const Icon(Icons.search, color: Colors.purpleAccent),
                filled: true,
                fillColor: Colors.white.withValues(alpha: 0.05),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(14),
                  borderSide: BorderSide.none,
                ),
                focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(14),
                  borderSide: const BorderSide(
                      color: Colors.purpleAccent, width: 1.5),
                ),
              ),
            ),
            const SizedBox(height: 14),

            // Quick picks
            _labelText('QUICK PICK'),
            const SizedBox(height: 8),
            SizedBox(
              height: 34,
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                itemCount: _quickPicks.length,
                separatorBuilder: (_, __) => const SizedBox(width: 6),
                itemBuilder: (ctx, i) {
                  final sym = _quickPicks[i];
                  final active =
                      _symbolController.text.trim().toUpperCase() == sym;
                  return GestureDetector(
                    onTap: () =>
                        setState(() => _symbolController.text = sym),
                    child: AnimatedContainer(
                      duration: const Duration(milliseconds: 200),
                      padding: const EdgeInsets.symmetric(
                          horizontal: 14, vertical: 7),
                      decoration: BoxDecoration(
                        color: active
                            ? Colors.purpleAccent.withValues(alpha: 0.25)
                            : Colors.white.withValues(alpha: 0.05),
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(
                          color: active
                              ? Colors.purpleAccent
                              : Colors.white12,
                          width: active ? 1.5 : 1,
                        ),
                      ),
                      child: Text(
                        sym,
                        style: TextStyle(
                          color:
                              active ? Colors.purpleAccent : Colors.white54,
                          fontSize: 11,
                          fontWeight: FontWeight.w700,
                          letterSpacing: 0.5,
                        ),
                      ),
                    ),
                  );
                },
              ),
            ),
            const SizedBox(height: 20),

            // Days selector
            _labelText('DATE RANGE'),
            const SizedBox(height: 8),
            Row(
              children: [30, 60, 90, 180].map((d) {
                final active = _selectedDays == d;
                return Expanded(
                  child: GestureDetector(
                    onTap: () => setState(() => _selectedDays = d),
                    child: AnimatedContainer(
                      duration: const Duration(milliseconds: 200),
                      margin: const EdgeInsets.only(right: 6),
                      padding: const EdgeInsets.symmetric(vertical: 12),
                      decoration: BoxDecoration(
                        color: active
                            ? Colors.purpleAccent.withValues(alpha: 0.2)
                            : Colors.white.withValues(alpha: 0.04),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(
                          color: active
                              ? Colors.purpleAccent
                              : Colors.white12,
                          width: active ? 1.5 : 1,
                        ),
                      ),
                      child: Column(
                        children: [
                          Text(
                            '$d',
                            style: TextStyle(
                              color: active
                                  ? Colors.purpleAccent
                                  : Colors.white54,
                              fontSize: 18,
                              fontWeight: FontWeight.w900,
                            ),
                          ),
                          Text(
                            'days',
                            style: TextStyle(
                              color: active
                                  ? Colors.purpleAccent.withValues(alpha: 0.7)
                                  : Colors.white24,
                              fontSize: 9,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                );
              }).toList(),
            ),
            const SizedBox(height: 20),

            // Min Score
            _labelText('MIN WHALE SCORE: $_minScore / 100'),
            Slider(
              value: _minScore.toDouble(),
              min: 20,
              max: 90,
              divisions: 14,
              activeColor: Colors.purpleAccent,
              inactiveColor: Colors.white12,
              label: '$_minScore',
              onChanged: (v) => setState(() => _minScore = v.round()),
            ),
            const SizedBox(height: 8),

            // Capital
            _labelText('INITIAL CAPITAL'),
            const SizedBox(height: 8),
            Row(
              children: [50000, 100000, 500000, 1000000].map((c) {
                final active = _capital == c.toDouble();
                final label = c >= 100000
                    ? '₹${(c / 100000).toStringAsFixed(c >= 100000 && c % 100000 == 0 ? 0 : 1)}L'
                    : '₹${(c / 1000).toStringAsFixed(0)}K';
                return Expanded(
                  child: GestureDetector(
                    onTap: () => setState(() => _capital = c.toDouble()),
                    child: AnimatedContainer(
                      duration: const Duration(milliseconds: 200),
                      margin: const EdgeInsets.only(right: 6),
                      padding: const EdgeInsets.symmetric(vertical: 10),
                      decoration: BoxDecoration(
                        color: active
                            ? Colors.purpleAccent.withValues(alpha: 0.15)
                            : Colors.white.withValues(alpha: 0.04),
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(
                          color: active
                              ? Colors.purpleAccent
                              : Colors.white12,
                          width: active ? 1.5 : 1,
                        ),
                      ),
                      child: Text(
                        label,
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          color: active
                              ? Colors.purpleAccent
                              : Colors.white54,
                          fontSize: 12,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                    ),
                  ),
                );
              }).toList(),
            ),
            const SizedBox(height: 24),

            // Run Button
            SizedBox(
              width: double.infinity,
              height: 54,
              child: ElevatedButton(
                onPressed: _isLoading ? null : _runBacktest,
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.purpleAccent,
                  disabledBackgroundColor:
                      Colors.purpleAccent.withValues(alpha: 0.3),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(16)),
                  elevation: 0,
                ),
                child: _isLoading
                    ? const Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: Colors.white,
                            ),
                          ),
                          SizedBox(width: 12),
                          Text(
                            'RUNNING BACKTEST...',
                            style: TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.w900,
                              letterSpacing: 2,
                              fontSize: 13,
                            ),
                          ),
                        ],
                      )
                    : const Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(Icons.play_arrow_rounded,
                              color: Colors.white, size: 22),
                          SizedBox(width: 8),
                          Text(
                            'RUN BACKTEST',
                            style: TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.w900,
                              letterSpacing: 2,
                              fontSize: 14,
                            ),
                          ),
                        ],
                      ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  // ── Loader ─────────────────────────────────────────────────────────────────
  Widget _buildLoader() {
    return Padding(
      padding: const EdgeInsets.all(48),
      child: Column(
        children: [
          const SizedBox(
            width: 60,
            height: 60,
            child: CircularProgressIndicator(
              strokeWidth: 3,
              color: Colors.purpleAccent,
            ),
          ),
          const SizedBox(height: 20),
          Text(
            'Fetching ${_symbolController.text.trim().toUpperCase()} data\n& simulating $_selectedDays days...',
            textAlign: TextAlign.center,
            style: const TextStyle(
              color: Colors.white54,
              fontSize: 13,
              height: 1.6,
            ),
          ),
          const SizedBox(height: 10),
          const Text(
            'This may take 30–90 seconds',
            style: TextStyle(
              color: Colors.white24,
              fontSize: 11,
            ),
          ),
        ],
      ),
    );
  }

  // ── Error ──────────────────────────────────────────────────────────────────
  Widget _buildError() {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: Colors.red.withValues(alpha: 0.1),
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: Colors.red.withValues(alpha: 0.3)),
        ),
        child: Row(
          children: [
            const Icon(Icons.error_outline, color: Colors.redAccent, size: 20),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                _error!,
                style: const TextStyle(color: Colors.redAccent, fontSize: 13),
              ),
            ),
          ],
        ),
      ),
    );
  }

  // ── Metrics Grid ───────────────────────────────────────────────────────────
  Widget _buildMetricsGrid() {
    if (_result == null) return const SizedBox();
    final m = _result!.metrics;
    final totalPnl = (m['total_pnl'] as num?)?.toDouble() ?? 0;
    final pnlColor = totalPnl >= 0 ? Colors.greenAccent : Colors.redAccent;

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 20, 16, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header
          Row(
            children: [
              const Icon(Icons.bar_chart_rounded,
                  color: Colors.purpleAccent, size: 18),
              const SizedBox(width: 8),
              Text(
                '${_result!.symbol} — ${_result!.days}D RESULTS',
                style: const TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.w900,
                  fontSize: 14,
                  letterSpacing: 1.5,
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),

          // Hero PnL Card
          _glassCard(
            color: totalPnl >= 0
                ? Colors.green.withValues(alpha: 0.08)
                : Colors.red.withValues(alpha: 0.08),
            border: Border.all(
              color: pnlColor.withValues(alpha: 0.3),
            ),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'NET PROFIT / LOSS',
                        style: TextStyle(
                          color: Colors.white54,
                          fontSize: 10,
                          fontWeight: FontWeight.w700,
                          letterSpacing: 2,
                        ),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        '${totalPnl >= 0 ? '+' : ''}₹${totalPnl.toStringAsFixed(0)}',
                        style: TextStyle(
                          color: pnlColor,
                          fontSize: 32,
                          fontWeight: FontWeight.w900,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        '${((m['return_pct'] as num?) ?? 0) >= 0 ? '+' : ''}${m['return_pct']}% return on ₹${_capital.toStringAsFixed(0)}',
                        style:
                            TextStyle(color: pnlColor.withValues(alpha: 0.7), fontSize: 12),
                      ),
                    ],
                  ),
                ),
                Icon(
                  totalPnl >= 0
                      ? Icons.trending_up_rounded
                      : Icons.trending_down_rounded,
                  color: pnlColor,
                  size: 48,
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),

          // Metrics Grid
          GridView.count(
            crossAxisCount: 2,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            crossAxisSpacing: 10,
            mainAxisSpacing: 10,
            childAspectRatio: 2.0,
            children: [
              _metricTile('WIN RATE', '${m['win_rate']}%',
                  (m['win_rate'] as num? ?? 0) >= 50
                      ? Colors.greenAccent
                      : Colors.orangeAccent,
                  Icons.emoji_events_outlined),
              _metricTile('PROFIT FACTOR', '${m['profit_factor']}',
                  (m['profit_factor'] as num? ?? 0) >= 1.5
                      ? Colors.greenAccent
                      : Colors.orangeAccent,
                  Icons.show_chart_rounded),
              _metricTile('TOTAL TRADES', '${m['total_trades']}',
                  Colors.cyanAccent, Icons.receipt_long_outlined),
              _metricTile('MAX DRAWDOWN', '-${m['max_drawdown']}%',
                  (m['max_drawdown'] as num? ?? 0) <= 10
                      ? Colors.greenAccent
                      : Colors.redAccent,
                  Icons.arrow_downward_rounded),
              _metricTile('AVG WIN', '₹${m['avg_win']}', Colors.greenAccent,
                  Icons.add_circle_outline),
              _metricTile('AVG LOSS', '₹${m['avg_loss']}', Colors.redAccent,
                  Icons.remove_circle_outline),
              _metricTile('SHARPE RATIO', '${m['sharpe_ratio']}',
                  (m['sharpe_ratio'] as num? ?? 0) >= 1
                      ? Colors.greenAccent
                      : Colors.white54,
                  Icons.speed_rounded),
              _metricTile('TOTAL CHARGES', '₹${m['total_charges']}',
                  Colors.orangeAccent, Icons.receipt_outlined),
            ],
          ),
        ],
      ),
    );
  }

  Widget _metricTile(
      String label, String value, Color color, IconData icon) {
    return _glassCard(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      child: Row(
        children: [
          Icon(icon, color: color.withValues(alpha: 0.8), size: 20),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(
                  label,
                  style: const TextStyle(
                    color: Colors.white38,
                    fontSize: 8,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1.5,
                  ),
                ),
                const SizedBox(height: 3),
                Text(
                  value,
                  style: TextStyle(
                    color: color,
                    fontSize: 16,
                    fontWeight: FontWeight.w900,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // ── Equity Curve Chart ─────────────────────────────────────────────────────
  Widget _buildEquityChart() {
    if (_result == null || _result!.equityCurve.length < 2) return const SizedBox();
    final curve = _result!.equityCurve;
    final minY = curve.reduce((a, b) => a < b ? a : b);
    final maxY = curve.reduce((a, b) => a > b ? a : b);
    final isProfit = curve.last >= curve.first;

    final spots = List.generate(
      curve.length,
      (i) => FlSpot(i.toDouble(), curve[i]),
    );

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 20, 16, 0),
      child: _glassCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  width: 4,
                  height: 18,
                  decoration: BoxDecoration(
                    color: Colors.purpleAccent,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
                const SizedBox(width: 10),
                const Text(
                  'EQUITY CURVE',
                  style: TextStyle(
                    color: Colors.white70,
                    fontSize: 11,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 2,
                  ),
                ),
                const Spacer(),
                Text(
                  '${curve.length} data points',
                  style: const TextStyle(color: Colors.white24, fontSize: 10),
                ),
              ],
            ),
            const SizedBox(height: 20),
            SizedBox(
              height: 200,
              child: LineChart(
                LineChartData(
                  minY: minY * 0.995,
                  maxY: maxY * 1.005,
                  gridData: FlGridData(
                    show: true,
                    drawVerticalLine: false,
                    getDrawingHorizontalLine: (_) => FlLine(
                      color: Colors.white.withValues(alpha: 0.05),
                      strokeWidth: 1,
                    ),
                  ),
                  borderData: FlBorderData(show: false),
                  titlesData: FlTitlesData(
                    leftTitles: AxisTitles(
                      sideTitles: SideTitles(
                        showTitles: true,
                        reservedSize: 52,
                        getTitlesWidget: (val, meta) {
                          if (val == meta.min || val == meta.max) {
                            return Text(
                              '₹${(val / 1000).toStringAsFixed(0)}K',
                              style: const TextStyle(
                                  color: Colors.white38, fontSize: 9),
                            );
                          }
                          return const SizedBox();
                        },
                      ),
                    ),
                    rightTitles: const AxisTitles(
                        sideTitles: SideTitles(showTitles: false)),
                    topTitles: const AxisTitles(
                        sideTitles: SideTitles(showTitles: false)),
                    bottomTitles: const AxisTitles(
                        sideTitles: SideTitles(showTitles: false)),
                  ),
                  lineBarsData: [
                    LineChartBarData(
                      spots: spots,
                      isCurved: true,
                      curveSmoothness: 0.3,
                      color: isProfit ? Colors.greenAccent : Colors.redAccent,
                      barWidth: 2.5,
                      isStrokeCapRound: true,
                      dotData: const FlDotData(show: false),
                      belowBarData: BarAreaData(
                        show: true,
                        gradient: LinearGradient(
                          begin: Alignment.topCenter,
                          end: Alignment.bottomCenter,
                          colors: [
                            (isProfit ? Colors.greenAccent : Colors.redAccent)
                                .withValues(alpha: 0.2),
                            Colors.transparent,
                          ],
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
    );
  }

  // ── Trade Log ──────────────────────────────────────────────────────────────
  Widget _buildTradeLog() {
    if (_result == null || _result!.trades.isEmpty) return const SizedBox();
    final trades = _result!.trades.reversed.toList();

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 20, 16, 0),
      child: _glassCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  width: 4,
                  height: 18,
                  decoration: BoxDecoration(
                    color: Colors.purpleAccent,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
                const SizedBox(width: 10),
                const Text(
                  'TRADE LOG',
                  style: TextStyle(
                    color: Colors.white70,
                    fontSize: 11,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 2,
                  ),
                ),
                const Spacer(),
                Text(
                  '${_result!.trades.length} trades (latest first)',
                  style: const TextStyle(color: Colors.white24, fontSize: 10),
                ),
              ],
            ),
            const SizedBox(height: 14),

            // Column headers
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 4),
              child: Row(
                children: [
                  _colHeader('SIGNAL', flex: 1),
                  _colHeader('ENTRY', flex: 2),
                  _colHeader('EXIT', flex: 2),
                  _colHeader('P&L', flex: 2),
                  _colHeader('RESULT', flex: 2),
                ],
              ),
            ),
            const Divider(color: Colors.white12),

            // Trade rows
            ListView.separated(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              itemCount: trades.length,
              separatorBuilder: (_, __) =>
                  Divider(color: Colors.white.withValues(alpha: 0.04), height: 1),
              itemBuilder: (ctx, i) {
                final t = trades[i];
                final pnl = (t['net_pnl'] as num?)?.toDouble() ?? 0;
                final pnlColor =
                    pnl >= 0 ? Colors.greenAccent : Colors.redAccent;
                final sig = t['signal'] ?? 'BUY';
                final result = t['result'] ?? '';
                final isTarget = result == 'TARGET';

                return Padding(
                  padding: const EdgeInsets.symmetric(vertical: 10),
                  child: Row(
                    children: [
                      Expanded(
                        flex: 1,
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 6, vertical: 3),
                          decoration: BoxDecoration(
                            color: sig == 'BUY'
                                ? Colors.greenAccent.withValues(alpha: 0.15)
                                : Colors.redAccent.withValues(alpha: 0.15),
                            borderRadius: BorderRadius.circular(6),
                          ),
                          child: Text(
                            sig,
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              color: sig == 'BUY'
                                  ? Colors.greenAccent
                                  : Colors.redAccent,
                              fontSize: 9,
                              fontWeight: FontWeight.w900,
                            ),
                          ),
                        ),
                      ),
                      Expanded(
                        flex: 2,
                        child: Text(
                          '₹${t['entry'] ?? '—'}',
                          textAlign: TextAlign.center,
                          style: const TextStyle(
                              color: Colors.white70, fontSize: 11),
                        ),
                      ),
                      Expanded(
                        flex: 2,
                        child: Text(
                          '₹${t['exit'] ?? '—'}',
                          textAlign: TextAlign.center,
                          style: const TextStyle(
                              color: Colors.white70, fontSize: 11),
                        ),
                      ),
                      Expanded(
                        flex: 2,
                        child: Text(
                          '${pnl >= 0 ? '+' : ''}₹${pnl.toStringAsFixed(0)}',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            color: pnlColor,
                            fontSize: 12,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                      ),
                      Expanded(
                        flex: 2,
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 6, vertical: 3),
                          decoration: BoxDecoration(
                            color: isTarget
                                ? Colors.greenAccent.withValues(alpha: 0.1)
                                : Colors.redAccent.withValues(alpha: 0.1),
                            borderRadius: BorderRadius.circular(6),
                          ),
                          child: Text(
                            result.replaceAll('_', ' '),
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              color: isTarget
                                  ? Colors.greenAccent
                                  : Colors.redAccent,
                              fontSize: 8,
                              fontWeight: FontWeight.w800,
                              letterSpacing: 0.5,
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                );
              },
            ),
          ],
        ),
      ),
    );
  }

  // ── Helpers ────────────────────────────────────────────────────────────────
  Widget _colHeader(String text, {int flex = 1}) {
    return Expanded(
      flex: flex,
      child: Text(
        text,
        textAlign: TextAlign.center,
        style: const TextStyle(
          color: Colors.white38,
          fontSize: 8,
          fontWeight: FontWeight.w800,
          letterSpacing: 1,
        ),
      ),
    );
  }

  Widget _labelText(String text) {
    return Text(
      text,
      style: const TextStyle(
        color: Colors.white38,
        fontSize: 9,
        fontWeight: FontWeight.w700,
        letterSpacing: 2,
      ),
    );
  }

  Widget _glassCard({
    required Widget child,
    EdgeInsetsGeometry padding =
        const EdgeInsets.all(18),
    Color? color,
    Border? border,
  }) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(18),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
        child: Container(
          padding: padding,
          decoration: BoxDecoration(
            color: color ?? Colors.white.withValues(alpha: 0.04),
            borderRadius: BorderRadius.circular(18),
            border: border ??
                Border.all(color: Colors.white.withValues(alpha: 0.08)),
          ),
          child: child,
        ),
      ),
    );
  }
}

// ─── Background Painter ───────────────────────────────────────────────────────
class _BacktestBgPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()..style = PaintingStyle.fill;

    paint.color = const Color(0xFF7B2FBE).withValues(alpha: 0.06);
    canvas.drawCircle(Offset(size.width * 0.85, size.height * 0.1), 220, paint);

    paint.color = const Color(0xFF4A1FAD).withValues(alpha: 0.05);
    canvas.drawCircle(Offset(size.width * 0.1, size.height * 0.5), 180, paint);

    paint.color = const Color(0xFF9B59B6).withValues(alpha: 0.04);
    canvas.drawCircle(Offset(size.width * 0.6, size.height * 0.85), 150, paint);
  }

  @override
  bool shouldRepaint(_) => false;
}
