import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import '../services/api_service.dart';

class TradingProvider with ChangeNotifier {
  static final GlobalKey<ScaffoldMessengerState> scaffoldMessengerKey = GlobalKey<ScaffoldMessengerState>();

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

  Map<String, dynamic> _systemSettings = {};

  Map<String, dynamic>? get analyticsData => _analyticsData;
  Map<String, dynamic>? get pnlData => _pnlData;
  List<Map<String, dynamic>> get dailyPnlRecords => _dailyPnlRecords;
  Map<String, dynamic> get systemSettings => _systemSettings;

  double get winRate {
    if (_analyticsData == null) return 0.0;
    return (_analyticsData!['win_rate'] as num?)?.toDouble() ?? 0.0;
  }

  double get dailyPnl => todayPnl;

  // Computed getters for daily / weekly / monthly PnL
  double get todayPnl {
    final today = DateTime.now().toUtc().toIso8601String().substring(0, 10);
    final rec = _dailyPnlRecords.firstWhere(
      (r) => r['date'] == today,
      orElse: () => {},
    );
    return (rec['total_pnl'] as num?)?.toDouble() ?? 0.0;
  }

  double get weeklyPnl {
    final now = DateTime.now().toUtc();
    final weekStart = now.subtract(Duration(days: now.weekday - 1));
    return _dailyPnlRecords
        .where((r) {
          final d = DateTime.tryParse(r['date'] ?? '');
          return d != null && !d.isBefore(DateTime(weekStart.year, weekStart.month, weekStart.day));
        })
        .fold(0.0, (acc, r) => acc + ((r['total_pnl'] as num?)?.toDouble() ?? 0.0));
  }

  double get monthlyPnl {
    final now = DateTime.now().toUtc();
    final monthKey = '${now.year}-${now.month.toString().padLeft(2, '0')}';
    return _dailyPnlRecords
        .where((r) => (r['month'] ?? '') == monthKey)
        .fold(0.0, (acc, r) => acc + ((r['total_pnl'] as num?)?.toDouble() ?? 0.0));
  }

  final ApiService _apiService = ApiService();
  final FirebaseFirestore _firestore = FirebaseFirestore.instance;
  WebSocketChannel? _wsChannel;
  StreamSubscription? _wsSubscription;
  bool _wsConnected = false;
  bool get wsConnected => _wsConnected;

  TradingProvider() {
    _initFirestoreListeners();
    _connectWebSocket();
    _startWatchlistRefreshTimer();
  }

  void _connectWebSocket() {
    try {
      // ws://10.0.2.2:8000/ws/market -> emulator tunnels 10.0.2.2 to host machine
      _wsChannel = WebSocketChannel.connect(
        Uri.parse(kDebugMode
            ? 'ws://10.0.2.2:8000/ws/market'
            : 'wss://pariksha-production-ca52.up.railway.app/ws/market'),
      );
      _wsSubscription = _wsChannel!.stream.listen(
        (data) {
          _wsConnected = true;
          final jsonData = jsonDecode(data as String);
          _ltp = (jsonData['ltp'] as num?)?.toDouble() ?? _ltp;
          
          // FIX 1: Read all new real-time fields from WebSocket payload
          if (jsonData['sentiment'] != null) _sentiment = jsonData['sentiment'];
          if (jsonData['sentiment_score'] != null) {
            _sentimentScore = (jsonData['sentiment_score'] as num).toDouble();
          }
          if (jsonData['in_killzone'] != null) _inKillzone = jsonData['in_killzone'];
          if (jsonData['is_active'] != null) _isActive = jsonData['is_active'];
          if (jsonData['trades_today'] != null) _tradesToday = jsonData['trades_today'];
          if (jsonData['daily_loss'] != null) {
            _dailyLoss = (jsonData['daily_loss'] as num).toDouble();
          }
          
          // Throttle UI updates to 10Hz to save CPU
          final now = DateTime.now();
          if (now.difference(_lastUpdateTime).inMilliseconds > 100) {
            _lastUpdateTime = now;
            notifyListeners();
          }
        },
        onError: (e) {
          _wsConnected = false;
          notifyListeners();
          Future.delayed(const Duration(seconds: 3), _connectWebSocket);
        },
        onDone: () {
          _wsConnected = false;
          notifyListeners();
          Future.delayed(const Duration(seconds: 3), _connectWebSocket);
        },
      );
    } catch (e) {
      _wsConnected = false;
      Future.delayed(const Duration(seconds: 3), _connectWebSocket);
    }
  }

