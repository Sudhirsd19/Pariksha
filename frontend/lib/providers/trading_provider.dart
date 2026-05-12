import 'dart:async';
import 'dart:convert';
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
  double get ltp => _ltp;
  String get sentiment => _sentiment;
  double get sentimentScore => _sentimentScore;
  double get dailyLoss => _dailyLoss;
  int get tradesToday => _tradesToday;
  List<dynamic> get signals => _signals;

  Map<String, dynamic>? _analyticsData;
  Map<String, dynamic>? _pnlData;
  List<Map<String, dynamic>> _dailyPnlRecords = [];

  Map<String, dynamic> _systemSettings = {
    'risk_percent': 1.0,
    'take_profit_points': 50,
    'stop_loss_points': 25,
    'max_daily_trades': 5,
    'paper_trading': true,
  };

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
  }

  void _connectWebSocket() {
    try {
      // ws://10.0.2.2:8000/ws/market -> emulator tunnels 10.0.2.2 to host machine
      _wsChannel = WebSocketChannel.connect(
        Uri.parse('wss://pariksha-production-ca52.up.railway.app/ws/market'),
      );
      _wsSubscription = _wsChannel!.stream.listen(
        (data) {
          _wsConnected = true;
          final jsonData = jsonDecode(data as String);
          _ltp = (jsonData['ltp'] as num?)?.toDouble() ?? _ltp;
          _sentiment = jsonData['sentiment'] ?? _sentiment;
          _sentimentScore = (jsonData['sentiment_score'] as num?)?.toDouble() ?? _sentimentScore;
          
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
}
