import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import '../services/api_service.dart';

class TradingProvider with ChangeNotifier {
  static final GlobalKey<ScaffoldMessengerState> scaffoldMessengerKey =
      GlobalKey<ScaffoldMessengerState>();

  bool _isActive = false;
  String? _hardLockReason;
  bool _inKillzone = true;
  int _currentScore = 0;

  double _dailyLoss = 0.0;
  int _tradesToday = 0;
  final List<dynamic> _signals = [];

  double _ltp = 0.0;
  String _sentiment = "Neutral";
  double _sentimentScore = 0.5; // 0.0 to 1.0
  DateTime _lastUpdateTime = DateTime.now();

  bool get isActive => _isActive;
  String? get hardLockReason => _hardLockReason;
  bool get inKillzone => _inKillzone;
  int get currentScore => _currentScore;
  bool get isPaperTrading => _systemSettings['paper_trading'] ?? true;
  String get instrumentType => _systemSettings['instrument_type'] ?? 'FUTURES';
  bool get isFnoTrading => _systemSettings['fno_trading'] ?? true;
  bool get isEquityTrading => _systemSettings['equity_trading'] ?? true;
  double get ltp => _ltp;
  String get sentiment => _sentiment;
  double get sentimentScore => _sentimentScore;
  double get dailyLoss => _dailyLoss;
  int get tradesToday => _tradesToday;
  List<dynamic> get signals => _signals;

  Map<String, dynamic>? _analyticsData;
  Map<String, dynamic>? _pnlData;
  List<Map<String, dynamic>> _dailyPnlRecords = [];
  Map<String, dynamic>? _conditionWinRates;

  Map<String, dynamic> _systemSettings = {};

  Map<String, dynamic>? get analyticsData => _analyticsData;
  Map<String, dynamic>? get pnlData => _pnlData;
  List<Map<String, dynamic>> get dailyPnlRecords => _dailyPnlRecords;
  Map<String, dynamic>? get conditionWinRates => _conditionWinRates;
  Map<String, dynamic> get systemSettings => _systemSettings;

  double get winRate {
    if (_analyticsData == null) return 0.0;
    return (_analyticsData!['win_rate'] as num?)?.toDouble() ?? 0.0;
  }

  double get dailyPnl => todayPnl;

  // Computed getters for daily / weekly / monthly PnL
  double get todayPnl {
    // FIX CRIT-1: Use UTC consistently to avoid timezone-based date mismatches
    final now = DateTime.now().toUtc();
    final todayStart =
        DateTime.utc(now.year, now.month, now.day).millisecondsSinceEpoch;
    final todayEnd = DateTime.utc(now.year, now.month, now.day, 23, 59, 59)
        .millisecondsSinceEpoch;
    double calculatedPnl = 0.0;
    bool hasClosedTrades = false;

    for (final sig in _signals) {
      final int ts = sig['timestamp'] is num
          ? (sig['timestamp'] as num).toInt()
          : (double.tryParse(sig['timestamp']?.toString() ?? '')?.toInt() ?? 0);
      // FIX CRIT-1: Compare with UTC timestamps
      if (ts >= todayStart && ts <= todayEnd && sig['status'] == 'CLOSED') {
        calculatedPnl += (sig['pnl'] as num?)?.toDouble() ?? 0.0;
        hasClosedTrades = true;
      }
    }

    if (hasClosedTrades) {
      return calculatedPnl;
    }

    // FIX CRIT-1: Use UTC for date formatting
    final today = DateTime.now().toUtc().toIso8601String().substring(0, 10);
    final rec = _dailyPnlRecords.firstWhere(
      (r) => r['date'] == today,
      orElse: () => {},
    );
    return (rec['total_pnl'] as num?)?.toDouble() ?? 0.0;
  }

  double get weeklyPnl {
    // FIX CRIT-1: Use UTC consistently
    final now = DateTime.now().toUtc();
    final weekStart = now.subtract(Duration(days: now.weekday - 1));
    final weekStartDate =
        DateTime.utc(weekStart.year, weekStart.month, weekStart.day);
    return _dailyPnlRecords.where((r) {
      final d = DateTime.tryParse(r['date'] ?? '');
      return d != null && !d.isBefore(weekStartDate);
    }).fold(
        0.0, (acc, r) => acc + ((r['total_pnl'] as num?)?.toDouble() ?? 0.0));
  }

