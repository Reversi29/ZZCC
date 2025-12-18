import 'dart:io';
// import 'dart:typed_data';
import 'package:image_picker/image_picker.dart';
import 'package:image/image.dart' as img;
import 'package:flutter/foundation.dart'; // 添加此导入

Future<File?> pickAndCropImage(String title, double aspectRatio) async {
  try {
    final picker = ImagePicker();
    final picked = await picker.pickImage(source: ImageSource.gallery);
    if (picked == null) return null;

    final bytes = await File(picked.path).readAsBytes();
    final originalImage = img.decodeImage(bytes);
    if (originalImage == null) return null;

    // 计算裁剪区域
    int targetWidth, targetHeight;
    if (originalImage.width / originalImage.height > aspectRatio) {
      targetHeight = originalImage.height;
      targetWidth = (targetHeight * aspectRatio).toInt();
    } else {
      targetWidth = originalImage.width;
      targetHeight = (targetWidth / aspectRatio).toInt();
    }

    targetWidth = targetWidth.clamp(0, originalImage.width);
    targetHeight = targetHeight.clamp(0, originalImage.height);

    final x = (originalImage.width - targetWidth) ~/ 2;
    final y = (originalImage.height - targetHeight) ~/ 2;

    final croppedImage = img.copyCrop(
      originalImage,
      x: x,
      y: y,
      width: targetWidth,
      height: targetHeight,
    );

    final tempFile = File('${picked.path}_cropped.png');
    final pngBytes = img.encodePng(croppedImage);
    if (pngBytes.isEmpty) return null;
    
    await tempFile.writeAsBytes(pngBytes);
    return tempFile;
  } catch (e) {
    debugPrint('图片处理失败: $e'); // 现在可以正常使用debugPrint
    return null;
  }
}