// lib/presentation/pages/square/widgets/knowledge_graph_view.dart
import 'dart:io'; 
import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'package:url_launcher/url_launcher.dart';

class KnowledgeGraphView extends StatefulWidget {
  const KnowledgeGraphView({super.key});

  @override
  State<KnowledgeGraphView> createState() => _KnowledgeGraphViewState();
}

class _KnowledgeGraphViewState extends State<KnowledgeGraphView> {
  bool _isLoading = true;
  double _progress = 0;

  @override
  void initState() {
    super.initState();
    if (Platform.isWindows) {
      _checkWebViewInstallation();
    }
  }

  Future<void> _checkWebViewInstallation() async {
    try {
      final result = await Process.run('reg', [
        'query',
        r'HKEY_LOCAL_MACHINE\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
        '/v',
        'pv'
      ]);
      if (result.exitCode != 0) {
        _showInstallDialog();
        return;
      }
    } catch (e) {
      _showInstallDialog();
      return;
    }
  }

  void _showInstallDialog() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      showDialog(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('需要安装 WebView2 运行时'),
          content: const Text('此功能需要 Microsoft Edge WebView2 运行时，是否现在下载并安装？'),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('取消'),
            ),
            TextButton(
              onPressed: () {
                launchUrl(Uri.parse(
                    'https://developer.microsoft.com/en-us/microsoft-edge/webview2/#download-section'));
                Navigator.pop(context);
              },
              child: const Text('下载'),
            ),
          ],
        ),
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      // 完全移除 AppBar
      body: Stack(
        children: [
          InAppWebView(
            initialUrlRequest: URLRequest(
              url: WebUri('http://60.204.234.59:3009'),
            ),
            initialSettings: InAppWebViewSettings(
              javaScriptEnabled: true,
              transparentBackground: true,
              useShouldOverrideUrlLoading: true,
            ),
            onLoadStart: (controller, url) {
              setState(() => _isLoading = true);
            },
            onLoadStop: (controller, url) {
              setState(() => _isLoading = false);
            },
            onProgressChanged: (controller, progress) {
              setState(() => _progress = progress / 100);
            },
            onReceivedError: (controller, request, error) {
              debugPrint('WebView加载错误: ${error.description}');
              setState(() => _isLoading = false);
            },
            shouldOverrideUrlLoading: (controller, navigationAction) async {
              final uri = navigationAction.request.url;
              if (uri != null && (uri.toString().startsWith('http://') || uri.toString().startsWith('https://'))) {
                return NavigationActionPolicy.ALLOW;
              }
              return NavigationActionPolicy.CANCEL;
            },
          ),
          if (_isLoading)
            Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  CircularProgressIndicator(value: _progress),
                  const SizedBox(height: 10),
                  Text('加载中... ${(_progress * 100).toStringAsFixed(0)}%'),
                ],
              ),
            ),
        ],
      ),
    );
  }
}