  double get monthlyPnl {
    final now = DateTime.now().toUtc();
    final monthKey = '${now.year}-${now.month.toString().padLeft(2, '0')}';
    return _dailyPnlRecords.where((r) => (r['month'] ?? '') == monthKey).fold(
        0.0, (acc, r) => acc + ((r['total_pnl'] as num?)?.toDouble() ?? 0.0));
  }

  final ApiService _apiService = ApiService();
  final FirebaseFirestore _firestore = FirebaseFirestore.instance;
  WebSocketChannel? _wsChannel;
  StreamSubscription? _wsSubscription;
  // FIX CRIT-05: Store all Firestore subscriptions so they can be properly cancelled in dispose()
  final List<StreamSubscription> _firestoreSubscriptions = [];
  // FIX CRIT-2: Track pending reconnection futures to cancel them in dispose()
  final List<Future> _pendingFutures = [];
  bool _isDisposed =
      false; // FIX CRIT-2: Prevent notifyListeners() calls after dispose
  bool _wsConnected = false;
  bool get wsConnected => _wsConnected;

  TradingProvider() {
    _initFirestoreListeners();
    _connectWebSocket();
    _startWatchlistRefreshTimer();
    fetchConditionAnalytics();

    // FIX H-7: Removed unconditional 5-second polling timer that was racing with Firestore listener.
    // fetchLogs() is now only called explicitly when needed (e.g. from LogsScreen sync button).
    // Firestore real-time listener handles live signal updates. SQLite fallback is triggered by
    // Firestore errors (handled in _initFirestoreListeners onError callback).
  }

  bool _wsReconnecting =
      false; // FIX HIGH-03: Guard against simultaneous reconnect attempts

  void _connectWebSocket() {
    if (_wsReconnecting || _isDisposed) {
      return; // FIX HIGH-03: Prevent double-reconnect, FIX CRIT-2: Check disposed
    }
    _wsReconnecting = true;
    try {
      // FIX HIGH-03: Cancel existing subscription before creating new one
      _wsSubscription?.cancel();
      _wsChannel?.sink.close();
      final String wsUrl = _apiService.wsUrl;
      _wsChannel = WebSocketChannel.connect(Uri.parse(wsUrl));
      _wsSubscription = _wsChannel!.stream.listen(
        (data) {
          _wsReconnecting = false;
          _wsConnected = true;
          final jsonData = jsonDecode(data as String);
          _ltp = (jsonData['ltp'] as num?)?.toDouble() ?? _ltp;

          // FIX 1: Read all new real-time fields from WebSocket payload
          if (jsonData['sentiment'] != null) _sentiment = jsonData['sentiment'];
          if (jsonData['sentiment_score'] != null) {
            _sentimentScore = (jsonData['sentiment_score'] as num).toDouble();
          }
          if (jsonData['in_killzone'] != null) {
            _inKillzone = jsonData['in_killzone'];
          }
          if (jsonData['is_active'] != null) {
            _isActive = jsonData['is_active'];
          }
          if (jsonData['trades_today'] != null) {
            _tradesToday = jsonData['trades_today'];
          }
          if (jsonData['daily_loss'] != null) {
            _dailyLoss = (jsonData['daily_loss'] as num).toDouble();
          }

          // Throttle UI updates to 10Hz to save CPU
          final now = DateTime.now();
          if (now.difference(_lastUpdateTime).inMilliseconds > 100) {
            _lastUpdateTime = now;
            if (!_isDisposed) notifyListeners(); // FIX CRIT-2: Check disposed
          }
        },
        onError: (e) {
          _wsConnected = false;
          _wsReconnecting = false;
          if (!_isDisposed) notifyListeners(); // FIX CRIT-2: Check disposed
          if (!_isDisposed) {
            final future = Future.delayed(const Duration(seconds: 3),
                _connectWebSocket); // FIX CRIT-2: Track future
            _pendingFutures.add(future);
          }
        },
        onDone: () {
          _wsConnected = false;
          _wsReconnecting = false;
          if (!_isDisposed) notifyListeners(); // FIX CRIT-2: Check disposed
          if (!_isDisposed) {
            final future = Future.delayed(const Duration(seconds: 3),
                _connectWebSocket); // FIX CRIT-2: Track future
            _pendingFutures.add(future);
          }
        },
      );
    } catch (e) {
      _wsConnected = false;
      _wsReconnecting = false;
      if (!_isDisposed) {
        final future = Future.delayed(const Duration(seconds: 3),
            _connectWebSocket); // FIX CRIT-2: Track future
        _pendingFutures.add(future);
      }
    }
  }

