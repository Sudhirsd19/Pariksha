import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

class ApiService {
  static String _resolvedBaseUrl = "https://pariksha-backend-lar4.onrender.com";
  
  String get baseUrl => _resolvedBaseUrl;

  String get wsUrl {
    if (baseUrl.startsWith("https://")) {
      return "wss://${baseUrl.replaceFirst("https://", "")}/ws/market";
    } else {
      return "ws://${baseUrl.replaceFirst("http://", "")}/ws/market";
    }
  }

  static Future<void> init() async {
    if (kDebugMode) {
      try {
        final uri = Uri.parse("http://10.0.2.2:8000/status");
        final response = await http.get(uri).timeout(const Duration(milliseconds: 500));
        if (response.statusCode == 200) {
          _resolvedBaseUrl = "http://10.0.2.2:8000";
          debugPrint("[ApiService] Detected local emulator backend at $_resolvedBaseUrl");
          return;
        }
      } catch (e) {
        debugPrint("[ApiService] Local emulator backend not reachable. Falling back to production Railway URL. Error: $e");
      }
    }
    _resolvedBaseUrl = "https://pariksha-backend-lar4.onrender.com";
    debugPrint("[ApiService] Using production backend at $_resolvedBaseUrl");
  }

  Future<Map<String, dynamic>> getStatus() async {
    try {
      final response = await http.get(Uri.parse('$baseUrl/status'));
      if (response.statusCode == 200) {
        return json.decode(response.body);
      }
    } catch (e) {
      debugPrint("Error fetching status: $e");
    }
    return {"is_active": false, "daily_loss": 0.0, "trades_today": 0};
  }

  Future<bool> toggleTrading(bool active) async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/toggle-trading?active=$active'),
      );
      return response.statusCode == 200;
    } catch (e) {
      debugPrint("Error toggling trading: $e");
    }
    return false;
  }

  Future<List<dynamic>> getLogs() async {
    try {
      final response = await http.get(Uri.parse('$baseUrl/logs'));
      if (response.statusCode == 200) {
        return json.decode(response.body);
      }
    } catch (e) {
      debugPrint("Error fetching logs: $e");
    }
    return [];
  }

  Future<Map<String, dynamic>?> getAnalytics() async {
    try {
      final response = await http.get(Uri.parse('$baseUrl/analytics'));
      if (response.statusCode == 200) {
        return json.decode(response.body);
      }
    } catch (e) {
      debugPrint("Error fetching analytics: $e");
    }
    return null;
  }

  Future<Map<String, dynamic>?> getPnl() async {
    try {
      final response = await http.get(Uri.parse('$baseUrl/pnl'));
      if (response.statusCode == 200) {
        return json.decode(response.body);
      }
    } catch (e) {
      debugPrint("Error fetching pnl: $e");
    }
    return null;
  }

  Future<bool> squareOff() async {
    try {
      final response = await http.post(Uri.parse('$baseUrl/square-off'));
      return response.statusCode == 200;
    } catch (e) {
      debugPrint("Error during square off: $e");
    }
    return false;
  }

  Future<List<dynamic>> searchStocks(String query) async {
    try {
      final response = await http.get(Uri.parse('$baseUrl/search-stocks?q=${Uri.encodeComponent(query)}'));
      if (response.statusCode == 200) {
        return json.decode(response.body);
      }
    } catch (e) {
      debugPrint("Error searching stocks: $e");
    }
    return [];
  }

  Future<Map<String, dynamic>?> smartScreener(double maxPrice, {int minScore = 70}) async {
    try {
      final response = await http.get(
        Uri.parse('$baseUrl/api/scanner/bulk-scan?max_price=$maxPrice'),
      ).timeout(const Duration(seconds: 180));
      if (response.statusCode == 200) {
        return json.decode(response.body);
      }
    } catch (e) {
      debugPrint("Error in smart screener: $e");
    }
    return null;
  }

  Future<Map<String, dynamic>?> analyzeStock(String symbol, {double? ltp}) async {
    try {
      final url = ltp != null && ltp > 0
          ? '$baseUrl/analyze-stock?symbol=$symbol&ltp=$ltp'
          : '$baseUrl/analyze-stock?symbol=$symbol';
      final response = await http.get(Uri.parse(url));
      if (response.statusCode == 200) {
        return json.decode(response.body);
      }
    } catch (e) {
      debugPrint("Error analyzing stock: $e");
    }
    return null;
  }

  Future<Map<String, dynamic>?> executeStockTrade(String symbol, String side, int qty, {double? ltp}) async {
    try {
      final url = ltp != null 
          ? '$baseUrl/execute-stock-trade?symbol=$symbol&side=$side&qty=$qty&ltp=$ltp'
          : '$baseUrl/execute-stock-trade?symbol=$symbol&side=$side&qty=$qty';
      final response = await http.post(Uri.parse(url));
      if (response.statusCode == 200) {
        return json.decode(response.body);
      }
    } catch (e) {
      debugPrint("Error executing stock trade: $e");
    }
    return null;
  }
}
