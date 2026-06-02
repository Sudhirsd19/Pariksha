import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import 'dart:async';

void main() {
  runApp(const QuantumIndexApp());
}

class QuantumIndexApp extends StatelessWidget {
  const QuantumIndexApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Quantum Index Control Panel',
      theme: ThemeData(
        brightness: Brightness.dark,
        primarySwatch: Colors.blue,
        scaffoldBackgroundColor: const Color(0xFF121212),
        cardColor: const Color(0xFF1E1E1E),
        colorScheme: const ColorScheme.dark(
          primary: Colors.blueAccent,
          secondary: Colors.tealAccent,
        ),
      ),
      home: const DashboardScreen(),
    );
  }
}

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  // Replace 10.0.2.2 with your backend IP if running on physical device
  final String backendUrl = 'http://10.0.2.2:8000';
  
  bool isTradingActive = false;
  bool useTimeRestrictions = true;
  String instrumentType = "FUTURES";
  Map<String, dynamic> systemStatus = {};
  Timer? _statusTimer;

  @override
  void initState() {
    super.initState();
    _fetchSettings();
    _fetchStatus();
    // Poll status every 5 seconds
    _statusTimer = Timer.periodic(const Duration(seconds: 5), (timer) {
      _fetchStatus();
    });
  }

  @override
  void dispose() {
    _statusTimer?.cancel();
    super.dispose();
  }

  Future<void> _fetchSettings() async {
    try {
      final response = await http.get(Uri.parse('$backendUrl/settings'));
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        setState(() {
          useTimeRestrictions = data['use_time_restrictions'] ?? true;
          instrumentType = data['instrument_type'] ?? "FUTURES";
        });
      }
    } catch (e) {
      debugPrint('Error fetching settings: $e');
    }
  }

  Future<void> _fetchStatus() async {
    try {
      final response = await http.get(Uri.parse('$backendUrl/status'));
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        setState(() {
          systemStatus = data;
          isTradingActive = data['trading_active'] ?? false;
        });
      }
    } catch (e) {
      debugPrint('Error fetching status: $e');
    }
  }

  Future<void> _toggleTrading(bool value) async {
    try {
      final response = await http.post(Uri.parse('$backendUrl/toggle-trading?active=$value'));
      if (response.statusCode == 200) {
        setState(() {
          isTradingActive = value;
        });
      }
    } catch (e) {
      debugPrint('Error toggling trading: $e');
    }
  }

  Future<void> _updateSettings(String key, dynamic value) async {
    // First fetch current, then merge
    try {
      final getRes = await http.get(Uri.parse('$backendUrl/settings'));
      Map<String, dynamic> current = {};
      if (getRes.statusCode == 200) {
        current = jsonDecode(getRes.body);
      }
      
      current[key] = value;
      
      final postRes = await http.post(
        Uri.parse('$backendUrl/settings'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(current),
      );
      
      if (postRes.statusCode == 200) {
        setState(() {
          if (key == 'use_time_restrictions') useTimeRestrictions = value;
          if (key == 'instrument_type') instrumentType = value;
        });
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Setting updated: $key = $value')),
        );
      }
    } catch (e) {
      debugPrint('Error updating settings: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Quantum Index Control'),
        backgroundColor: Theme.of(context).cardColor,
        elevation: 0,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _buildStatusCard(),
            const SizedBox(height: 24),
            Text(
              'CONFIGURATION',
              style: TextStyle(
                color: Colors.grey[400],
                fontWeight: FontWeight.bold,
                letterSpacing: 1.2,
              ),
            ),
            const SizedBox(height: 16),
            _buildSettingsCard(),
          ],
        ),
      ),
    );
  }

  Widget _buildStatusCard() {
    final todayStats = systemStatus['today_stats'] ?? {};
    final pnl = todayStats['daily_loss'] ?? 0.0;
    final isLoss = pnl < 0;

    return Card(
      elevation: 4,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: Padding(
        padding: const EdgeInsets.all(20.0),
        child: Column(
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text(
                  'Engine Status',
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                ),
                Switch(
                  value: isTradingActive,
                  activeColor: Colors.greenAccent,
                  onChanged: (val) => _toggleTrading(val),
                ),
              ],
            ),
            const Divider(height: 30),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceAround,
              children: [
                _buildStatItem('Today PnL', '₹${pnl.toStringAsFixed(2)}', isLoss ? Colors.redAccent : Colors.greenAccent),
                _buildStatItem('Trades', '${todayStats['trades'] ?? 0}', Colors.white),
              ],
            )
          ],
        ),
      ),
    );
  }

  Widget _buildStatItem(String label, String value, Color color) {
    return Column(
      children: [
        Text(
          label,
          style: TextStyle(color: Colors.grey[400], fontSize: 14),
        ),
        const SizedBox(height: 8),
        Text(
          value,
          style: TextStyle(color: color, fontSize: 24, fontWeight: FontWeight.bold),
        ),
      ],
    );
  }

  Widget _buildSettingsCard() {
    return Card(
      elevation: 4,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: Column(
        children: [
          SwitchListTile(
            title: const Text('Time Restrictions (9:15-9:30 & 1:00-1:30)'),
            subtitle: const Text('Block trades during volatile/lull periods'),
            value: useTimeRestrictions,
            activeColor: Colors.blueAccent,
            onChanged: (val) => _updateSettings('use_time_restrictions', val),
          ),
          const Divider(height: 1),
          ListTile(
            title: const Text('Instrument Type'),
            subtitle: const Text('Force system to trade Futures or Options'),
            trailing: DropdownButton<String>(
              value: instrumentType,
              dropdownColor: Theme.of(context).cardColor,
              underline: const SizedBox(),
              items: const [
                DropdownMenuItem(value: 'FUTURES', child: Text('FUTURES')),
                DropdownMenuItem(value: 'OPTIONS', child: Text('OPTIONS')),
              ],
              onChanged: (val) {
                if (val != null) {
                  _updateSettings('instrument_type', val);
                }
              },
            ),
          ),
        ],
      ),
    );
  }
}
