import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/trading_provider.dart';

class StockScannerScreen extends StatefulWidget {
  const StockScannerScreen({super.key});

  @override
  State<StockScannerScreen> createState() => _StockScannerScreenState();
}

class _StockScannerScreenState extends State<StockScannerScreen> {
  final TextEditingController _searchController = TextEditingController();
  final FocusNode _searchFocusNode = FocusNode();

  // Top Indian liquid stock recommendations
  final List<String> _suggestions = [
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "TATASTEEL", "SBIN", "BHARTIARTL", "WIPRO", "ADANIPORTS"
  ];

  // Price filter limit
  double? _selectedPriceLimit;

  // Typical prices mapping for suggestions
  final Map<String, double> _refPrices = {
    "RELIANCE": 2900.0,
    "TCS": 3800.0,
    "INFY": 1500.0,
    "HDFCBANK": 1500.0,
    "ICICIBANK": 1100.0,
    "TATASTEEL": 160.0,
    "SBIN": 800.0,
    "BHARTIARTL": 1400.0,
    "WIPRO": 460.0,
    "ADANIPORTS": 1300.0,
  };

  @override
  void dispose() {
    _searchController.dispose();
    _searchFocusNode.dispose();
    super.dispose();
  }

  void _triggerScan(String symbol) {
    if (symbol.isEmpty) return;
    _searchFocusNode.unfocus();
    Provider.of<TradingProvider>(context, listen: false).scanStock(symbol.trim().toUpperCase());
  }

  @override
  Widget build(BuildContext context) {
    final provider = Provider.of<TradingProvider>(context);
    final isScanning = provider.isScanning;
    final data = provider.scannedStockData;

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
                leading: IconButton(
                  icon: const Icon(Icons.arrow_back_ios_new_rounded, color: Colors.white70),
                  onPressed: () => Navigator.pop(context),
                ),
                flexibleSpace: ClipRRect(
                  child: BackdropFilter(
                    filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
                    child: FlexibleSpaceBar(
                      title: const Text(
                        'STOCK SCANNER',
                        style: TextStyle(
                          fontWeight: FontWeight.w900,
                          letterSpacing: 4,
                          fontSize: 14,
                          color: Colors.white,
                        ),
                      ),
                      background: Container(color: Colors.black.withValues(alpha: 0.3)),
                    ),
                  ),
                ),
              ),

              SliverPadding(
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
                sliver: SliverList(
                  delegate: SliverChildListDelegate([
                    // Search Section
                    _buildSearchCard(isScanning),
                    const SizedBox(height: 20),

                    // Scanner State / Results
                    if (isScanning)
                      _buildLoadingIndicator()
                    else if (data == null)
                      _buildEmptyState()
                    else if (data['status'] == 'error')
                      _buildErrorState(data['message'] ?? "Unknown error occurred.")
                    else
                      _buildScanResults(context, provider, data),

                    // Watchlist Panel - Visible at the bottom when not scanning
                    if (!isScanning && provider.watchlist.isNotEmpty) ...[
                      const SizedBox(height: 32),
                      _buildWatchlistPanel(context, provider),
                    ],

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
        Positioned(
          top: 100,
          right: -100,
          child: _buildOrb(400, Colors.cyanAccent.withValues(alpha: 0.05)),
        ),
        Positioned(
          bottom: 100,
          left: -150,
          child: _buildOrb(500, Colors.purpleAccent.withValues(alpha: 0.05)),
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
            blurRadius: 120,
            spreadRadius: 60,
          )
        ],
      ),
    );
  }