  @override
  void dispose() {
    _wsSubscription?.cancel();
    _wsChannel?.sink.close();
    _watchlistRefreshTimer?.cancel();
    super.dispose();
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
    _firestore.collection('quantum_system').doc('live_status').snapshots().listen((doc) {
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
    });

    // Listen to PnL & Analytics
    _firestore.collection('quantum_system').doc('pnl_data').snapshots().listen((doc) {
      if (doc.exists) {
        final data = doc.data()!;
        _pnlData = data;
        _analyticsData = data; // Both use the same doc now
        notifyListeners();
      }
    });

    // Listen to Settings
    _firestore.collection('quantum_system').doc('settings').snapshots().listen((doc) {
      if (doc.exists) {
        _systemSettings = doc.data()!;
        notifyListeners();
      }
    });

    // Listen to trades
    _firestore.collection('quantum_trades').orderBy('timestamp', descending: true).limit(50).snapshots().listen((snapshot) {
      _signals.clear();
      for (var doc in snapshot.docs) {
        _signals.add(doc.data());
      }
      notifyListeners();
    });

    // Listen to daily PnL records (last 90 days covers daily/weekly/monthly)
    final ninetyDaysAgo = DateTime.now().toUtc().subtract(const Duration(days: 90));
    final cutoff = '${ninetyDaysAgo.year}-${ninetyDaysAgo.month.toString().padLeft(2,'0')}-${ninetyDaysAgo.day.toString().padLeft(2,'0')}';

    _firestore
        .collection('pnl_daily')
        .where('date', isGreaterThanOrEqualTo: cutoff)
        .orderBy('date', descending: true)
        .snapshots()
        .listen((snapshot) {
      _dailyPnlRecords = snapshot.docs.map((d) => d.data()).toList();
      notifyListeners();
    });

    // Listen to Watchlist
    _firestore.collection('quantum_system').doc('watchlist').snapshots().listen((doc) {
      if (doc.exists) {
        final data = doc.data();
        if (data != null && data['items'] != null) {
          _watchlist = List<Map<String, dynamic>>.from(
            (data['items'] as List<dynamic>).map((e) => Map<String, dynamic>.from(e as Map)),
          );
        } else {
          _watchlist = [];
        }
        notifyListeners();
      } else {
        _watchlist = [];
        notifyListeners();
      }
    });
  }

  Future<void> fetchStatus() async {
    // LTP now comes via WebSocket. API is only fallback for initial load.
    if (_ltp == 0.0) {
      try {
        final status = await _apiService.getStatus();
        _ltp = (status['ltp'] as num?)?.toDouble() ?? 0.0;
        _sentiment = status['sentiment'] ?? 'Neutral';
        _sentimentScore = (status['sentiment_score'] as num?)?.toDouble() ?? 0.5;
        _hardLockReason = status['hard_lock_reason'];
        _inKillzone = status['in_killzone'] ?? true;
        _currentScore = status['current_score'] ?? 0;
        notifyListeners();
      } catch (_) {}
    }
  }

