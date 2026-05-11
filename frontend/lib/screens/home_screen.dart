import 'dart:ui';
import 'package:flutter/material.dart';
import 'dashboard_screen.dart';
import 'pnl_screen.dart';
import 'logs_screen.dart';
import 'analytics_screen.dart';
import 'settings_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _selectedIndex = 0;

  final List<Widget> _screens = [
    const DashboardScreen(),
    const PnLScreen(),
    const LogsScreen(),
    const AnalyticsScreen(),
    const SettingsScreen(),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF040408),
      extendBody: true, // Crucial for floating glass nav bar
      body: IndexedStack(
        index: _selectedIndex,
        children: _screens,
      ),
      bottomNavigationBar: Container(
        height: 95,
        margin: const EdgeInsets.fromLTRB(20, 0, 20, 30),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(30),
          border: Border.all(color: Colors.white.withValues(alpha: 0.05)),
          boxShadow: [
            BoxShadow(color: Colors.black.withValues(alpha: 0.5), blurRadius: 40, spreadRadius: 0),
          ],
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(30),
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
            child: BottomNavigationBar(
              currentIndex: _selectedIndex,
              onTap: (index) => setState(() => _selectedIndex = index),
              backgroundColor: Colors.white.withValues(alpha: 0.02),
              selectedItemColor: Colors.cyanAccent,
              unselectedItemColor: Colors.white24,
              showSelectedLabels: true,
              showUnselectedLabels: true,
              type: BottomNavigationBarType.fixed,
              elevation: 0,
              selectedFontSize: 9,
              unselectedFontSize: 9,
              selectedLabelStyle: const TextStyle(fontWeight: FontWeight.w900, letterSpacing: 0.5),
              unselectedLabelStyle: const TextStyle(fontWeight: FontWeight.bold, letterSpacing: 0.5),
              items: [
                _buildNavItem(Icons.grid_view_rounded, 'CORE', 0),
                _buildNavItem(Icons.analytics_outlined, 'RESULTS', 1),
                _buildNavItem(Icons.terminal_rounded, 'LOGS', 2),
                _buildNavItem(Icons.radar_rounded, 'HUB', 3),
                _buildNavItem(Icons.settings_input_component_rounded, 'PROTOCOLS', 4),
              ],
            ),
          ),
        ),
      ),
    );
  }

  BottomNavigationBarItem _buildNavItem(IconData icon, String label, int index) {
    final isSelected = _selectedIndex == index;
    return BottomNavigationBarItem(
      icon: Container(
        margin: const EdgeInsets.only(bottom: 4),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        decoration: BoxDecoration(
          color: isSelected ? Colors.cyanAccent.withValues(alpha: 0.05) : Colors.transparent,
          borderRadius: BorderRadius.circular(16),
        ),
        child: Icon(icon, size: 22),
      ),
      label: label,
    );
  }
}