  @override
  void dispose() {
    _isDisposed =
        true; // FIX CRIT-2: Mark as disposed BEFORE cancelling to prevent new calls
    _wsSubscription?.cancel();
    _wsChannel?.sink.close();
    _watchlistRefreshTimer?.cancel();
    // FIX CRIT-05: Cancel all Firestore listeners to prevent memory leaks and ghost notifyListeners() calls
    for (final sub in _firestoreSubscriptions) {
      sub.cancel();
    }
    // FIX CRIT-2: Clear pending futures (note: they may still execute but _isDisposed guards notifyListeners)
    _pendingFutures.clear();
    try {
      super.dispose();
    } catch (e) {
      debugPrint('Error in dispose: $e');
    }
  }

  void _initFirestoreListeners() {
    // Safety check for Web/Initialization failures
    try {
      if (FirebaseFirestore.instance.app.name.isEmpty) return;
    } catch (e) {
      debugPrint("Firestore not initialized, skipping listeners: $e");
      return;
    }

    // Listen to system status
    _firestoreSubscriptions.add(
      _firestore
          .collection('quantum_system')
          .doc('live_status')
          .snapshots()
          .listen((doc) {
        if (doc.exists) {
          final data = doc.data()!;
          _isActive = data['is_active'] ?? _isActive;
          _dailyLoss = (data['daily_loss'] as num?)?.toDouble() ?? _dailyLoss;
          _tradesToday = data['trades_today'] ?? _tradesToday;
          _hardLockReason = data['hard_lock_reason'];
          _inKillzone = data['in_killzone'] ?? true;
          _currentScore = data['current_score'] ?? 0;
          notifyListeners();
        }
      }, onError: (e) => debugPrint('Firestore live_status error: $e')),
    );

    // Listen to PnL & Analytics
    _firestoreSubscriptions.add(
      _firestore
          .collection('quantum_system')
          .doc('pnl_data')
          .snapshots()
          .listen((doc) {
        if (doc.exists) {
          final data = doc.data()!;
          _pnlData = data;
          _analyticsData = data; // Both use the same doc now
          notifyListeners();
        }
      }, onError: (e) => debugPrint('Firestore pnl_data error: $e')),
    );

    // Listen to Settings
    _firestoreSubscriptions.add(
      _firestore
          .collection('quantum_system')
          .doc('settings')
          .snapshots()
          .listen((doc) {
        if (doc.exists) {
          _systemSettings = doc.data()!;
          notifyListeners();
        }
      }, onError: (e) => debugPrint('Firestore settings error: $e')),
    );

    // Listen to trades
    _firestoreSubscriptions.add(
      _firestore
          .collection('quantum_trades')
          .orderBy('timestamp', descending: true)
          .limit(50)
          .snapshots()
          .listen((snapshot) {
        // FIX CRIT-3: Make signals update atomic to prevent UI reading empty list
        final newSignals = snapshot.docs.map((doc) {
          // FIX H-6: Include document ID in signal data (was missing, causing sig['id'] == null)
          final data = Map<String, dynamic>.from(doc.data());
          data['id'] = doc.id;
          return data as dynamic;
        }).toList();
        // CRIT-3: Atomic assignment instead of clear+addAll
        _signals.clear();
        _signals.addAll(newSignals);
        if (!_isDisposed) notifyListeners(); // FIX CRIT-2: Check disposed
      }, onError: (e) {
        debugPrint(
            'Firestore quantum_trades error: $e — falling back to HTTP polling');
        // FIX H-7: Only poll from API when Firestore fails
        if (!_isDisposed) fetchLogs();
      }),
    );

    // Listen to daily PnL records (last 90 days covers daily/weekly/monthly)
    final ninetyDaysAgo =
        DateTime.now().toUtc().subtract(const Duration(days: 90));
    final cutoff =
        '${ninetyDaysAgo.year}-${ninetyDaysAgo.month.toString().padLeft(2, '0')}-${ninetyDaysAgo.day.toString().padLeft(2, '0')}';

    _firestoreSubscriptions.add(
      _firestore
          .collection('pnl_daily')
          .where('date', isGreaterThanOrEqualTo: cutoff)
          .orderBy('date', descending: true)
          .snapshots()
          .listen((snapshot) {
        _dailyPnlRecords = snapshot.docs.map((d) => d.data()).toList();
        notifyListeners();
      }, onError: (e) => debugPrint('Firestore pnl_daily error: $e')),
    );

    // Listen to Watchlist
    _firestoreSubscriptions.add(
      _firestore
          .collection('quantum_system')
          .doc('watchlist')
          .snapshots()
          .listen((doc) {
        if (doc.exists) {
          final data = doc.data();
          if (data != null && data['items'] != null) {
            _watchlist = List<Map<String, dynamic>>.from(
              (data['items'] as List<dynamic>)
                  .map((e) => Map<String, dynamic>.from(e as Map)),
            );
          } else {
            _watchlist = [];
          }
          notifyListeners();
        } else {
          _watchlist = [];
          notifyListeners();
        }
      }, onError: (e) => debugPrint('Firestore watchlist error: $e')),
    );
  }