  Future<void> toggleTrading(bool active) async {
    _isActive = active;
    notifyListeners();
    
    final success = await _apiService.toggleTrading(active);
    if (!success) {
      _isActive = !active;
      notifyListeners();
      scaffoldMessengerKey.currentState?.showSnackBar(
        const SnackBar(content: Text("Backend Connection Failed! Run python main.py")),
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

  Future<void> emergencySquareOff() async {
    final success = await _apiService.squareOff();
    if (success) {
      _isActive = false;
      notifyListeners();
      scaffoldMessengerKey.currentState?.showSnackBar(
        const SnackBar(content: Text("Emergency Square Off Successful!"), backgroundColor: Colors.red),
      );
    } else {
      scaffoldMessengerKey.currentState?.showSnackBar(
        const SnackBar(content: Text("Square Off Failed! Check Broker Connection.")),
      );
    }
  }

  Future<void> updateSettings(Map<String, dynamic> newSettings) async {
    try {
      await _firestore.collection('quantum_system').doc('settings').set(newSettings, SetOptions(merge: true));
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

  Future<void> scanStock(String symbol) async {
    _isScanning = true;
    _scannedStockData = null;
    notifyListeners();

    try {
      final res = await _apiService.analyzeStock(symbol);
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

  Future<List<Map<String, dynamic>>> searchStocks(String query) async {
    if (query.isEmpty) return [];
    try {
      final results = await _apiService.searchStocks(query);
      return results.map((e) => Map<String, dynamic>.from(e as Map)).toList();
    } catch (_) {
      return [];
    }
  }

  Future<bool> executeStockTrade(String symbol, String side) async {
    try {
      final res = await _apiService.executeStockTrade(symbol, side);
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
    try {
      final symbol = stockData['symbol'] as String;
      
      final exists = _watchlist.any((item) => item['symbol'] == symbol);
      if (exists) return;

      final updatedList = List<Map<String, dynamic>>.from(_watchlist);
      updatedList.add({
        "symbol": symbol,
        "name": stockData['symbol'] ?? symbol,
        "ltp": stockData['ltp'] ?? 0.0,
        "score": stockData['score'] ?? 0,
        "actionable": stockData['actionable'] ?? false,
        "recommendation": (stockData['score'] ?? 0) >= 70 ? "BUY" : ((stockData['score'] ?? 0) <= 40 ? "SELL" : "NEUTRAL"),
        "timestamp": DateTime.now().millisecondsSinceEpoch,
      });

      await _firestore.collection('quantum_system').doc('watchlist').set({"items": updatedList});
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
    try {
      final updatedList = _watchlist.where((item) => item['symbol'] != symbol).toList();
      await _firestore.collection('quantum_system').doc('watchlist').set({"items": updatedList});
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
    _watchlistRefreshTimer = Timer.periodic(const Duration(seconds: 30), (timer) {
      refreshWatchlist();
    });
  }

  Future<void> refreshWatchlist() async {
    if (_watchlist.isEmpty || _isRefreshingWatchlist) return;
    _isRefreshingWatchlist = true;
    notifyListeners();

    try {
      final List<Map<String, dynamic>> updatedList = List<Map<String, dynamic>>.from(_watchlist);
      bool changesMade = false;

      final futures = updatedList.map((item) async {
        final symbol = item['symbol'];
        if (symbol == null) return null;
        try {
          final res = await _apiService.analyzeStock(symbol);
          return {"symbol": symbol, "res": res};
        } catch (e) {
          debugPrint("Error fetching refresh for $symbol: $e");
          return null;
        }
      }).toList();

      final results = await Future.wait(futures);

      for (final result in results) {
        if (result == null) continue;
        final String symbol = result['symbol'] as String;
        final res = result['res'];
        if (res != null && res['status'] == 'success') {
          final double newLtp = (res['ltp'] as num?)?.toDouble() ?? 0.0;
          final int newScore = res['score'] ?? 0;
          final bool actionable = res['actionable'] ?? false;
          final String htfTrend = res['htf_trend'] ?? "NEUTRAL";

          String recommendation = "NEUTRAL";
          if (newScore >= 70) {
            recommendation = htfTrend == "Bullish" ? "BUY" : "SELL";
          }

          final idx = updatedList.indexWhere((item) => item['symbol'] == symbol);
          if (idx != -1) {
            final oldItem = updatedList[idx];
            if (oldItem['ltp'] != newLtp || oldItem['score'] != newScore || oldItem['recommendation'] != recommendation) {
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
      }

      if (changesMade) {
        await _firestore.collection('quantum_system').doc('watchlist').set({"items": updatedList});
      }
    } catch (e) {
      debugPrint("Error refreshing watchlist: $e");
    } finally {
      _isRefreshingWatchlist = false;
      notifyListeners();
    }
  }
}
