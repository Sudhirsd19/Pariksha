import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'providers/trading_provider.dart';
import 'screens/splash_screen.dart';
import 'screens/home_screen.dart';
import 'services/notification_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp();
  await NotificationService.initialize();
  
  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => TradingProvider()),
      ],
      child: const QuantumIndexApp(),
    ),
  );
}

class QuantumIndexApp extends StatelessWidget {
  const QuantumIndexApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'QuantumIndex',
      debugShowCheckedModeBanner: false,
      scaffoldMessengerKey: TradingProvider.scaffoldMessengerKey,
      theme: ThemeData(
        brightness: Brightness.dark,
        primaryColor: Colors.cyanAccent,
        scaffoldBackgroundColor: const Color(0xFF040408),
        colorScheme: const ColorScheme.dark(
          primary: Colors.cyanAccent,
          secondary: Colors.purpleAccent,
          surface: Color(0xFF0A0A0E),
        ),
        useMaterial3: true,
      ),
      initialRoute: '/',
      routes: {
        '/': (context) => const SplashScreen(),
        '/home': (context) => const HomeScreen(),
      },
    );
  }
}