  Widget _buildPriceFilters() {
    final filters = [
      {"label": "ALL", "val": null},
      {"label": "< ₹500", "val": 500.0},
      {"label": "< ₹1000", "val": 1000.0},
      {"label": "< ₹1500", "val": 1500.0},
      {"label": "< ₹3000", "val": 3000.0},
    ];

    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      physics: const BouncingScrollPhysics(),
      child: Row(
        children: filters.map((f) {
          final isSelected = _selectedPriceLimit == f["val"];
          return Padding(
            padding: const EdgeInsets.only(right: 8),
            child: GestureDetector(
              onTap: () {
                setState(() {
                  _selectedPriceLimit = f["val"] as double?;
                });
              },
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                decoration: BoxDecoration(
                  color: isSelected ? Colors.cyanAccent.withValues(alpha: 0.15) : Colors.white.withValues(alpha: 0.02),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(
                    color: isSelected ? Colors.cyanAccent.withValues(alpha: 0.5) : Colors.white.withValues(alpha: 0.05),
                    width: 1,
                  ),
                ),
                child: Text(
                  f["label"] as String,
                  style: TextStyle(
                    color: isSelected ? Colors.cyanAccent : Colors.white60,
                    fontSize: 10,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ),
          );
        }).toList(),
      ),
    );
  }

  Widget _buildSearchCard(bool isScanning) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.02),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: Colors.white.withValues(alpha: 0.05)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            "COMPANY SCAN PACKETS",
            style: TextStyle(
              color: Colors.white30,
              fontSize: 10,
              fontWeight: FontWeight.w900,
              letterSpacing: 2,
            ),
          ),
          const SizedBox(height: 14),
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _searchController,
                  focusNode: _searchFocusNode,
                  style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
                  decoration: InputDecoration(
                    hintText: "Enter Symbol (e.g. RELIANCE, TCS)",
                    hintStyle: const TextStyle(color: Colors.white24, fontSize: 13),
                    filled: true,
                    fillColor: Colors.white.withValues(alpha: 0.03),
                    contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(16),
                      borderSide: BorderSide.none,
                    ),
                    focusedBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(16),
                      borderSide: const BorderSide(color: Colors.cyanAccent, width: 1.5),
                    ),
                  ),
                  onSubmitted: (val) => _triggerScan(val),
                ),
              ),
              const SizedBox(width: 12),
              GestureDetector(
                onTap: isScanning ? null : () => _triggerScan(_searchController.text),
                child: Container(
                  height: 52,
                  width: 52,
                  decoration: BoxDecoration(
                    color: isScanning ? Colors.white10 : Colors.cyanAccent.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(
                      color: isScanning ? Colors.white10 : Colors.cyanAccent.withValues(alpha: 0.3),
                      width: 1.5,
                    ),
                  ),
                  child: Icon(
                    Icons.search_rounded,
                    color: isScanning ? Colors.white30 : Colors.cyanAccent,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          _buildPriceFilters(),
          const SizedBox(height: 16),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: _suggestions.map((symbol) {
              return GestureDetector(
                onTap: isScanning
                    ? null
                    : () {
                        _searchController.text = symbol;
                        _triggerScan(symbol);
                      },
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: 0.03),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: Colors.white.withValues(alpha: 0.05)),
                  ),
                  child: Text(
                    symbol,
                    style: const TextStyle(
                      color: Colors.white70,
                      fontSize: 11,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
              );
            }).toList(),
          ),
        ],
      ),
    );
  }

  Widget _buildLoadingIndicator() {
    return Container(
      height: 250,
      alignment: Alignment.center,
      child: const Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          CircularProgressIndicator(
            color: Colors.cyanAccent,
            strokeWidth: 3,
          ),
          SizedBox(height: 20),
          Text(
            "COMPILING FUNDAMENTAL & TECHNICAL CHANNELS...",
            textAlign: TextAlign.center,
            style: TextStyle(
              color: Colors.white30,
              fontSize: 10,
              fontWeight: FontWeight.bold,
              letterSpacing: 1.5,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildEmptyState() {
    return Container(
      height: 250,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.01),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: Colors.white.withValues(alpha: 0.02)),
      ),
      child: const Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.radar_rounded, size: 48, color: Colors.white10),
          SizedBox(height: 16),
          Text(
            "AWAITING TARGET RESOLUTION",
            style: TextStyle(
              color: Colors.white30,
              fontSize: 12,
              fontWeight: FontWeight.w900,
              letterSpacing: 2,
            ),
          ),
          SizedBox(height: 6),
          Text(
            "Search or select a ticker above to run algorithms.",
            style: TextStyle(color: Colors.white10, fontSize: 11),
          ),
        ],
      ),
    );
  }

  Widget _buildErrorState(String message) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: Colors.redAccent.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: Colors.redAccent.withValues(alpha: 0.2)),
      ),
      child: Column(
        children: [
          const Icon(Icons.error_outline_rounded, size: 36, color: Colors.redAccent),
          const SizedBox(height: 12),
          const Text(
            "RESOLVER CONNECTION ERROR",
            style: TextStyle(
              color: Colors.redAccent,
              fontSize: 12,
              fontWeight: FontWeight.w900,
              letterSpacing: 1.5,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            message,
            textAlign: TextAlign.center,
            style: const TextStyle(color: Colors.white60, fontSize: 12),
          ),
        ],
      ),
    );
  }

  Widget _buildScanResults(BuildContext context, TradingProvider provider, Map<String, dynamic> data) {
    final int score = data['score'] ?? 0;
    final bool actionable = data['actionable'] ?? false;
    final String symbol = data['symbol'] ?? "";
    final double ltp = (data['ltp'] as num?)?.toDouble() ?? 0.0;
    final checklist = data['checklist'] as List<dynamic>? ?? [];

    Color scoreColor = Colors.redAccent;
    if (score >= 70) {
      scoreColor = Colors.greenAccent;
    } else if (score >= 40) {
      scoreColor = Colors.orangeAccent;
    }

    return Column(
      children: [
        // Score Header Card
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 20),
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: 0.02),
            borderRadius: BorderRadius.circular(28),
            border: Border.all(color: scoreColor.withValues(alpha: 0.15)),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Flexible(
                          child: Text(
                            symbol,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 24,
                              fontWeight: FontWeight.w900,
                              letterSpacing: -0.5,
                            ),
                          ),
                        ),
                        const SizedBox(width: 8),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                          decoration: BoxDecoration(
                            color: Colors.white10,
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: const Text(
                            "NSE CASH",
                            style: TextStyle(
                              color: Colors.cyanAccent,
                              fontSize: 9,
                              fontWeight: FontWeight.w900,
                              letterSpacing: 1,
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Text(
                      "₹${ltp.toStringAsFixed(2)}",
                      style: const TextStyle(
                        color: Colors.white70,
                        fontSize: 18,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        Icon(
                          actionable ? Icons.check_circle_rounded : Icons.info_outline_rounded,
                          color: scoreColor,
                          size: 14,
                        ),
                        const SizedBox(width: 6),
                        Text(
                          actionable
                              ? "ALGO SUITE APPROVED"
                              : "ALGO SUITE REJECTED",
                          style: TextStyle(
                            color: scoreColor,
                            fontSize: 10,
                            fontWeight: FontWeight.w900,
                            letterSpacing: 1,
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  (() {
                    final inWatchlist = provider.watchlist.any((item) => item['symbol'] == symbol);
                    return IconButton(
                      padding: EdgeInsets.zero,
                      constraints: const BoxConstraints(),
                      icon: Icon(
                        inWatchlist ? Icons.star_rounded : Icons.star_border_rounded,
                        color: inWatchlist ? Colors.amberAccent : Colors.white30,
                      ),
                      iconSize: 26,
                      onPressed: () {
                        if (inWatchlist) {
                          provider.removeFromWatchlist(symbol);
                        } else {
                          provider.addToWatchlist(data);
                        }
                      },
                    );
                  })(),
                  const SizedBox(width: 8),
                  SizedBox(
                    width: 76,
                    height: 76,
                    child: Stack(
                      fit: StackFit.expand,
                      children: [
                        CircularProgressIndicator(
                          value: score / 100,
                          strokeWidth: 6,
                          backgroundColor: Colors.white.withValues(alpha: 0.05),
                          color: scoreColor,
                          strokeCap: StrokeCap.round,
                        ),
                        Center(
                          child: Text(
                            "$score%",
                            style: TextStyle(
                              color: scoreColor,
                              fontSize: 16,
                              fontWeight: FontWeight.w900,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 20),

        // Checklist Items
        Container(
          padding: const EdgeInsets.all(24),
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: 0.02),
            borderRadius: BorderRadius.circular(28),
            border: Border.all(color: Colors.white.withValues(alpha: 0.04)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                "VERIFICATION CHECKLIST",
                style: TextStyle(
                  color: Colors.white30,
                  fontSize: 10,
                  fontWeight: FontWeight.w900,
                  letterSpacing: 2,
                ),
              ),
              const SizedBox(height: 16),
              ListView.separated(
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                itemCount: checklist.length,
                separatorBuilder: (context, idx) => Divider(
                  color: Colors.white.withValues(alpha: 0.03),
                  height: 24,
                ),
                itemBuilder: (context, idx) {
                  final item = checklist[idx];
                  final bool pass = item['status'] == 'Pass';
                  final String name = item['item'] ?? "";
                  final String detail = item['detail'] ?? "";
                  final int points = item['points'] ?? 0;

                  return Row(
                    children: [
                      Icon(
                        pass ? Icons.check_circle_outline_rounded : Icons.cancel_outlined,
                        color: pass ? Colors.greenAccent : Colors.redAccent,
                        size: 20,
                      ),
                      const SizedBox(width: 14),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              name,
                              style: const TextStyle(
                                color: Colors.white,
                                fontWeight: FontWeight.bold,
                                fontSize: 13,
                              ),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              detail,
                              style: const TextStyle(
                                color: Colors.white30,
                                fontSize: 11,
                              ),
                            ),
                          ],
                        ),
                      ),
                      Text(
                        "+$points pts",
                        style: TextStyle(
                          color: pass ? Colors.white30 : Colors.white10,
                          fontSize: 11,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ],
                  );
                },
              ),
            ],
          ),
        ),
        const SizedBox(height: 24),

        // Execution Row
        Row(
          children: [
            Expanded(
              child: _buildActionButton(
                label: "EXECUTE ALGO BUY",
                color: Colors.greenAccent,
                onPressed: () => _executeTrade(context, provider, symbol, "BUY"),
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: _buildActionButton(
                label: "EXECUTE ALGO SELL",
                color: Colors.redAccent,
                onPressed: () => _executeTrade(context, provider, symbol, "SELL"),
              ),
            ),
          ],
        ),
      ],
    );
  }



  Widget _buildActionButton({required String label, required Color color, required VoidCallback onPressed}) {
    return GestureDetector(
      onTap: onPressed,
      child: Container(
        height: 56,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.1),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: color.withValues(alpha: 0.3), width: 1.5),
          boxShadow: [
            BoxShadow(
              color: color.withValues(alpha: 0.05),
              blurRadius: 12,
              spreadRadius: 2,
            )
          ],
        ),
        child: Text(
          label,
          style: TextStyle(
            color: color,
            fontWeight: FontWeight.w900,
            fontSize: 12,
            letterSpacing: 2,
          ),
        ),
      ),
    );
  }

  void _executeTrade(BuildContext context, TradingProvider provider, String symbol, String side) {
    showDialog(
      context: context,
      builder: (ctx) {
        return BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 5, sigmaY: 5),
          child: AlertDialog(
            backgroundColor: const Color(0xFF0F0F1A),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(24),
              side: const BorderSide(color: Colors.white10),
            ),
            title: Text(
              "CONFIRM ALGO EXECUTION",
              style: TextStyle(
                color: side == "BUY" ? Colors.greenAccent : Colors.redAccent,
                fontWeight: FontWeight.w900,
                fontSize: 14,
                letterSpacing: 2,
              ),
            ),
            content: Text(
              "Are you sure you want to trigger a dynamic $side algo trade for $symbol in the NSE Cash Segment?",
              style: const TextStyle(color: Colors.white70, fontSize: 13),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(ctx),
                child: const Text("CANCEL", style: TextStyle(color: Colors.white24, fontWeight: FontWeight.bold)),
              ),
              ElevatedButton(
                style: ElevatedButton.styleFrom(
                  backgroundColor: side == "BUY" ? Colors.green : Colors.red,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                ),
                onPressed: () async {
                  Navigator.pop(ctx);
                  await provider.executeStockTrade(symbol, side);
                },
                child: const Text("EXECUTE", style: TextStyle(fontWeight: FontWeight.w900, color: Colors.white)),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildWatchlistPanel(BuildContext context, TradingProvider provider) {
    final bool isRefreshing = provider.isRefreshingWatchlist;
    final filteredWatchlist = provider.watchlist.where((item) {
      if (_selectedPriceLimit == null) return true;
      final double ltp = (item['ltp'] as num?)?.toDouble() ?? 0.0;
      return ltp <= _selectedPriceLimit!;
    }).toList();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            const Text(
              "ACTIVE WATCHLIST",
              style: TextStyle(
                color: Colors.white30,
                fontSize: 10,
                fontWeight: FontWeight.w900,
                letterSpacing: 2,
              ),
            ),
            if (isRefreshing)
              const SizedBox(
                width: 12,
                height: 12,
                child: CircularProgressIndicator(
                  strokeWidth: 1.5,
                  valueColor: AlwaysStoppedAnimation<Color>(Colors.white30),
                ),
              )
            else
              GestureDetector(
                onTap: () => provider.refreshWatchlist(),
                child: const Icon(
                  Icons.refresh_rounded,
                  color: Colors.white30,
                  size: 16,
                ),
              ),
          ],
        ),
        const SizedBox(height: 14),
        if (filteredWatchlist.isEmpty)
          Container(
            padding: const EdgeInsets.symmetric(vertical: 24),
            width: double.infinity,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.01),
              borderRadius: BorderRadius.circular(20),
              border: Border.all(color: Colors.white.withValues(alpha: 0.02)),
            ),
            child: const Text(
              "No watchlist items under selected price limit",
              style: TextStyle(
                color: Colors.white24,
                fontSize: 11,
                fontStyle: FontStyle.italic,
              ),
            ),
          )
        else
          ListView.separated(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            itemCount: filteredWatchlist.length,
            separatorBuilder: (context, idx) => const SizedBox(height: 12),
            itemBuilder: (context, idx) {
              final item = filteredWatchlist[idx];
              final String symbol = item['symbol'] ?? "";
              final double ltp = (item['ltp'] as num?)?.toDouble() ?? 0.0;
              final int score = item['score'] ?? 0;
              final String rec = item['recommendation'] ?? "NEUTRAL";

              // Find if this stock has an active trade open
              final activeTrade = provider.signals.firstWhere(
                (sig) => (sig['symbol'] == "$symbol-EQ" || sig['symbol'] == symbol) && sig['status'] != "CLOSED",
                orElse: () => null,
              );
              final bool hasActive = activeTrade != null;
              final String? tradeSide = hasActive ? activeTrade['signal'] : null;

              Color scoreColor = Colors.redAccent;
              if (score >= 70) {
                scoreColor = Colors.greenAccent;
              } else if (score >= 40) {
                scoreColor = Colors.orangeAccent;
              }

              return Container(
                padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.02),
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: Colors.white.withValues(alpha: 0.04)),
                ),
                child: Row(
                  children: [
                    GestureDetector(
                      onTap: () {
                        _searchController.text = symbol;
                        _triggerScan(symbol);
                      },
                      child: Row(
                        children: [
                          Container(
                            width: 8,
                            height: 8,
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              color: scoreColor,
                            ),
                          ),
                          const SizedBox(width: 12),
                          Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  Text(
                                    symbol,
                                    style: const TextStyle(
                                      color: Colors.white,
                                      fontWeight: FontWeight.bold,
                                      fontSize: 14,
                                    ),
                                  ),
                                  if (hasActive) ...[
                                    const SizedBox(width: 8),
                                    Container(
                                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                      decoration: BoxDecoration(
                                        color: (tradeSide == "BUY" ? Colors.green : Colors.red).withValues(alpha: 0.15),
                                        borderRadius: BorderRadius.circular(6),
                                        border: Border.all(
                                          color: (tradeSide == "BUY" ? Colors.greenAccent : Colors.redAccent).withValues(alpha: 0.3),
                                          width: 1,
                                        ),
                                      ),
                                      child: Text(
                                        tradeSide == "BUY" ? "BUY ACTIVE" : "SELL ACTIVE",
                                        style: TextStyle(
                                          color: tradeSide == "BUY" ? Colors.greenAccent : Colors.redAccent,
                                          fontSize: 8,
                                          fontWeight: FontWeight.w900,
                                        ),
                                      ),
                                    ),
                                  ],
                                ],
                              ),
                              const SizedBox(height: 2),
                              Text(
                                "₹${ltp.toStringAsFixed(2)} | Score: $score%",
                                style: const TextStyle(
                                  color: Colors.white30,
                                  fontSize: 11,
                                ),
                              ),
                            ],
                          ),
                      ],
                    ),
                  ),
                  const Spacer(),
                  if (rec == "BUY")
                    _buildQuickExecutionButton(
                      context,
                      label: "BUY",
                      color: Colors.greenAccent,
                      onPressed: () => _executeTrade(context, provider, symbol, "BUY"),
                    )
                  else if (rec == "SELL")
                    _buildQuickExecutionButton(
                      context,
                      label: "SELL",
                      color: Colors.redAccent,
                      onPressed: () => _executeTrade(context, provider, symbol, "SELL"),
                    )
                  else
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                      decoration: BoxDecoration(
                        color: Colors.white.withValues(alpha: 0.03),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: const Text(
                        "NEUTRAL",
                        style: TextStyle(color: Colors.white30, fontSize: 10, fontWeight: FontWeight.bold),
                      ),
                    ),
                  const SizedBox(width: 12),
                  IconButton(
                    icon: const Icon(Icons.delete_outline_rounded, color: Colors.white24, size: 20),
                    onPressed: () => provider.removeFromWatchlist(symbol),
                  ),
                ],
              ),
            );
          },
        ),
      ],
    );
  }

  Widget _buildQuickExecutionButton(
    BuildContext context, {
    required String label,
    required Color color,
    required VoidCallback onPressed,
  }) {
    return GestureDetector(
      onTap: onPressed,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.1),
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: color.withValues(alpha: 0.3), width: 1),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: color,
            fontWeight: FontWeight.w900,
            fontSize: 10,
            letterSpacing: 1,
          ),
        ),
      ),
    );
  }
}