  Future<void> fetchStatus() async {
    // LTP now comes via WebSocket. API is only fallback for initial load.
    if (_ltp == 0.0) {
      try {
        final status = await _apiService.getStatus();
        _ltp = (status['ltp'] as num?)?.toDouble() ?? 0.0;
        _sentiment = status['sentiment'] ?? 'Neutral';
        _sentimentScore =
            (status['sentiment_score'] as num?)?.toDouble() ?? 0.5;
        _hardLockReason = status['hard_lock_reason'];
        _inKillzone = status['in_killzone'] ?? true;
        _currentScore = status['current_score'] ?? 0;
        notifyListeners();
      } catch (_) {}
    }
  }

  Future<void> toggleTrading(bool active) async {
    if (_isDisposed) return; // FIX: Prevent operations on disposed provider
    _isActive = active;
    if (!_isDisposed) notifyListeners();

    final success = await _apiService.toggleTrading(active);
    if (!success) {
      _isActive = !active;
      if (!_isDisposed) notifyListeners();
      scaffoldMessengerKey.currentState?.showSnackBar(
        const SnackBar(
            content: Text("Backend Connection Failed! Run python main.py")),
      );
    }
  }

  Future<void> fetchLogs() async {
    final logs = await _apiService.getLogs();
    _signals.clear();
    _signals.addAll(logs);
    notifyListeners();
  }

  Future<void> fetchAnalyticsAndPnl() async {
    // Now handled by Firestore real-time listener (_initFirestoreListeners)
    // Kept empty to avoid breaking existing UI calls during transition
  }

  Future<void> fetchConditionAnalytics() async {
    final res = await _apiService.getAnalytics();
    if (res != null && res.containsKey('condition_win_rates')) {
      _conditionWinRates = res['condition_win_rates'] as Map<String, dynamic>;
      notifyListeners();
    }
  }

  Future<void> emergencySquareOff() async {
    final success = await _apiService.squareOff();
    if (success) {
      _isActive = false;
      notifyListeners();
      scaffoldMessengerKey.currentState?.showSnackBar(
        const SnackBar(
            content: Text("Emergency Square Off Successful!"),
            backgroundColor: Colors.red),
      );
    } else {
      scaffoldMessengerKey.currentState?.showSnackBar(
        const SnackBar(
            content: Text("Square Off Failed! Check Broker Connection.")),
      );
    }
  }

  Future<void> updateSettings(Map<String, dynamic> newSettings) async {
    if (_isDisposed) return; // FIX: Prevent operations on disposed provider
    try {
      await _firestore
          .collection('quantum_system')
          .doc('settings')
          .set(newSettings, SetOptions(merge: true));
      if (!_isDisposed) notifyListeners();
    } catch (e) {
      debugPrint("Error updating settings: $e");
    }
  }

