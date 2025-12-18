import 'dart:io';
import 'dart:typed_data';
import 'package:image_picker/image_picker.dart';
import 'package:image_cropper/image_cropper.dart';

abstract class FileRepository {
  Future<File?> pickImage();
  Future<Uint8List> readFileBytes(String path);
  Future<void> saveFile(String path, Uint8List content);
  Future<File> cropImage(File original, double aspectRatio);
}

class FileRepositoryImpl implements FileRepository {
  @override
  Future<File?> pickImage() async {
    final picked = await ImagePicker().pickImage(
      source: ImageSource.gallery,
      requestFullMetadata: false, // 禁用元数据加载
      maxWidth: 1920,
      maxHeight: 1080,
      imageQuality: 85,
    );
    return picked != null ? File(picked.path) : null;
  }

  @override
  Future<File> cropImage(File original, double aspectRatio) async {
    final croppedFile = await ImageCropper().cropImage(
      sourcePath: original.path,
      aspectRatio: CropAspectRatio(ratioX: aspectRatio, ratioY: 1.0),
      compressQuality: 100,
    );
    return croppedFile != null ? File(croppedFile.path) : original;
  }

  @override
  Future<Uint8List> readFileBytes(String path) async {
    return await File(path).readAsBytes();
  }

  @override
  Future<void> saveFile(String path, Uint8List content) async {
    await File(path).writeAsBytes(content);
  }
}