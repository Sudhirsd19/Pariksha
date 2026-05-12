import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

class ApiService {
  final String baseUrl = "https://pariksha-production-ca52.up.railway.app";

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
}