  // --- WATCHLIST STATE ---
  List<Map<String, dynamic>> _watchlist = [];
  List<Map<String, dynamic>> get watchlist => _watchlist;
  Timer? _watchlistRefreshTimer;
  bool _isRefreshingWatchlist = false;
  bool get isRefreshingWatchlist => _isRefreshingWatchlist;

  // --- STOCK SCANNER INTEGRATION ---
  Map<String, dynamic>? _scannedStockData;
  bool _isScanning = false;

  Map<String, dynamic>? get scannedStockData => _scannedStockData;
  bool get isScanning => _isScanning;

  Future<void> scanStock(String symbol, {double? ltp}) async {
    _isScanning = true;
    _scannedStockData = null;
    notifyListeners();

    try {
      final res = await _apiService.analyzeStock(symbol, ltp: ltp);
      if (res != null) {
        _scannedStockData = res;
      } else {
        _scannedStockData = {
          "status": "error",
          "message": "Failed to analyze stock. Please try again."
        };
      }
    } catch (e) {
      _scannedStockData = {
        "status": "error",
        "message": "Error contacting backend server: $e"
      };
    } finally {
      _isScanning = false;
      notifyListeners();
    }
  }

  void clearScannedStock() {
    _scannedStockData = null;
    notifyListeners();
  }

  Future<List<Map<String, dynamic>>> searchStocks(String query) async {
    if (query.isEmpty) return [];
    try {
      final results = await _apiService.searchStocks(query);
      return results.map((e) => Map<String, dynamic>.from(e as Map)).toList();
    } catch (_) {
      return [];
    }
  }

  Future<Map<String, dynamic>?> smartScreener(double maxPrice,
      {int minScore = 70}) async {
    try {
      return await _apiService.smartScreener(maxPrice, minScore: minScore);
    } catch (_) {
      return null;
    }
  }

  Future<bool> executeStockTrade(String symbol, String side, int qty, {double? ltp}) async {
    try {
      final res = await _apiService.executeStockTrade(symbol, side, qty, ltp: ltp);
      if (res != null && res['status'] == 'success') {
        scaffoldMessengerKey.currentState?.showSnackBar(
          SnackBar(
            content: Text("Algo Trade Executed for $symbol!"),
            backgroundColor: Colors.green,
          ),
        );
        await fetchLogs();
        return true;
      } else {
        final msg = res?['message'] ?? "Execution failed.";
        scaffoldMessengerKey.currentState?.showSnackBar(
          SnackBar(
            content: Text("Trade Failed: $msg"),
            backgroundColor: Colors.red,
          ),
        );
      }
    } catch (e) {
      scaffoldMessengerKey.currentState?.showSnackBar(
        SnackBar(
          content: Text("Error executing trade: $e"),
          backgroundColor: Colors.red,
        ),
      );
    }
    return false;
  }

  // --- WATCHLIST METHODS ---
  Future<void> addToWatchlist(Map<String, dynamic> stockData) async {
    if (_isDisposed) return; // FIX: Prevent operations on disposed provider
    try {
      final symbol = stockData['symbol'] as String;

      // FIX HIGH-3: Use atomic Firestore read to prevent race condition
      final docRef = _firestore.collection('quantum_system').doc('watchlist');
      final doc = await docRef.get();
      final currentList = doc.exists && doc.data() != null
          ? List<Map<String, dynamic>>.from(
              (doc.data()!['items'] as List<dynamic>)
                  .map((e) => Map<String, dynamic>.from(e as Map)))
          : [];

      // Check again after read (TOCTOU prevention)
      if (currentList.any((item) => item['symbol'] == symbol)) return;

      currentList.add({
        "symbol": symbol,
        "name": stockData['symbol'] ?? symbol,
        "ltp": stockData['ltp'] ?? 0.0,
        "score": stockData['score'] ?? 0,
        "actionable": stockData['actionable'] ?? false,
        "recommendation": stockData['recommendation'] ?? "NEUTRAL",
        "timestamp": DateTime.now().millisecondsSinceEpoch,
      });

      await docRef.set({"items": currentList});
      scaffoldMessengerKey.currentState?.showSnackBar(
        SnackBar(
          content: Text("$symbol added to Watchlist!"),
          backgroundColor: Colors.green,
          duration: const Duration(seconds: 2),
        ),
      );
    } catch (e) {
      debugPrint("Error adding to watchlist: $e");
    }
  }

