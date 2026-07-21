import 'dart:async';
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

  // Top Indian liquid stock quick-tap suggestions
  final List<String> _suggestions = [
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "TATASTEEL", "SBIN", "BHARTIARTL", "WIPRO", "ADANIPORTS"
  ];

  // Overlay-based search dropdown
  OverlayEntry? _dropdownOverlay;
  final LayerLink _layerLink = LayerLink();
  List<Map<String, dynamic>> _searchResults = [];
  Timer? _debounce;

  // Price filter limit
  double? _selectedPriceLimit;

  @override
  void initState() {
    super.initState();
    _searchController.addListener(_onSearchChanged);
    _searchFocusNode.addListener(() {
      if (!_searchFocusNode.hasFocus) {
        // Add a small delay so that if the user tapped on a dropdown item,
        // the onTap event has time to fire before the overlay is removed.
        Future.delayed(const Duration(milliseconds: 150), () {
          if (mounted) _removeDropdown();
        });
      }
    });
  }

  void _onSearchChanged() {
    final query = _searchController.text.trim();
    if (_debounce?.isActive ?? false) _debounce!.cancel();
    if (query.isEmpty) {
      _removeDropdown();
      return;
    }
    _debounce = Timer(const Duration(milliseconds: 300), () async {
      final provider = Provider.of<TradingProvider>(context, listen: false);
      final results = await provider.searchStocks(query);
      if (!mounted) return;
      _searchResults = results;
      if (results.isNotEmpty && _searchFocusNode.hasFocus) {
        _showDropdownOverlay();
      } else {
        _removeDropdown();
      }
    });
  }

  void _showDropdownOverlay() {
    _removeDropdown();
    _dropdownOverlay = OverlayEntry(
      builder: (context) {
        return Positioned(
          width: MediaQuery.of(context).size.width - 40 - 12 - 52, // screen - horizontal padding - gap - button
          child: CompositedTransformFollower(
            link: _layerLink,
            showWhenUnlinked: false,
            offset: const Offset(0, 56),
            child: Material(
              color: Colors.transparent,
              child: Container(
                constraints: const BoxConstraints(maxHeight: 280),
                decoration: BoxDecoration(
                  color: const Color(0xFF0E0E1C),
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: Colors.cyanAccent.withValues(alpha: 0.25), width: 1),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withValues(alpha: 0.6),
                      blurRadius: 24,
                      offset: const Offset(0, 8),
                    ),
                    BoxShadow(
                      color: Colors.cyanAccent.withValues(alpha: 0.08),
                      blurRadius: 16,
                      spreadRadius: 1,
                    ),
                  ],
                ),
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(16),
                  child: ListView.builder(
                    padding: EdgeInsets.zero,
                    shrinkWrap: true,
                    physics: const BouncingScrollPhysics(),
                    itemCount: _searchResults.length,
                    itemBuilder: (ctx, index) {
                      final item = _searchResults[index];
                      final String name = item['name'] ?? '';
                      final String symbol = item['symbol'] ?? '';
                      return GestureDetector(
                        behavior: HitTestBehavior.opaque,
                        onTap: () => _selectStock(name),
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 13),
                          decoration: BoxDecoration(
                            border: index < _searchResults.length - 1
                                ? Border(bottom: BorderSide(color: Colors.white.withValues(alpha: 0.05)))
                                : null,
                          ),
                          child: Row(
                            children: [
                              Container(
                                width: 6,
                                height: 6,
                                decoration: const BoxDecoration(
                                  shape: BoxShape.circle,
                                  color: Colors.cyanAccent,
                                ),
                              ),
                              const SizedBox(width: 12),
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
                                    Text(
                                      symbol,
                                      style: TextStyle(
                                        color: Colors.white.withValues(alpha: 0.35),
                                        fontSize: 10,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                              Icon(
                                Icons.north_west_rounded,
                                color: Colors.white.withValues(alpha: 0.2),
                                size: 14,
                              ),
                            ],
                          ),
                        ),
                      );
                    },
                  ),
                ),
              ),
            ),
          ),
        );
      },
    );
    Overlay.of(context).insert(_dropdownOverlay!);
  }

  void _removeDropdown() {
    _dropdownOverlay?.remove();
    _dropdownOverlay = null;
  }

  void _selectStock(String symbol) {
    _removeDropdown();
    _searchController.removeListener(_onSearchChanged);
    _searchController.text = symbol;
    _searchController.addListener(_onSearchChanged);
    _searchResults = [];
    _triggerScan(symbol);
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _removeDropdown();
    _searchController.removeListener(_onSearchChanged);
    _searchController.dispose();
    _searchFocusNode.dispose();
    super.dispose();
  }

  void _triggerScan(String symbol, {double? ltp}) {
    if (symbol.isEmpty) return;
    _searchFocusNode.unfocus();
    Provider.of<TradingProvider>(context, listen: false).scanStock(symbol.trim().toUpperCase(), ltp: ltp);
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
          const _MeshBackground(),
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
                    else if (data == null) ...[
                      _SmartScreenerCard(
                        onExecuteTrade: (symbol, side, ltp) => _executeTrade(context, provider, symbol, side, ltp),
                      ),
                    ]
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
          // Search row with CompositedTransformTarget for Overlay positioning
          CompositedTransformTarget(
            link: _layerLink,
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _searchController,
                    focusNode: _searchFocusNode,
                    style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
                    decoration: InputDecoration(
                      hintText: "Search company (e.g. BANK, TATA, HDFC)",
                      hintStyle: const TextStyle(color: Colors.white24, fontSize: 13),
                      filled: true,
                      fillColor: Colors.white.withValues(alpha: 0.03),
                      contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
                      prefixIcon: const Icon(Icons.search_rounded, color: Colors.white30, size: 18),
                      suffixIcon: _searchController.text.isNotEmpty
                          ? IconButton(
                              icon: const Icon(Icons.close_rounded, color: Colors.white30, size: 18),
                              onPressed: () {
                                _searchController.clear();
                                _removeDropdown();
                                Provider.of<TradingProvider>(context, listen: false).clearScannedStock();
                              },
                            )
                          : null,
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(16),
                        borderSide: BorderSide.none,
                      ),
                      focusedBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(16),
                        borderSide: const BorderSide(color: Colors.cyanAccent, width: 1.5),
                      ),
                    ),
                    onSubmitted: (val) => _selectStock(val.trim().toUpperCase()),
                  ),
                ),
                const SizedBox(width: 12),
                GestureDetector(
                  onTap: isScanning ? null : () => _selectStock(_searchController.text.trim().toUpperCase()),
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
                    : () => _selectStock(symbol),
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
    final double adxScore = (data['strict_score'] as num?)?.toDouble() ?? 0.0;
    // BUG-1 FIX: Removed dead `signals` list. Backend returns strict_signal/strict_score/strict_breakdown,
    // not a signals[] list. The signals card below has been removed accordingly.
    final bool actionable = (data['strict_signal'] ?? 'NONE') != 'NONE';
    
    final String symbol = data['symbol'] ?? "";
    final double ltp = (data['ltp'] as num?)?.toDouble() ?? 0.0;

    final activeTrade = provider.activeTradeMap[symbol];
    final bool hasActive = activeTrade != null;
    final String? tradeSide = hasActive ? activeTrade['signal'] : null;

    Color scoreColor = adxScore >= 80 ? Colors.greenAccent : adxScore >= 65 ? Colors.cyanAccent : Colors.white24;

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
                        const SizedBox(width: 8),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                          decoration: BoxDecoration(
                            color: (data['strict_score'] == 100)
                                ? Colors.deepOrangeAccent.withValues(alpha: 0.2)
                                : Colors.blueGrey.withValues(alpha: 0.2),
                            borderRadius: BorderRadius.circular(8),
                            border: Border.all(
                              color: (data['strict_score'] == 100)
                                  ? Colors.orangeAccent
                                  : Colors.blueGrey.withValues(alpha: 0.5),
                            ),
                          ),
                          child: Text(
                            (data['strict_score'] == 100)
                                ? "🔥 100% WHALE ${data['strict_signal']} 🟠"
                                : "Score: ${data['strict_score'] ?? '0'}",
                            style: TextStyle(
                              color: (data['strict_score'] == 100)
                                  ? Colors.orangeAccent
                                  : Colors.blueGrey.shade300,
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
                  IconButton(
                    padding: EdgeInsets.zero,
                    constraints: const BoxConstraints(),
                    icon: const Icon(Icons.refresh_rounded, color: Colors.white54),
                    iconSize: 26,
                    onPressed: () {
                      _triggerScan(symbol);
                    },
                  ),
                  const SizedBox(width: 12),
                  IconButton(
                    padding: EdgeInsets.zero,
                    constraints: const BoxConstraints(),
                    icon: const Icon(Icons.close_rounded, color: Colors.white54),
                    iconSize: 26,
                    onPressed: () {
                      provider.clearScannedStock();
                    },
                  ),
                  const SizedBox(width: 12),
                  (() {
                    final cleanSymbol = symbol.replaceAll('.NS', '');
                    final inWatchlist = provider.watchlist.any((item) => item['symbol'].toString().replaceAll('.NS', '') == cleanSymbol);
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
                          value: (adxScore / 100).clamp(0.0, 1.0),
                          strokeWidth: 6,
                          backgroundColor: Colors.white.withValues(alpha: 0.05),
                          color: scoreColor,
                          strokeCap: StrokeCap.round,
                        ),
                        Center(
                          child: Column(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Text(
                                adxScore.toInt().toString(),
                                style: TextStyle(
                                  color: scoreColor,
                                  fontSize: 16,
                                  fontWeight: FontWeight.w900,
                                ),
                              ),
                              Text(
                                "SCORE",
                                style: TextStyle(
                                  color: scoreColor.withValues(alpha: 0.7),
                                  fontSize: 7,
                                  fontWeight: FontWeight.bold,
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
            ],
          ),
        ),
        const SizedBox(height: 16),

        // Whale Score Breakdown
        if (data['strict_breakdown'] != null && (data['strict_breakdown'] as Map).isNotEmpty)
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
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      "WHALE SCORE BREAKDOWN".toUpperCase(),
                      style: const TextStyle(
                        color: Colors.white30,
                        fontSize: 10,
                        fontWeight: FontWeight.w900,
                        letterSpacing: 2,
                      ),
                    ),
                    Text(
                      "${data['strict_score'] ?? 0}/100",
                      style: TextStyle(
                        color: (data['strict_score'] == 100) ? Colors.orangeAccent : Colors.white70,
                        fontSize: 12,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                Column(
                  mainAxisSize: MainAxisSize.min,
                  children: (data['strict_breakdown'] as Map).entries.map((entry) {
                    final key = entry.key;
                    final value = entry.value;
                    // Define max points per category
                    final hasNewSMC = (data['strict_breakdown'] as Map).containsKey("SMC Structure");
                    int maxPts = 0;
                    if (key == "Macro Trend") {
                      maxPts = 15;
                    } else if (key == "Fundamentals") {
                      maxPts = 10;
                    } else if (key == "Price Action") {
                      maxPts = 25;
                    } else if (key == "Volume") {
                      maxPts = 20;
                    } else if (key == "Momentum") {
                      maxPts = hasNewSMC ? 20 : 15;
                    } else if (key == "Risk & Execution") {
                      maxPts = 15;
                    } else if (key == "SMC Structure") {
                      maxPts = 25;
                    } else if (key == "Trend & MTF") {
                      maxPts = 20;
                    } else if (key == "Volume & VWAP") {
                      maxPts = 20;
                    } else if (key == "Candlestick") {
                      maxPts = 10;
                    } else if (key == "Risk Quality") {
                      maxPts = 5;
                    }

                    final double pct = maxPts > 0 ? ((value as num).toDouble() / maxPts) : 0;
                    final Color barColor = pct == 1.0 ? Colors.greenAccent : (pct > 0 ? Colors.orangeAccent : Colors.white24);

                    return Padding(
                      padding: const EdgeInsets.only(bottom: 12.0),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Text(
                                key.toString(),
                                style: const TextStyle(
                                  color: Colors.white70,
                                  fontSize: 12,
                                  fontWeight: FontWeight.bold,
                                ),
                              ),
                              Text(
                                "$value / $maxPts PTS",
                                style: TextStyle(
                                  color: barColor,
                                  fontSize: 11,
                                  fontWeight: FontWeight.w900,
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 6),
                          ClipRRect(
                            borderRadius: BorderRadius.circular(4),
                            child: LinearProgressIndicator(
                              value: pct,
                              backgroundColor: Colors.white.withValues(alpha: 0.05),
                              valueColor: AlwaysStoppedAnimation<Color>(barColor),
                              minHeight: 4,
                            ),
                          ),
                        ],
                      ),
                    );
                  }).toList(),
                ),
              ],
            ),
          ),
        if (data['strict_breakdown'] != null && (data['strict_breakdown'] as Map).isNotEmpty)
          const SizedBox(height: 24),

        // Execution Row
        (() {
          if (hasActive) {
            final Color activeColor = tradeSide == "BUY" ? Colors.greenAccent : Colors.redAccent;
            return Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(vertical: 16),
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: activeColor.withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: activeColor.withValues(alpha: 0.3), width: 1.5),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(Icons.lock_clock_outlined, color: activeColor, size: 18),
                  const SizedBox(width: 10),
                  Text(
                    "ALGO $tradeSide ACTIVE FOR $symbol",
                    style: TextStyle(
                      color: activeColor,
                      fontWeight: FontWeight.w900,
                      fontSize: 12,
                      letterSpacing: 1.5,
                    ),
                  ),
                ],
              ),
            );
          }

          // Daily lock check: prevent trading the same stock if it was already traded TODAY
          // FIX HIGH-08: Was missing date filter — yesterday's closed trades were locking stock permanently
          final nowForLock = DateTime.now();
          final todayStartMs = DateTime(nowForLock.year, nowForLock.month, nowForLock.day).millisecondsSinceEpoch;
          final closedTrades = provider.signals.where(
            (sig) {
              final String sigSym = sig['symbol'] ?? '';
              final isMatch = sigSym == "$symbol-EQ" || sigSym == symbol;
              final isClosed = sig['status'] == "CLOSED";
              // FIX HIGH-08: Only count TODAY's trades for the daily lock
              final int ts = sig['timestamp'] is num 
                  ? (sig['timestamp'] as num).toInt()
                  : (double.tryParse(sig['timestamp']?.toString() ?? '')?.toInt() ?? 0);
              final isToday = ts >= todayStartMs;
              return isMatch && isClosed && isToday;
            }
          ).toList();
          final bool isLockedToday = closedTrades.isNotEmpty;
          if (isLockedToday) {
            return Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(vertical: 16),
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: Colors.redAccent.withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: Colors.redAccent.withValues(alpha: 0.3), width: 1.5),
              ),
              child: const Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(Icons.lock_outline_rounded, color: Colors.redAccent, size: 18),
                  SizedBox(width: 10),
                  Text(
                    "LOCKED: STOCK TRADED TODAY",
                    style: TextStyle(
                      color: Colors.redAccent,
                      fontWeight: FontWeight.w900,
                      fontSize: 12,
                      letterSpacing: 1.5,
                    ),
                  ),
                ],
              ),
            );
          }

          return Row(
            children: [
              Expanded(
                child: _buildActionButton(
                  label: "EXECUTE ALGO BUY",
                  color: Colors.greenAccent,
                  onPressed: () => _executeTrade(context, provider, symbol, "BUY", (data['ltp'] as num?)?.toDouble() ?? 0.0),
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: _buildActionButton(
                  label: "EXECUTE ALGO SELL",
                  color: Colors.redAccent,
                  onPressed: () => _executeTrade(context, provider, symbol, "SELL", (data['ltp'] as num?)?.toDouble() ?? 0.0),
                ),
              ),
            ],
          );
        })(),
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

  void _executeTrade(BuildContext context, TradingProvider provider, String symbol, String side, double ltp) {
    // ── MARKET HOURS GUARD (IST) ──────────────────────────────────────────
    final nowIst = DateTime.now().toUtc().add(const Duration(hours: 5, minutes: 30));
    final weekday = nowIst.weekday; // 1=Mon … 5=Fri, 6=Sat, 7=Sun
    final t = TimeOfDay(hour: nowIst.hour, minute: nowIst.minute);
    final tMins = t.hour * 60 + t.minute;
    const marketOpen   = 9 * 60 + 15;  // 9:15 AM
    const entryCutoff  = 14 * 60 + 30; // 2:30 PM — no new intraday entries

    String? blockedReason;
    if (weekday >= 6) {
      blockedReason = 'Market closed today (${weekday == 6 ? 'Saturday' : 'Sunday'}). NSE trades Mon–Fri only.';
    } else if (tMins < marketOpen) {
      blockedReason = 'Market not open yet. NSE opens at 9:15 AM IST.';
    } else if (tMins >= entryCutoff) {
      blockedReason = 'Entry blocked after 2:30 PM IST. Auto square-off is at 3:10 PM — insufficient time for a new intraday position.';
    }

    if (blockedReason != null) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Row(
            children: [
              const Icon(Icons.access_time_rounded, color: Colors.white, size: 16),
              const SizedBox(width: 10),
              Expanded(child: Text(blockedReason, style: const TextStyle(fontWeight: FontWeight.bold))),
            ],
          ),
          backgroundColor: const Color(0xFF8B1A1A),
          duration: const Duration(seconds: 4),
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        ),
      );
      return;
    }
    // ──────────────────────────────────────────────────────────────────────

    if (ltp <= 0) ltp = 100.0;
    final double capitalLimit = (provider.systemSettings['capital_limit'] as num?)?.toDouble() ?? 10000.0;
    int maxQty = (capitalLimit / ltp).floor();
    if (maxQty <= 0) maxQty = 1;

    // Default: start with MAX quantity (full capital utilization)
    int selectedQty = maxQty;
    final TextEditingController qtyController = TextEditingController(text: maxQty.toString());

    final Color sideColor = side == 'BUY' ? Colors.greenAccent : Colors.redAccent;

    // SL/TP values (2% SL, 4% TP — same as backend)
    final double sl = side == 'BUY' ? ltp * 0.98 : ltp * 1.02;
    final double tp = side == 'BUY' ? ltp * 1.04 : ltp * 0.96;

    showDialog(
      context: context,
      builder: (ctx) {
        return StatefulBuilder(
          builder: (context, setS) {
            final double totalValue = selectedQty * ltp;
            final bool isValid = selectedQty > 0 && selectedQty <= maxQty;
            // Recalculate charges based on current qty selection
            final double estCharges = double.parse(((ltp * selectedQty * 0.00035) + 20).toStringAsFixed(2));
            final double slLoss   = (selectedQty * (ltp - sl).abs()) + estCharges;
            final double tpProfit = (selectedQty * (tp - ltp).abs()) - estCharges;

            void setQtyPercent(double pct) {
              final int q = ((capitalLimit * pct) / ltp).floor();
              setS(() {
                selectedQty = q < 1 ? 1 : (q > maxQty ? maxQty : q);
                qtyController.text = selectedQty.toString();
              });
            }

            return BackdropFilter(
              filter: ImageFilter.blur(sigmaX: 6, sigmaY: 6),
              child: AlertDialog(
                backgroundColor: const Color(0xFF0D0D1C),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(24),
                  side: BorderSide(color: sideColor.withValues(alpha: 0.3), width: 1.2),
                ),
                contentPadding: const EdgeInsets.fromLTRB(20, 0, 20, 0),
                titlePadding: const EdgeInsets.fromLTRB(20, 20, 20, 12),
                title: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Container(
                          padding: const EdgeInsets.all(8),
                          decoration: BoxDecoration(
                            color: sideColor.withValues(alpha: 0.12),
                            shape: BoxShape.circle,
                          ),
                          child: Icon(
                            side == 'BUY' ? Icons.trending_up_rounded : Icons.trending_down_rounded,
                            color: sideColor, size: 18,
                          ),
                        ),
                        const SizedBox(width: 12),
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              '$side  $symbol',
                              style: TextStyle(color: sideColor, fontWeight: FontWeight.w900, fontSize: 15, letterSpacing: 1),
                            ),
                            Text(
                              '₹${ltp.toStringAsFixed(2)} per share  •  NSE Cash',
                              style: const TextStyle(color: Colors.white38, fontSize: 10),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ],
                ),
                content: SingleChildScrollView(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Divider(color: Colors.white.withValues(alpha: 0.06)),
                      const SizedBox(height: 12),

                      // ── Capital info row ──────────────────────────────
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          _infoCell('CAPITAL LIMIT', '₹${capitalLimit.toStringAsFixed(0)}', Colors.white60),
                          _infoCell('MAX SHARES', '$maxQty', Colors.cyanAccent),
                          _infoCell('PRICE', '₹${ltp.toStringAsFixed(2)}', Colors.white60),
                        ],
                      ),
                      const SizedBox(height: 18),

                      // ── Preset % buttons ──────────────────────────────
                      const Text('CAPITAL ALLOCATION', style: TextStyle(color: Colors.white24, fontSize: 9, fontWeight: FontWeight.w900, letterSpacing: 1.5)),
                      const SizedBox(height: 8),
                      Row(
                        children: [
                          _pctBtn('25%',  0.25, selectedQty, maxQty, capitalLimit, ltp, sideColor, setQtyPercent),
                          const SizedBox(width: 8),
                          _pctBtn('50%',  0.50, selectedQty, maxQty, capitalLimit, ltp, sideColor, setQtyPercent),
                          const SizedBox(width: 8),
                          _pctBtn('75%',  0.75, selectedQty, maxQty, capitalLimit, ltp, sideColor, setQtyPercent),
                          const SizedBox(width: 8),
                          _pctBtn('MAX', 1.00, selectedQty, maxQty, capitalLimit, ltp, sideColor, setQtyPercent),
                        ],
                      ),
                      const SizedBox(height: 16),

                      // ── Qty stepper ───────────────────────────────────
                      const Text('QUANTITY (SHARES)', style: TextStyle(color: Colors.white24, fontSize: 9, fontWeight: FontWeight.w900, letterSpacing: 1.5)),
                      const SizedBox(height: 8),
                      Row(
                        children: [
                          GestureDetector(
                            onTap: selectedQty > 1
                                ? () => setS(() {
                                      selectedQty--;
                                      qtyController.text = selectedQty.toString();
                                    })
                                : null,
                            child: Container(
                              padding: const EdgeInsets.all(10),
                              decoration: BoxDecoration(
                                color: Colors.white.withValues(alpha: 0.06),
                                borderRadius: BorderRadius.circular(10),
                              ),
                              child: Icon(Icons.remove_rounded,
                                  color: selectedQty > 1 ? Colors.white70 : Colors.white12, size: 18),
                            ),
                          ),
                          Expanded(
                            child: TextField(
                              controller: qtyController,
                              keyboardType: TextInputType.number,
                              textAlign: TextAlign.center,
                              style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w900, fontSize: 20),
                              decoration: InputDecoration(
                                contentPadding: const EdgeInsets.symmetric(vertical: 10),
                                enabledBorder: OutlineInputBorder(
                                  borderSide: BorderSide(color: Colors.white.withValues(alpha: 0.1)),
                                  borderRadius: BorderRadius.circular(12),
                                ),
                                focusedBorder: OutlineInputBorder(
                                  borderSide: BorderSide(color: sideColor.withValues(alpha: 0.6)),
                                  borderRadius: BorderRadius.circular(12),
                                ),
                              ),
                              onChanged: (val) {
                                final parsed = int.tryParse(val) ?? 0;
                                setS(() => selectedQty = parsed);
                              },
                            ),
                          ),
                          GestureDetector(
                            onTap: selectedQty < maxQty
                                ? () => setS(() {
                                      selectedQty++;
                                      qtyController.text = selectedQty.toString();
                                    })
                                : null,
                            child: Container(
                              padding: const EdgeInsets.all(10),
                              decoration: BoxDecoration(
                                color: Colors.white.withValues(alpha: 0.06),
                                borderRadius: BorderRadius.circular(10),
                              ),
                              child: Icon(Icons.add_rounded,
                                  color: selectedQty < maxQty ? Colors.white70 : Colors.white12, size: 18),
                            ),
                          ),
                        ],
                      ),

                      if (selectedQty > maxQty) ...[
                        const SizedBox(height: 6),
                        Text(
                          '⚠ Capital limit exceeded! Max: $maxQty shares',
                          style: const TextStyle(color: Colors.redAccent, fontSize: 10, fontWeight: FontWeight.bold),
                        ),
                      ],
                      const SizedBox(height: 18),

                      // ── Trade summary ─────────────────────────────────
                      Divider(color: Colors.white.withValues(alpha: 0.06)),
                      const SizedBox(height: 12),
                      const Text('TRADE SUMMARY', style: TextStyle(color: Colors.white24, fontSize: 9, fontWeight: FontWeight.w900, letterSpacing: 1.5)),
                      const SizedBox(height: 10),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          _infoCell('TOTAL VALUE', '₹${totalValue.toStringAsFixed(0)}', Colors.white),
                          _infoCell('CHARGES', '~₹${estCharges.toStringAsFixed(0)}', Colors.white38),
                          _infoCell('SL', '₹${sl.toStringAsFixed(2)}', Colors.redAccent),
                          _infoCell('TARGET', '₹${tp.toStringAsFixed(2)}', Colors.greenAccent),
                        ],
                      ),
                      const SizedBox(height: 14),

                      // ── Risk/Reward summary ───────────────────────────
                      Row(
                        children: [
                          Expanded(
                            child: Container(
                              padding: const EdgeInsets.all(12),
                              decoration: BoxDecoration(
                                color: Colors.redAccent.withValues(alpha: 0.08),
                                borderRadius: BorderRadius.circular(12),
                                border: Border.all(color: Colors.redAccent.withValues(alpha: 0.2)),
                              ),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  const Text('MAX LOSS', style: TextStyle(color: Colors.redAccent, fontSize: 8, fontWeight: FontWeight.w900, letterSpacing: 1)),
                                  const SizedBox(height: 3),
                                  Text('-₹${slLoss.toStringAsFixed(0)}', style: const TextStyle(color: Colors.redAccent, fontWeight: FontWeight.w900, fontSize: 14)),
                                  Text('~ATR-based SL', style: TextStyle(color: Colors.redAccent.withValues(alpha: 0.5), fontSize: 9)),
                                ],
                              ),
                            ),
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Container(
                              padding: const EdgeInsets.all(12),
                              decoration: BoxDecoration(
                                color: Colors.greenAccent.withValues(alpha: 0.08),
                                borderRadius: BorderRadius.circular(12),
                                border: Border.all(color: Colors.greenAccent.withValues(alpha: 0.2)),
                              ),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  const Text('MAX PROFIT', style: TextStyle(color: Colors.greenAccent, fontSize: 8, fontWeight: FontWeight.w900, letterSpacing: 1)),
                                  const SizedBox(height: 3),
                                  Text('+₹${tpProfit.toStringAsFixed(0)}', style: const TextStyle(color: Colors.greenAccent, fontWeight: FontWeight.w900, fontSize: 14)),
                                  Text('~ATR-based TP', style: TextStyle(color: Colors.greenAccent.withValues(alpha: 0.5), fontSize: 9)),
                                ],
                              ),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 10),
                      // IMPROVE-2: Risk:Reward ratio display
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                        decoration: BoxDecoration(
                          color: Colors.white.withValues(alpha: 0.03),
                          borderRadius: BorderRadius.circular(10),
                          border: Border.all(color: Colors.white.withValues(alpha: 0.07)),
                        ),
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            const Icon(Icons.balance_rounded, size: 12, color: Colors.white38),
                            const SizedBox(width: 6),
                            Text(
                              'Risk : Reward  →  1 : ${slLoss > 0 ? (tpProfit / slLoss).clamp(0.0, 99.0).toStringAsFixed(2) : "∞"}',
                              style: const TextStyle(color: Colors.white54, fontSize: 11, fontWeight: FontWeight.bold),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 20),
                    ],
                  ),
                ),
                actions: [
                  TextButton(
                    onPressed: () => Navigator.pop(ctx),
                    child: const Text('CANCEL', style: TextStyle(color: Colors.white24, fontWeight: FontWeight.bold)),
                  ),
                  ElevatedButton(
                    style: ElevatedButton.styleFrom(
                      backgroundColor: side == 'BUY' ? const Color(0xFF1B6B3A) : const Color(0xFF6B1B1B),
                      foregroundColor: Colors.white,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                    ),
                    onPressed: isValid
                        ? () async {
                            Navigator.pop(ctx);
                            await provider.executeStockTrade(symbol, side, selectedQty, ltp: ltp);
                          }
                        : null,
                    child: Text(
                      '$side  $selectedQty shares',
                      style: const TextStyle(fontWeight: FontWeight.w900, letterSpacing: 1),
                    ),
                  ),
                ],
              ),
            );
          },
        );
      },
    );
  }

  // Helper: small info cell for dialog
  Widget _infoCell(String label, String value, Color color) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: const TextStyle(color: Colors.white24, fontSize: 8, fontWeight: FontWeight.w900, letterSpacing: 0.8)),
        const SizedBox(height: 2),
        Text(value, style: TextStyle(color: color, fontWeight: FontWeight.bold, fontSize: 12)),
      ],
    );
  }

  // Helper: capital % preset button
  Widget _pctBtn(String label, double pct, int currentQty, int maxQty, double capital, double ltp, Color color, void Function(double) onTap) {
    final int q = ((capital * pct) / ltp).floor();
    final int resolvedQty = q < 1 ? 1 : (q > maxQty ? maxQty : q);
    final bool isSelected = currentQty == resolvedQty;
    return Expanded(
      child: GestureDetector(
        onTap: () => onTap(pct),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 150),
          padding: const EdgeInsets.symmetric(vertical: 8),
          decoration: BoxDecoration(
            color: isSelected ? color.withValues(alpha: 0.18) : Colors.white.withValues(alpha: 0.04),
            borderRadius: BorderRadius.circular(10),
            border: Border.all(
              color: isSelected ? color.withValues(alpha: 0.5) : Colors.white.withValues(alpha: 0.08),
            ),
          ),
          child: Column(
            children: [
              Text(label, style: TextStyle(color: isSelected ? color : Colors.white38, fontWeight: FontWeight.w900, fontSize: 11)),
              Text('$resolvedQty', style: TextStyle(color: isSelected ? color.withValues(alpha: 0.8) : Colors.white24, fontSize: 9)),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildWatchlistPanel(BuildContext context, TradingProvider provider) {
    final bool isRefreshing = provider.isRefreshingWatchlist;
    final filteredWatchlist = provider.watchlist.where((item) {
      if (_selectedPriceLimit != null) {
        final double ltp = (item['ltp'] as num?)?.toDouble() ?? 0.0;
        if (ltp > _selectedPriceLimit!) return false;
      }
      return true;
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
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: Colors.deepPurpleAccent.withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(6),
                    border: Border.all(color: Colors.deepPurpleAccent.withValues(alpha: 0.3)),
                  ),
                  child: const Row(
                    children: [
                      Icon(Icons.refresh_rounded, color: Colors.deepPurpleAccent, size: 14),
                      SizedBox(width: 4),
                      Text(
                        "REFRESH",
                        style: TextStyle(
                          color: Colors.deepPurpleAccent,
                          fontSize: 9,
                          fontWeight: FontWeight.w900,
                          letterSpacing: 1,
                        ),
                      ),
                    ],
                  ),
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
              final int strictScore = item['strict_score'] ?? 0;
              final String strictSignal = item['strict_signal'] ?? 'NONE';
              
              String rec = 'WAIT';
              if (strictSignal.contains('BUY')) {
                rec = 'BUY';
              } else if (strictSignal.contains('SELL')) {
                rec = 'SELL';
              }

              // Use pre-computed trade map for O(1) lookup
              final activeTrade = provider.activeTradeMap[symbol];
              final bool hasActive = activeTrade != null;
              final String? tradeSide = hasActive ? activeTrade['signal'] : null;

              final Color scoreColor = strictScore >= 80 ? Colors.greenAccent
                  : strictScore >= 65 ? Colors.cyanAccent : Colors.white24;

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
                        // BUG-4 FIX: Pass known LTP so scan result shows correct price instead of ₹0.00
                        _triggerScan(symbol, ltp: ltp);
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
                                  const SizedBox(width: 8),
                                  Container(
                                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                    decoration: BoxDecoration(
                                      color: (item['strict_score'] == 100)
                                          ? Colors.deepOrangeAccent.withValues(alpha: 0.2)
                                          : Colors.blueGrey.withValues(alpha: 0.2),
                                      borderRadius: BorderRadius.circular(6),
                                      border: Border.all(
                                        color: (item['strict_score'] == 100)
                                            ? Colors.orangeAccent
                                            : Colors.blueGrey.withValues(alpha: 0.5),
                                      ),
                                    ),
                                    child: Text(
                                      (item['strict_score'] == 100)
                                          ? "🔥 100% WHALE ${item['strict_signal']} 🟠"
                                          : "Score: ${item['strict_score'] ?? '0'}",
                                      style: TextStyle(
                                        color: (item['strict_score'] == 100)
                                            ? Colors.orangeAccent
                                            : Colors.blueGrey.shade300,
                                        fontSize: 9,
                                        fontWeight: FontWeight.w900,
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 2),
                              Text(
                                "₹${ltp.toStringAsFixed(2)}",
                                style: const TextStyle(
                                  color: Colors.white60,
                                  fontSize: 10,
                                ),
                              ),
                            ],
                          ),
                        ],
                      ),
                    ),
                  const Spacer(),
                  if (hasActive)
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                      decoration: BoxDecoration(
                        color: (tradeSide == "BUY" ? Colors.green : Colors.red).withValues(alpha: 0.1),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: (tradeSide == "BUY" ? Colors.greenAccent : Colors.redAccent).withValues(alpha: 0.2)),
                      ),
                      child: Text(
                        "ACTIVE",
                        style: TextStyle(
                          color: tradeSide == "BUY" ? Colors.greenAccent : Colors.redAccent,
                          fontSize: 10,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    )
                  else if (rec == "BUY")
                    _buildQuickExecutionButton(
                      context,
                      label: "BUY",
                      color: Colors.greenAccent,
                      onPressed: () => _executeTrade(context, provider, symbol, "BUY", ltp),
                    )
                  else if (rec == "SELL")
                    _buildQuickExecutionButton(
                      context,
                      label: "SELL",
                      color: Colors.redAccent,
                      onPressed: () => _executeTrade(context, provider, symbol, "SELL", ltp),
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
                        style: TextStyle(color: Colors.white60, fontSize: 10, fontWeight: FontWeight.bold),
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

// ─────────────────────────────────────────────
// SMART SCREENER CARD (separate StatefulWidget)
// ─────────────────────────────────────────────
class _SmartScreenerCard extends StatefulWidget {
  final void Function(String symbol, String side, double ltp) onExecuteTrade;
  const _SmartScreenerCard({required this.onExecuteTrade});

  @override
  State<_SmartScreenerCard> createState() => _SmartScreenerCardState();
}

class _SmartScreenerCardState extends State<_SmartScreenerCard> {
  double _minPrice = 0;
  double _maxPrice = 500;
  bool _isScanning = false;
  List<Map<String, dynamic>> _results = [];
  int _scanned = 0;
  bool _hasScanned = false;
  String? _error;

  final List<double> _minLimits = [0, 100, 200, 500, 1000];
  final List<double> _maxLimits = [200, 500, 1000, 1500, 3000];

  Future<void> _runScan() async {
    setState(() {
      _isScanning = true;
      _error = null;
      _results = [];
      _hasScanned = false;
    });
    try {
      if (!mounted) return;
      final provider = Provider.of<TradingProvider>(context, listen: false);
      final res = await provider.smartScreener(_minPrice, _maxPrice);
      if (!mounted) return;
      if (res != null && res['status'] == 'success') {
        setState(() {
          _results = List<Map<String, dynamic>>.from(
            (res['results'] as List).map((e) => Map<String, dynamic>.from(e)),
          );
          _scanned = res['scanned'] ?? 0;
          _hasScanned = true;
        });
      } else {
        setState(() => _error = "Scan failed. Backend offline ya market band hai.");
      }
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = "Error: $e");
    } finally {
      if (mounted) {
        setState(() => _isScanning = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final provider = Provider.of<TradingProvider>(context);
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [
            const Color(0xFF0A0A18),
            Colors.deepPurple.withValues(alpha: 0.08),
          ],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: Colors.deepPurpleAccent.withValues(alpha: 0.2), width: 1),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: Colors.deepPurpleAccent.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: const Icon(Icons.auto_awesome_rounded, color: Colors.deepPurpleAccent, size: 18),
              ),
              const SizedBox(width: 12),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    "SMART SCREENER",
                    style: TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.w900,
                      fontSize: 14,
                      letterSpacing: 1.5,
                    ),
                  ),
                  Text(
                    "Price Range: ₹${_minPrice.toInt()} - ₹${_maxPrice.toInt()}",
                    style: const TextStyle(color: Colors.white38, fontSize: 10),
                  ),
                ],
              ),
            ],
          ),
          const SizedBox(height: 18),

          // Price Filter Label (Min Price)
          const Text(
            "FROM (MIN PRICE)",
            style: TextStyle(color: Colors.white30, fontSize: 9, fontWeight: FontWeight.w900, letterSpacing: 2),
          ),
          const SizedBox(height: 10),

          // Min Price Chips
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: _minLimits.map((price) {
              final selected = _minPrice == price;
              return GestureDetector(
                onTap: () => setState(() {
                  _minPrice = price;
                  if (_minPrice >= _maxPrice) {
                    _maxPrice = _minPrice + 500;
                  }
                }),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 200),
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                  decoration: BoxDecoration(
                    color: selected
                        ? Colors.deepPurpleAccent.withValues(alpha: 0.25)
                        : Colors.white.withValues(alpha: 0.03),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: selected
                          ? Colors.deepPurpleAccent.withValues(alpha: 0.6)
                          : Colors.white.withValues(alpha: 0.07),
                      width: 1.2,
                    ),
                  ),
                  child: Text(
                    "₹${price.toInt()}",
                    style: TextStyle(
                      color: selected ? Colors.deepPurpleAccent : Colors.white54,
                      fontWeight: FontWeight.bold,
                      fontSize: 12,
                    ),
                  ),
                ),
              );
            }).toList(),
          ),
          const SizedBox(height: 18),

          // Price Filter Label (Max Price)
          const Text(
            "TO (MAX PRICE)",
            style: TextStyle(color: Colors.white30, fontSize: 9, fontWeight: FontWeight.w900, letterSpacing: 2),
          ),
          const SizedBox(height: 10),

          // Max Price Chips
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: _maxLimits.map((price) {
              final selected = _maxPrice == price;
              return GestureDetector(
                onTap: () => setState(() {
                  _maxPrice = price;
                  if (_maxPrice <= _minPrice) {
                    _minPrice = _maxPrice >= 500 ? _maxPrice - 500 : 0;
                  }
                }),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 200),
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                  decoration: BoxDecoration(
                    color: selected
                        ? Colors.deepPurpleAccent.withValues(alpha: 0.25)
                        : Colors.white.withValues(alpha: 0.03),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: selected
                          ? Colors.deepPurpleAccent.withValues(alpha: 0.6)
                          : Colors.white.withValues(alpha: 0.07),
                      width: 1.2,
                    ),
                  ),
                  child: Text(
                    "₹${price.toInt()}",
                    style: TextStyle(
                      color: selected ? Colors.deepPurpleAccent : Colors.white54,
                      fontWeight: FontWeight.bold,
                      fontSize: 12,
                    ),
                  ),
                ),
              );
            }).toList(),
          ),
          const SizedBox(height: 18),



          GestureDetector(
            onTap: _isScanning ? null : _runScan,
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 200),
              width: double.infinity,
              padding: const EdgeInsets.symmetric(vertical: 14),
              decoration: BoxDecoration(
                gradient: _isScanning
                    ? null
                    : LinearGradient(
                        colors: [
                          Colors.deepPurpleAccent.withValues(alpha: 0.6),
                          Colors.purpleAccent.withValues(alpha: 0.4),
                        ],
                      ),
                color: _isScanning ? Colors.white10 : null,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(
                  color: _isScanning ? Colors.white10 : Colors.deepPurpleAccent.withValues(alpha: 0.4),
                ),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  if (_isScanning)
                    const SizedBox(
                      width: 14,
                      height: 14,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: Colors.white38,
                      ),
                    )
                  else
                    const Icon(Icons.radar_rounded, color: Colors.deepPurpleAccent, size: 16),
                  const SizedBox(width: 8),
                  Text(
                    _isScanning ? "SCANNING... (takes ~30-60s)" : "SCAN NOW",
                    style: TextStyle(
                      color: _isScanning ? Colors.white30 : Colors.white,
                      fontWeight: FontWeight.w900,
                      fontSize: 13,
                      letterSpacing: 1.5,
                    ),
                  ),
                ],
              ),
            ),
          ),

          // Results Section
          if (_error != null) ...[
            const SizedBox(height: 16),
            Text(_error!, style: const TextStyle(color: Colors.redAccent, fontSize: 12)),
          ],

          if (_hasScanned) ...[
            const SizedBox(height: 20),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Row(
                  children: [
                    const Icon(Icons.check_circle_rounded, color: Colors.greenAccent, size: 14),
                    const SizedBox(width: 6),
                    Text(
                      "$_scanned stocks scanned   •   ${_results.length} picks found",
                      style: const TextStyle(color: Colors.white38, fontSize: 11),
                    ),
                  ],
                ),
                // BUG-7 FIX: Clear/Reset button so user can run a fresh scan
                GestureDetector(
                  onTap: () => setState(() {
                    _hasScanned = false;
                    _results = [];
                    _scanned = 0;
                    _error = null;
                  }),
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                    decoration: BoxDecoration(
                      color: Colors.white.withValues(alpha: 0.04),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
                    ),
                    child: const Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.close_rounded, color: Colors.white30, size: 12),
                        SizedBox(width: 4),
                        Text(
                          'CLEAR',
                          style: TextStyle(color: Colors.white30, fontSize: 9, fontWeight: FontWeight.w900, letterSpacing: 1),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            if (_results.isEmpty)
              Container(
                padding: const EdgeInsets.symmetric(vertical: 20),
                alignment: Alignment.center,
                child: Column(
                  children: [
                    const Icon(Icons.search_off_rounded, color: Colors.white24, size: 32),
                    const SizedBox(height: 8),
                    Text(
                      "Koi stock nahi mila range mein (₹${_minPrice.toInt()} - ₹${_maxPrice.toInt()})",
                      textAlign: TextAlign.center,
                      style: const TextStyle(color: Colors.white38, fontSize: 12),
                    ),
                    const SizedBox(height: 4),
                    const Text(
                      "Score filter kam karo ya price limit badhao",
                      style: TextStyle(color: Colors.white24, fontSize: 10),
                    ),
                  ],
                ),
              )
            else
              Column(
                children: _results.map((stock) {
                  final String symbol = stock['symbol'] ?? '';
                  final double ltp = (stock['ltp'] as num?)?.toDouble() ?? 0;
                  final double adxScore = (stock['strict_score'] as num?)?.toDouble() ?? 0;
                  const String engineUsed = '100-Point Whale Score Engine';
                  final String signal = stock['strict_signal'] ?? 'NONE';
                  const String signalTime = 'Today';
                  final String reason = 'Strict Scorecard value: ${stock['strict_score'] ?? 0}/100';
                  
                  final bool isBuySignal = signal.contains('BUY');
                  final Color tileColor  = isBuySignal ? Colors.greenAccent : (signal.contains('SELL') ? Colors.redAccent : Colors.amberAccent);

                  // Score color
                  final Color scoreColor = adxScore >= 80 ? Colors.greenAccent
                      : adxScore >= 65 ? Colors.cyanAccent : Colors.white24;

                  // Find if this stock has an active trade open today
                  final now = DateTime.now();
                  final todayStart = DateTime(now.year, now.month, now.day).millisecondsSinceEpoch;
                  final activeTrade = provider.signals.firstWhere(
                    (sig) {
                      final int ts = sig['timestamp'] is num 
                          ? (sig['timestamp'] as num).toInt() 
                          : (double.tryParse(sig['timestamp']?.toString() ?? '')?.toInt() ?? 0);
                      return (sig['symbol'] == "$symbol-EQ" || sig['symbol'] == symbol) && 
                             sig['status'] != "CLOSED" && 
                             ts >= todayStart;
                    },
                    orElse: () => null,
                  );
                  final bool hasActive = activeTrade != null;
                  final String? tradeSide = hasActive ? activeTrade['signal'] : null;

                  // FIX HIGH-08: Daily lock must check TODAY's date only
                  final closedTodayTrades = provider.signals.where(
                    (sig) {
                      final String sigSym = sig['symbol'] ?? '';
                      final isMatch = sigSym == "$symbol-EQ" || sigSym == symbol;
                      final isClosed = sig['status'] == "CLOSED";
                      final int ts = sig['timestamp'] is num 
                          ? (sig['timestamp'] as num).toInt()
                          : (double.tryParse(sig['timestamp']?.toString() ?? '')?.toInt() ?? 0);
                      final isToday = ts >= todayStart;
                      return isMatch && isClosed && isToday;
                    }
                  ).toList();
                  final bool isLockedToday = closedTodayTrades.isNotEmpty;

                  return Container(
                    margin: const EdgeInsets.only(bottom: 12),
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: tileColor.withValues(alpha: 0.04),
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(color: tileColor.withValues(alpha: 0.15), width: 1),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Container(
                              width: 36,
                              height: 36,
                              decoration: BoxDecoration(
                                color: tileColor.withValues(alpha: 0.1),
                                shape: BoxShape.circle,
                              ),
                              child: Icon(
                                isBuySignal ? Icons.trending_up_rounded : Icons.trending_down_rounded,
                                color: tileColor, size: 18,
                              ),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Row(
                                    children: [
                                      Text(
                                        symbol,
                                        style: const TextStyle(
                                          color: Colors.white,
                                          fontWeight: FontWeight.w900,
                                          fontSize: 14,
                                        ),
                                      ),
                                      const SizedBox(width: 8),
                                      Container(
                                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                        decoration: BoxDecoration(
                                          color: tileColor.withValues(alpha: 0.15),
                                          borderRadius: BorderRadius.circular(6),
                                        ),
                                        child: Text(
                                          signal,
                                          style: TextStyle(color: tileColor, fontSize: 9, fontWeight: FontWeight.w900),
                                        ),
                                      ),
                                      const SizedBox(width: 8),
                                      Container(
                                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                        decoration: BoxDecoration(
                                          color: (stock['strict_score'] == 100)
                                              ? Colors.deepOrangeAccent.withValues(alpha: 0.2)
                                              : Colors.blueGrey.withValues(alpha: 0.2),
                                          borderRadius: BorderRadius.circular(6),
                                          border: Border.all(
                                            color: (stock['strict_score'] == 100)
                                                ? Colors.orangeAccent
                                                : Colors.blueGrey.withValues(alpha: 0.5),
                                          ),
                                        ),
                                        child: Text(
                                          (stock['strict_score'] == 100)
                                              ? "🔥 100% WHALE ${stock['strict_signal']} 🟠"
                                              : "Score: ${stock['strict_score'] ?? '0'}",
                                          style: TextStyle(
                                            color: (stock['strict_score'] == 100)
                                                ? Colors.orangeAccent
                                                : Colors.blueGrey.shade300,
                                            fontSize: 9,
                                            fontWeight: FontWeight.w900,
                                          ),
                                        ),
                                      ),
                                    ],
                                  ),
                                  const Text(
                                    engineUsed,
                                    style: TextStyle(color: Colors.white38, fontSize: 10),
                                  ),
                                  const SizedBox(height: 4),
                                  Text(
                                    "Time: $signalTime | $reason",
                                    style: const TextStyle(color: Colors.white54, fontSize: 9),
                                  ),
                                ],
                              ),
                            ),
                            Column(
                              crossAxisAlignment: CrossAxisAlignment.end,
                              children: [
                                Text(
                                  "₹${ltp.toStringAsFixed(2)}",
                                  style: const TextStyle(
                                    color: Colors.white,
                                    fontWeight: FontWeight.bold,
                                    fontSize: 13,
                                  ),
                                ),
                                Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                                  decoration: BoxDecoration(
                                    color: scoreColor.withValues(alpha: 0.15),
                                    borderRadius: BorderRadius.circular(6),
                                  ),
                                  child: Text(
                                    "ADX: ${adxScore.toStringAsFixed(1)}",
                                    style: TextStyle(
                                      color: scoreColor,
                                      fontWeight: FontWeight.w900,
                                      fontSize: 10,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ),
                        const SizedBox(height: 12),
                        // Quick Action Buttons
                        if (hasActive)
                          Container(
                            width: double.infinity,
                            padding: const EdgeInsets.symmetric(vertical: 8),
                            alignment: Alignment.center,
                            decoration: BoxDecoration(
                              color: (tradeSide == "BUY" ? Colors.greenAccent : Colors.redAccent).withValues(alpha: 0.1),
                              borderRadius: BorderRadius.circular(10),
                              border: Border.all(
                                color: (tradeSide == "BUY" ? Colors.greenAccent : Colors.redAccent).withValues(alpha: 0.3),
                              ),
                            ),
                            child: Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                Icon(
                                  Icons.lock_clock_outlined,
                                  color: tradeSide == "BUY" ? Colors.greenAccent : Colors.redAccent,
                                  size: 14,
                                ),
                                const SizedBox(width: 8),
                                Text(
                                  "ALGO $tradeSide ACTIVE FOR $symbol",
                                  style: TextStyle(
                                    color: tradeSide == "BUY" ? Colors.greenAccent : Colors.redAccent,
                                    fontWeight: FontWeight.w900,
                                    fontSize: 10,
                                    letterSpacing: 1,
                                  ),
                                ),
                              ],
                            ),
                          )
                        else if (isLockedToday)
                          Container(
                            width: double.infinity,
                            padding: const EdgeInsets.symmetric(vertical: 8),
                            alignment: Alignment.center,
                            decoration: BoxDecoration(
                              color: Colors.redAccent.withValues(alpha: 0.1),
                              borderRadius: BorderRadius.circular(10),
                              border: Border.all(
                                color: Colors.redAccent.withValues(alpha: 0.3),
                              ),
                            ),
                            child: const Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                Icon(
                                  Icons.lock_outline_rounded,
                                  color: Colors.redAccent,
                                  size: 14,
                                ),
                                SizedBox(width: 8),
                                Text(
                                  "LOCKED TODAY",
                                  style: TextStyle(
                                    color: Colors.redAccent,
                                    fontWeight: FontWeight.w900,
                                    fontSize: 10,
                                    letterSpacing: 1,
                                  ),
                                ),
                              ],
                            ),
                          )
                        else
                          Row(
                            children: [
                              Expanded(
                                child: GestureDetector(
                                  onTap: () => widget.onExecuteTrade(symbol, "BUY", ltp),
                                  child: Container(
                                    height: 38,
                                    alignment: Alignment.center,
                                    decoration: BoxDecoration(
                                      color: Colors.greenAccent.withValues(alpha: 0.1),
                                      borderRadius: BorderRadius.circular(10),
                                      border: Border.all(color: Colors.greenAccent.withValues(alpha: 0.3)),
                                    ),
                                    child: const Text(
                                      "BUY",
                                      style: TextStyle(
                                        color: Colors.greenAccent,
                                        fontWeight: FontWeight.w900,
                                        fontSize: 11,
                                        letterSpacing: 1,
                                      ),
                                    ),
                                  ),
                                ),
                              ),
                              const SizedBox(width: 10),
                              Expanded(
                                child: GestureDetector(
                                  onTap: () => widget.onExecuteTrade(symbol, "SELL", ltp),
                                  child: Container(
                                    height: 38,
                                    alignment: Alignment.center,
                                    decoration: BoxDecoration(
                                      color: Colors.redAccent.withValues(alpha: 0.1),
                                      borderRadius: BorderRadius.circular(10),
                                      border: Border.all(color: Colors.redAccent.withValues(alpha: 0.3)),
                                    ),
                                    child: const Text(
                                      "SELL",
                                      style: TextStyle(
                                        color: Colors.redAccent,
                                        fontWeight: FontWeight.w900,
                                        fontSize: 11,
                                        letterSpacing: 1,
                                      ),
                                    ),
                                  ),
                                ),
                              ),
                            ],
                          ),
                      ],
                    ),
                  );
                }).toList(),
              ),
          ],
        ],
      ),
    );
  }
}

class _MeshBackground extends StatelessWidget {
  const _MeshBackground();

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        Positioned(
          top: 100,
          right: -100,
          // ignore: deprecated_member_use
          child: _buildOrb(400, Colors.cyanAccent.withOpacity(0.05)),
        ),
        Positioned(
          bottom: 100,
          left: -150,
          // ignore: deprecated_member_use
          child: _buildOrb(500, Colors.purpleAccent.withOpacity(0.05)),
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
}
