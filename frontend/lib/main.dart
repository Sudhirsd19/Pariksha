import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'providers/trading_provider.dart';
import 'screens/splash_screen.dart';
import 'screens/home_screen.dart';
import 'services/notification_service.dart';

import 'package:flutter/foundation.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  
  try {
    if (kIsWeb) {
      await Firebase.initializeApp(
        options: const FirebaseOptions(
          apiKey: "AIzaSyDlwmeVszlAAvjzBsOI9snQLWAH5R-a3P4",
          authDomain: "parikshalay-31bd2.firebaseapp.com",
          projectId: "parikshalay-31bd2",
          storageBucket: "parikshalay-31bd2.appspot.com",
          messagingSenderId: "982906586279",
          appId: "1:982906586279:web:310289303e4f8a7f7b8782", // Estimated web ID
        ),
      );
    } else {
      await Firebase.initializeApp();
    }
    await NotificationService.initialize();
  } catch (e) {
    debugPrint("Initialization Error: $e");
  }
  
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
