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
  double _capitalLimit = 10000.0;
  double _maxDirectionalExposure = 5.0;
  bool _paperTrading = true;
  String _instrumentType = 'FUTURES';
  bool _fnoTrading = true;
  bool _equityTrading = true;
  bool _useTimeRestrictions = true;
  bool _equityAutoExecution = false;
  String _equityQtyMode = 'FIXED';
  int _equityFixedQty = 1;
  int _equityMinScore = 70;
  bool _isSaving = false;
  bool _isInitialized = false;

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
      _capitalLimit = (settings['capital_limit'] as num?)?.toDouble() ?? 10000.0;
      _maxDirectionalExposure = (settings['max_directional_exposure'] as num?)?.toDouble() ?? 5.0;
      _paperTrading = settings['paper_trading'] ?? true;
      _instrumentType = settings['instrument_type'] ?? 'FUTURES';
      _fnoTrading = settings['fno_trading'] ?? true;
      _equityTrading = settings['equity_trading'] ?? true;
      _useTimeRestrictions = settings['use_time_restrictions'] ?? true;
      _equityAutoExecution = settings['equity_auto_execution'] ?? false;
      _equityQtyMode = settings['equity_qty_mode'] ?? 'FIXED';
      _equityFixedQty = (settings['equity_fixed_qty'] as num?)?.toInt() ?? 1;
      _equityMinScore = (settings['equity_min_score'] as num?)?.toInt() ?? 70;
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
      'max_trades_per_day': _maxDailyTrades.toInt(),  // Backend key
      'capital_limit': _capitalLimit,
      'max_directional_exposure': _maxDirectionalExposure.toInt(),
      'paper_trading': _paperTrading,
      'instrument_type': _instrumentType,
      'fno_trading': _fnoTrading,
      'equity_trading': _equityTrading,
      'use_time_restrictions': _useTimeRestrictions,
      'equity_auto_execution': _equityAutoExecution,
      'equity_qty_mode': _equityQtyMode,
      'equity_fixed_qty': _equityFixedQty,
      'equity_min_score': _equityMinScore,
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

    if (!_isInitialized && provider.systemSettings.isNotEmpty) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) {
          _loadSettings();
          setState(() {
            _isInitialized = true;
          });
        }
      });
    }

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
                leading: Navigator.canPop(context)
                    ? IconButton(
                        icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 20),
                        onPressed: () => Navigator.pop(context),
                      )
                    : null,
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
                    
                    _buildSectionHeader('TRADING SEGMENTS'),
                    _buildSegmentSwitches(),
                    
                    _buildSectionHeader('TRADING INSTRUMENT'),
                    _buildInstrumentToggle(),
                    
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
                    _buildCyberSlider(
                      'MAX DIRECTIONAL EXPOSURE', 
                      '${_maxDirectionalExposure.toInt()} TRADES/SIDE', 
                      _maxDirectionalExposure, 1, 20, 19, 
                      (val) => setState(() => _maxDirectionalExposure = val),
                      Icons.compare_arrows_rounded, Colors.amberAccent
                    ),
                    _buildCyberSlider(
                      'CAPITAL LIMIT', 
                      '₹${_capitalLimit.toInt()}', 
                      _capitalLimit, 5000, 100000, 19, 
                      (val) => setState(() => _capitalLimit = val),
                      Icons.account_balance_wallet_rounded, Colors.cyanAccent
                    ),
                    
                    _buildSectionHeader('EQUITY AUTO-EXECUTION'),
                    _buildEquityAutoExecutionPanel(),

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

  Widget _buildSegmentSwitches() {
    const activeColor = Colors.cyanAccent;
    return Container(
      margin: const EdgeInsets.only(bottom: 24),
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.02),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: Colors.white.withValues(alpha: 0.03)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.tune_rounded, color: activeColor, size: 18),
              SizedBox(width: 12),
              Text('ACTIVE SEGMENTS', style: TextStyle(color: Colors.white60, fontWeight: FontWeight.bold, fontSize: 13)),
            ],
          ),
          const SizedBox(height: 16),
          SwitchListTile(
            title: const Text(
              'FUTURES & OPTIONS (F&O)',
              style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white, fontSize: 14),
            ),
            subtitle: const Text(
              'Automated F&O loop trading for NIFTY/BANKNIFTY.',
              style: TextStyle(color: Colors.white38, fontSize: 10),
            ),
            value: _fnoTrading,
            onChanged: (val) => setState(() => _fnoTrading = val),
            activeThumbColor: activeColor,
            activeTrackColor: activeColor.withValues(alpha: 0.2),
            inactiveThumbColor: Colors.white38,
            inactiveTrackColor: Colors.white10,
            contentPadding: EdgeInsets.zero,
          ),
          const Divider(color: Colors.white10, height: 24),
          SwitchListTile(
            title: const Text(
              'EQUITY CASH (INTRADAY)',
              style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white, fontSize: 14),
            ),
            subtitle: const Text(
              'Intraday stock trades execution from Watchlist.',
              style: TextStyle(color: Colors.white38, fontSize: 10),
            ),
            value: _equityTrading,
            onChanged: (val) => setState(() => _equityTrading = val),
            activeThumbColor: activeColor,
            activeTrackColor: activeColor.withValues(alpha: 0.2),
            inactiveThumbColor: Colors.white38,
            inactiveTrackColor: Colors.white10,
            contentPadding: EdgeInsets.zero,
          ),
          const Divider(color: Colors.white10, height: 24),
          SwitchListTile(
            title: const Text(
              'TIME RESTRICTIONS',
              style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white, fontSize: 14),
            ),
            subtitle: const Text(
              'Block trades during 9:15-9:30 & 1:00-1:30',
              style: TextStyle(color: Colors.white38, fontSize: 10),
            ),
            value: _useTimeRestrictions,
            onChanged: (val) => setState(() => _useTimeRestrictions = val),
            activeThumbColor: activeColor,
            activeTrackColor: activeColor.withValues(alpha: 0.2),
            inactiveThumbColor: Colors.white38,
            inactiveTrackColor: Colors.white10,
            contentPadding: EdgeInsets.zero,
          ),
        ],
      ),
    );
  }

  Widget _buildInstrumentToggle() {
    final isOptions = _instrumentType == "OPTIONS";
    const activeColor = Colors.cyanAccent;
    return Container(
      margin: const EdgeInsets.only(bottom: 24),
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.02),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: Colors.white.withValues(alpha: 0.03)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.swap_horizontal_circle_outlined, color: activeColor, size: 18),
              SizedBox(width: 12),
              Text('TRADING INSTRUMENT', style: TextStyle(color: Colors.white60, fontWeight: FontWeight.bold, fontSize: 13)),
            ],
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: InkWell(
                  onTap: () => setState(() => _instrumentType = "FUTURES"),
                  child: Container(
                    height: 48,
                    decoration: BoxDecoration(
                      color: !isOptions ? activeColor.withValues(alpha: 0.1) : Colors.transparent,
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: !isOptions ? activeColor : Colors.white24, width: 1.5),
                    ),
                    child: Center(
                      child: Text(
                        'FUTURES',
                        style: TextStyle(
                          fontWeight: FontWeight.w900,
                          color: !isOptions ? Colors.white : Colors.white38,
                          letterSpacing: 1.5,
                        ),
                      ),
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: InkWell(
                  onTap: () => setState(() => _instrumentType = "OPTIONS"),
                  child: Container(
                    height: 48,
                    decoration: BoxDecoration(
                      color: isOptions ? activeColor.withValues(alpha: 0.1) : Colors.transparent,
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: isOptions ? activeColor : Colors.white24, width: 1.5),
                    ),
                    child: Center(
                      child: Text(
                        'OPTIONS',
                        style: TextStyle(
                          fontWeight: FontWeight.w900,
                          color: isOptions ? Colors.white : Colors.white38,
                          letterSpacing: 1.5,
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            isOptions 
                ? 'Low Capital Buying: Trade ATM Weekly Call/Put Options (~₹3k - ₹10k per lot).' 
                : 'Direct Index Tracking: Trade index futures (~₹1.2L margin per lot).',
            style: const TextStyle(color: Colors.white38, fontSize: 11),
          ),
        ],
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

  Widget _buildEquityAutoExecutionPanel() {
    const activeColor = Colors.cyanAccent;
    return Container(
      margin: const EdgeInsets.only(bottom: 24),
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        // ignore: deprecated_member_use
        color: Colors.white.withOpacity(0.02),
        borderRadius: BorderRadius.circular(24),
        // ignore: deprecated_member_use
        border: Border.all(color: Colors.white.withOpacity(0.03)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.bolt_rounded, color: activeColor, size: 18),
              SizedBox(width: 12),
              Text('EQUITY AUTO-EXECUTION SETTINGS', style: TextStyle(color: Colors.white60, fontWeight: FontWeight.bold, fontSize: 13)),
            ],
          ),
          const SizedBox(height: 16),
          SwitchListTile(
            title: const Text(
              'AUTO-EXECUTION PROTOCOL',
              style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white, fontSize: 14),
            ),
            subtitle: const Text(
              'Automatic buy/sell order placement on scan signals.',
              style: TextStyle(color: Colors.white38, fontSize: 10),
            ),
            value: _equityAutoExecution,
            onChanged: (val) => setState(() => _equityAutoExecution = val),
            activeThumbColor: activeColor,
            // ignore: deprecated_member_use
            activeTrackColor: activeColor.withOpacity(0.2),
            inactiveThumbColor: Colors.white38,
            inactiveTrackColor: Colors.white10,
            contentPadding: EdgeInsets.zero,
          ),
          if (_equityAutoExecution) ...[
            const Divider(color: Colors.white10, height: 24),
            const Text('QUANTITY ALLOCATION MODE', style: TextStyle(color: Colors.white60, fontWeight: FontWeight.bold, fontSize: 13)),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: RadioListTile<String>(
                    title: const Text('FIXED SHARES', style: TextStyle(color: Colors.white, fontSize: 12)),
                    value: 'FIXED',
                    // ignore: deprecated_member_use
                    groupValue: _equityQtyMode,
                    activeColor: activeColor,
                    contentPadding: EdgeInsets.zero,
                    // ignore: deprecated_member_use
                    onChanged: (val) => setState(() => _equityQtyMode = val!),
                  ),
                ),
                Expanded(
                  child: RadioListTile<String>(
                    title: const Text('CAPITAL LIMIT', style: TextStyle(color: Colors.white, fontSize: 12)),
                    value: 'CAPITAL_LIMIT',
                    // ignore: deprecated_member_use
                    groupValue: _equityQtyMode,
                    activeColor: activeColor,
                    contentPadding: EdgeInsets.zero,
                    // ignore: deprecated_member_use
                    onChanged: (val) => setState(() => _equityQtyMode = val!),
                  ),
                ),
              ],
            ),
            if (_equityQtyMode == 'FIXED') ...[
              const SizedBox(height: 12),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text('FIXED SHARES COUNT', style: TextStyle(color: Colors.white70, fontSize: 13)),
                  Row(
                    children: [
                      IconButton(
                        icon: const Icon(Icons.remove_rounded, color: Colors.white54),
                        onPressed: _equityFixedQty > 1 ? () => setState(() => _equityFixedQty--) : null,
                      ),
                      Text(
                        '$_equityFixedQty',
                        style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 16),
                      ),
                      IconButton(
                        icon: const Icon(Icons.add_rounded, color: Colors.white54),
                        onPressed: () => setState(() => _equityFixedQty++),
                      ),
                    ],
                  )
                ],
              ),
            ],
            const Divider(color: Colors.white10, height: 24),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('MINIMUM WHALE SCORE', style: TextStyle(color: Colors.white70, fontSize: 13, fontWeight: FontWeight.bold)),
                    Text('Only trigger auto-trades if score is above this', style: TextStyle(color: Colors.white38, fontSize: 10)),
                  ],
                ),
                Row(
                  children: [
                    IconButton(
                      icon: const Icon(Icons.remove_rounded, color: Colors.white54),
                      onPressed: _equityMinScore > 20 ? () => setState(() => _equityMinScore -= 5) : null,
                    ),
                    Text(
                      '$_equityMinScore',
                      style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 16),
                    ),
                    IconButton(
                      icon: const Icon(Icons.add_rounded, color: Colors.white54),
                      onPressed: _equityMinScore < 100 ? () => setState(() => _equityMinScore += 5) : null,
                    ),
                  ],
                )
              ],
            ),
          ]
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
