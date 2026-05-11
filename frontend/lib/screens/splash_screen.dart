import 'dart:async';
import 'package:flutter/material.dart';

class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key});

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen> with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _scaleAnimation;
  late Animation<double> _opacityAnimation;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2500),
    );

    _scaleAnimation = Tween<double>(begin: 0.8, end: 1.05).animate(
      CurvedAnimation(parent: _controller, curve: Curves.easeOutBack),
    );

    _opacityAnimation = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _controller, curve: const Interval(0.0, 0.5, curve: Curves.easeIn)),
    );

    _controller.forward();

    Timer(const Duration(seconds: 4), () {
      if (mounted) {
        Navigator.pushReplacementNamed(context, '/home');
      }
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF040408),
      body: Stack(
        fit: StackFit.expand,
        children: [
          // 1. Mesh Background Orbs
          Positioned(top: -100, right: -50, child: _buildOrb(400, Colors.deepPurpleAccent.withValues(alpha: 0.1))),
          Positioned(bottom: -100, left: -50, child: _buildOrb(300, Colors.cyanAccent.withValues(alpha: 0.1))),
          
          // 2. Main Content
          Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                ScaleTransition(
                  scale: _scaleAnimation,
                  child: FadeTransition(
                    opacity: _opacityAnimation,
                    child: Container(
                      padding: const EdgeInsets.all(40),
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        border: Border.all(color: Colors.cyanAccent.withValues(alpha: 0.2), width: 1),
                        boxShadow: [
                          BoxShadow(color: Colors.cyanAccent.withValues(alpha: 0.05), blurRadius: 60, spreadRadius: 10),
                        ],
                      ),
                      child: Column(
                        children: [
                          const Icon(Icons.auto_awesome_motion_rounded, size: 80, color: Colors.cyanAccent),
                          const SizedBox(height: 20),
                          const Text(
                            'QUANTUM',
                            style: TextStyle(
                              fontSize: 32,
                              fontWeight: FontWeight.w900,
                              letterSpacing: 12,
                              color: Colors.white,
                            ),
                          ),
                          Text(
                            'INDEX',
                            style: TextStyle(
                              fontSize: 14,
                              fontWeight: FontWeight.w300,
                              letterSpacing: 10,
                              color: Colors.cyanAccent.withValues(alpha: 0.8),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 100),
                
                // 3. Futuristic Loader
                FadeTransition(
                  opacity: _opacityAnimation,
                  child: const Column(
                    children: [
                      SizedBox(
                        width: 40,
                        height: 40,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.cyanAccent,
                          backgroundColor: Colors.white10,
                        ),
                      ),
                      SizedBox(height: 24),
                      Text(
                        'INITIALIZING QUANTUM CORE',
                        style: TextStyle(
                          color: Colors.white10,
                          fontSize: 10,
                          fontWeight: FontWeight.w900,
                          letterSpacing: 4,
                        ),
                      ),
                      SizedBox(height: 8),
                      Text(
                        'v2.0 HOLOGRAPHIC INTERFACE',
                        style: TextStyle(
                          color: Colors.white12,
                          fontSize: 8,
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
    );
  }

  Widget _buildOrb(double size, Color color) {
    return Container(
      width: size, height: size,
      decoration: BoxDecoration(shape: BoxShape.circle, boxShadow: [BoxShadow(color: color, blurRadius: 100, spreadRadius: 50)]),
    );
  }
}
