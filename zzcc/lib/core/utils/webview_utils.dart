// // lib/core/utils/webview_utils.dart
// import 'dart:io';
// import 'package:flutter/material.dart';
// import 'package:url_launcher/url_launcher.dart'; // 添加这个导入

// class WebViewUtils {
//   static Future<bool> isWebView2Installed() async {
//     if (Platform.isWindows) {
//       try {
//         final result = await Process.run('reg', [
//           'query',
//           r'HKEY_LOCAL_MACHINE\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
//           '/v',
//           'pv'
//         ]);
//         return result.exitCode == 0;
//       } catch (e) {
//         return false;
//       }
//     }
//     return true;
//   }

//   static Future<void> showInstallDialog(BuildContext context) async {
//     return showDialog(
//       context: context,
//       builder: (context) => AlertDialog(
//         title: const Text('需要安装 WebView2 运行时'),
//         content: const Text('此功能需要 Microsoft Edge WebView2 运行时，是否现在下载并安装？'),
//         actions: [
//           TextButton(
//             onPressed: () => Navigator.pop(context),
//             child: const Text('取消'),
//           ),
//           TextButton(
//             onPressed: () {
//               // 使用 url_launcher 包中的 launchUrl 方法
//               launchUrl(Uri.parse('https://developer.microsoft.com/en-us/microsoft-edge/webview2/#download-section'));
//               Navigator.pop(context);
//             },
//             child: const Text('下载'),
//           ),
//         ],
//       ),
//     );
//   }
// }