  Future<void> removeFromWatchlist(String symbol) async {
    if (_isDisposed) return; // FIX: Prevent operations on disposed provider
    try {
      // FIX HIGH-3: Use atomic Firestore read to prevent race condition
      final docRef = _firestore.collection('quantum_system').doc('watchlist');
      final doc = await docRef.get();
      final currentList = doc.exists && doc.data() != null
          ? List<Map<String, dynamic>>.from(
              (doc.data()!['items'] as List<dynamic>)
                  .map((e) => Map<String, dynamic>.from(e as Map)))
          : [];

      final updatedList =
          currentList.where((item) => item['symbol'] != symbol).toList();
      await docRef.set({"items": updatedList});
      scaffoldMessengerKey.currentState?.showSnackBar(
        SnackBar(
          content: Text("$symbol removed from Watchlist!"),
          backgroundColor: Colors.blueGrey,
          duration: const Duration(seconds: 2),
        ),
      );
    } catch (e) {
      debugPrint("Error removing from watchlist: $e");
    }
  }

  void _startWatchlistRefreshTimer() {
    if (_isDisposed) return; // FIX: Don't start timer if already disposed
    _watchlistRefreshTimer =
        Timer.periodic(const Duration(seconds: 60), (timer) {
      if (!_isDisposed) refreshWatchlist();
    });
  }

  Future<void> refreshWatchlist() async {
    if (_isDisposed || _watchlist.isEmpty || _isRefreshingWatchlist) {
      return; // FIX: Check disposed
    }
    _isRefreshingWatchlist = true;
    if (!_isDisposed) notifyListeners();

    try {
      final List<Map<String, dynamic>> updatedList =
          List<Map<String, dynamic>>.from(_watchlist);
      bool changesMade = false;

      // FIX M-8: Was using Future.wait() which fired all requests simultaneously.
      // AngelOne rate limit is 3 req/sec; each analyzeStock() makes 2 API calls.
      // Now processes sequentially with a 600ms gap to stay safely under the limit.
      for (final item in updatedList) {
        final symbol = item['symbol'];
        if (symbol == null) continue;
        try {
          final double currentLtp = (item['ltp'] as num?)?.toDouble() ?? 0.0;
          final res = await _apiService.analyzeStock(symbol, ltp: currentLtp);
          if (res != null && res['status'] == 'success') {
            final double newLtp = (res['ltp'] as num?)?.toDouble() ?? 0.0;
            final int newScore = res['score'] ?? 0;
            final bool actionable = res['actionable'] ?? false;

            String recommendation = res['recommendation'] ?? "NEUTRAL";

            final idx = updatedList.indexWhere((i) => i['symbol'] == symbol);
            if (idx != -1) {
              final oldItem = updatedList[idx];
              if (oldItem['ltp'] != newLtp ||
                  oldItem['score'] != newScore ||
                  oldItem['recommendation'] != recommendation) {
                updatedList[idx] = {
                  ...oldItem,
                  "ltp": newLtp,
                  "score": newScore,
                  "recommendation": recommendation,
                  "actionable": actionable,
                  "timestamp": DateTime.now().millisecondsSinceEpoch,
                };
                changesMade = true;
              }
            }
          }
        } catch (e) {
          debugPrint("Error fetching refresh for $symbol: $e");
        }
        // Delay between stocks to respect AngelOne 3 req/sec rate limit
        await Future.delayed(const Duration(milliseconds: 600));
      }

      if (changesMade) {
        await _firestore
            .collection('quantum_system')
            .doc('watchlist')
            .set({"items": updatedList});
      }
    } catch (e) {
      debugPrint("Error refreshing watchlist: $e");
    } finally {
      _isRefreshingWatchlist = false;
      notifyListeners();
    }
  }
}
