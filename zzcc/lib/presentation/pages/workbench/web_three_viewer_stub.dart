import 'dart:typed_data';

import 'package:flutter/widgets.dart';

/// 非 Web 平台的占位实现：3D 模型查看在非 Web 平台走原生 WebView，不用此 widget。
class WebThreeViewer extends StatelessWidget {
  final String ext;
  final Uint8List bytes;

  const WebThreeViewer({super.key, required this.ext, required this.bytes});

  @override
  Widget build(BuildContext context) {
    return const Center(child: Text('Web 3D 查看器仅限 Web 平台'));
  }
}
