import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/trading_provider.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  double _riskPercent = 1.0;
  double _takeProfitPoints = 50.0;
  double _stopLossPoints = 25.0;
  double _maxDailyTrades = 5.0;
  bool _paperTrading = true;
  bool _isSaving = false;

  @override
  void initState() {
    super.initState();
    _loadSettings();
  }

  void _loadSettings() {
    final provider = Provider.of<TradingProvider>(context, listen: false);
    final settings = provider.systemSettings;
    setState(() {
      _riskPercent = (settings['risk_percent'] as num?)?.toDouble() ?? 1.0;
      _takeProfitPoints = (settings['take_profit_points'] as num?)?.toDouble() ?? 50.0;
      _stopLossPoints = (settings['stop_loss_points'] as num?)?.toDouble() ?? 25.0;
      _maxDailyTrades = (settings['max_daily_trades'] as num?)?.toDouble() ?? 5.0;
      _paperTrading = settings['paper_trading'] ?? true;
    });
  }

  Future<void> _saveSettings() async {
    setState(() => _isSaving = true);
    final provider = Provider.of<TradingProvider>(context, listen: false);
    await provider.updateSettings({
      'risk_percent': _riskPercent,
      'take_profit_points': _takeProfitPoints.toInt(),
      'stop_loss_points': _stopLossPoints.toInt(),
      'max_daily_trades': _maxDailyTrades.toInt(),
      'paper_trading': _paperTrading,
    });
    setState(() => _isSaving = false);
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Protocol Updated Successfully!"), backgroundColor: Colors.cyanAccent, duration: Duration(seconds: 2)),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final provider = Provider.of<TradingProvider>(context);

    return Scaffold(
      backgroundColor: const Color(0xFF040408),
      body: Stack(
        children: [
          // 1. Futuristic Mesh Background
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
                flexibleSpace: ClipRRect(
                  child: BackdropFilter(
                    filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
                    child: FlexibleSpaceBar(
                      title: const Text('CORE PROTOCOL', style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: 4, fontSize: 14)),
                      background: Container(color: Colors.black.withValues(alpha: 0.3)),
                    ),
                  ),
                ),
                leading: IconButton(
                  icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 20),
                  onPressed: () => Navigator.pop(context),
                ),
                actions: [
                  IconButton(
                    icon: const Icon(Icons.refresh_rounded, color: Colors.cyanAccent),
                    onPressed: _loadSettings,
                  ),
                ],
              ),

              SliverPadding(
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 20),
                sliver: SliverList(
                  delegate: SliverChildListDelegate([
                    _buildSectionHeader('SYSTEM MODE'),
                    _buildHolographicModeSwitch(),
                    
                    _buildSectionHeader('RISK PARAMETERS'),
                    _buildCyberSlider(
                      'CAPITAL RISK', 
                      '${_riskPercent.toStringAsFixed(1)}%', 
                      _riskPercent, 0.5, 5.0, 45, 
                      (val) => setState(() => _riskPercent = val),
                      Icons.percent_rounded, Colors.purpleAccent
                    ),
                    _buildCyberSlider(
                      'STOP LOSS', 
                      '${_stopLossPoints.toInt()} PTS', 
                      _stopLossPoints, 10, 100, 90, 
                      (val) => setState(() => _stopLossPoints = val),
                      Icons.trending_down_rounded, Colors.redAccent
                    ),
                    _buildCyberSlider(
                      'TAKE PROFIT', 
                      '${_takeProfitPoints.toInt()} PTS', 
                      _takeProfitPoints, 20, 200, 180, 
                      (val) => setState(() => _takeProfitPoints = val),
                      Icons.trending_up_rounded, Colors.greenAccent
                    ),

                    _buildSectionHeader('TRADING CAPACITY'),
                    _buildCyberSlider(
                      'MAX DAILY TRADES', 
                      '${_maxDailyTrades.toInt()} SESSIONS', 
                      _maxDailyTrades, 1, 20, 19, 
                      (val) => setState(() => _maxDailyTrades = val),
                      Icons.security_rounded, Colors.orangeAccent
                    ),

                    const SizedBox(height: 30),
                    _buildCyberSaveButton(),
                    
                    const SizedBox(height: 40),
                    _buildSectionHeader('CRITICAL OVERRIDE'),
                    _buildEmergencyPanel(provider),
                    const SizedBox(height: 60),
                  ]),
                ),
              ),
            ],
          ),
          
          if (_isSaving)
            Container(
              color: Colors.black54,
              child: const Center(child: CircularProgressIndicator(color: Colors.cyanAccent)),
            ),
        ],
      ),
    );
  }

  Widget _buildMeshBackground() {
    return Stack(
      children: [
        Positioned(top: -100, right: -100, child: _buildOrb(400, Colors.deepPurpleAccent.withValues(alpha: 0.1))),
        Positioned(bottom: 100, left: -100, child: _buildOrb(300, Colors.cyanAccent.withValues(alpha: 0.05))),
      ],
    );
  }

  Widget _buildOrb(double size, Color color) {
    return Container(
      width: size, height: size,
      decoration: BoxDecoration(shape: BoxShape.circle, boxShadow: [BoxShadow(color: color, blurRadius: 100, spreadRadius: 50)]),
    );
  }

  Widget _buildSectionHeader(String title) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16.0, top: 10),
      child: Text(
        title,
        style: const TextStyle(color: Colors.white24, fontWeight: FontWeight.w900, letterSpacing: 3, fontSize: 11),
      ),
    );
  }

  Widget _buildHolographicModeSwitch() {
    final color = _paperTrading ? Colors.orangeAccent : Colors.greenAccent;
    return Container(
      margin: const EdgeInsets.only(bottom: 24),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: color.withValues(alpha: 0.1)),
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(24),
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
          child: Container(
            padding: const EdgeInsets.all(8),
            color: color.withValues(alpha: 0.03),
            child: SwitchListTile(
              title: Text(
                _paperTrading ? 'PAPER TRADING' : 'REAL CAPITAL',
                style: TextStyle(fontWeight: FontWeight.w900, color: color, fontSize: 16, letterSpacing: 1),
              ),
              subtitle: Text(
                _paperTrading ? 'Virtual simulation active.' : 'DANGER: Real funds in use.',
                style: const TextStyle(color: Colors.white38, fontSize: 11),
              ),
              value: _paperTrading,
              onChanged: (val) => setState(() => _paperTrading = val),
              activeThumbColor: Colors.orangeAccent,
              inactiveTrackColor: Colors.greenAccent.withValues(alpha: 0.1),
              secondary: Icon(_paperTrading ? Icons.biotech_rounded : Icons.account_balance_wallet_rounded, color: color),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildCyberSlider(String label, String value, double val, double min, double max, int divisions, ValueChanged<double> onChanged, IconData icon, Color color) {
    return Container(
      margin: const EdgeInsets.only(bottom: 20),
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.02),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: Colors.white.withValues(alpha: 0.03)),
      ),
      child: Column(
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(
                children: [
                  Icon(icon, color: color, size: 18),
                  const SizedBox(width: 12),
                  Text(label, style: const TextStyle(color: Colors.white60, fontWeight: FontWeight.bold, fontSize: 13)),
                ],
              ),
              Text(value, style: TextStyle(color: color, fontWeight: FontWeight.w900, fontSize: 16)),
            ],
          ),
          const SizedBox(height: 12),
          SliderTheme(
            data: SliderThemeData(
              activeTrackColor: color,
              inactiveTrackColor: color.withValues(alpha: 0.1),
              thumbColor: Colors.white,
              overlayColor: color.withValues(alpha: 0.2),
              trackHeight: 2,
              thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 6),
            ),
            child: Slider(value: val, min: min, max: max, divisions: divisions, onChanged: onChanged),
          ),
        ],
      ),
    );
  }

  Widget _buildCyberSaveButton() {
    return Container(
      height: 64,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        boxShadow: [
          BoxShadow(color: Colors.cyanAccent.withValues(alpha: 0.1), blurRadius: 20, spreadRadius: -5),
        ],
      ),
      child: ElevatedButton(
        onPressed: _saveSettings,
        style: ElevatedButton.styleFrom(
          backgroundColor: Colors.cyanAccent.withValues(alpha: 0.1),
          foregroundColor: Colors.cyanAccent,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(20),
            side: const BorderSide(color: Colors.cyanAccent, width: 1.5),
          ),
          elevation: 0,
        ),
        child: const Text('UPLOAD PROTOCOL', style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: 2)),
      ),
    );
  }

  Widget _buildEmergencyPanel(TradingProvider provider) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.redAccent.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: Colors.redAccent.withValues(alpha: 0.2)),
      ),
      child: Row(
        children: [
          const Icon(Icons.warning_amber_rounded, color: Colors.redAccent, size: 32),
          const SizedBox(width: 20),
          const Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('EMERGENCY EXIT', style: TextStyle(color: Colors.redAccent, fontWeight: FontWeight.w900, fontSize: 14)),
                Text('Liquidate all open positions.', style: TextStyle(color: Colors.white24, fontSize: 11)),
              ],
            ),
          ),
          IconButton(
            icon: const Icon(Icons.power_off_rounded, color: Colors.redAccent),
            onPressed: () => _showSquareOffDialog(context, provider),
          ),
        ],
      ),
    );
  }

  void _showSquareOffDialog(BuildContext context, TradingProvider provider) {
    showDialog(
      context: context,
      builder: (context) => BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 5, sigmaY: 5),
        child: AlertDialog(
          backgroundColor: const Color(0xFF0A0A0E),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24), side: const BorderSide(color: Colors.redAccent, width: 1)),
          title: const Text("INITIALIZE LIQUIDATION?", style: TextStyle(color: Colors.redAccent, fontWeight: FontWeight.w900)),
          content: const Text("This protocol will terminate all active market positions. Proceed?", style: TextStyle(color: Colors.white70)),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context), child: const Text("ABORT", style: TextStyle(color: Colors.white24))),
            ElevatedButton(
              style: ElevatedButton.styleFrom(backgroundColor: Colors.redAccent, foregroundColor: Colors.white),
              onPressed: () { provider.emergencySquareOff(); Navigator.pop(context); },
              child: const Text("CONFIRM"),
            ),
          ],
        ),
      ),
    );
  }
}
