// lib/core/utils/encrypt_utils.dart
import 'dart:typed_data';
import 'package:encrypt/encrypt.dart' as encrypt;

class EncryptUtils {
  // 自定义Base字符集（与注册时保持一致）
  static const String _customBaseChars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  static const int _customBase = _customBaseChars.length;

  // 加密UID（与注册时逻辑完全一致）
  static String encryptUID(String uid, String password) {
    final paddedPassword = password.padRight(32).substring(0, 32);
    final key = encrypt.Key.fromUtf8(paddedPassword);
    final iv = encrypt.IV.fromSecureRandom(16);
    final encrypter = encrypt.Encrypter(encrypt.AES(key));
    final encrypted = encrypter.encrypt(uid, iv: iv);

    // 将List<int>转换为Uint8List
    final combinedBytes = Uint8List.fromList(iv.bytes + encrypted.bytes);
    return _customBaseEncode(combinedBytes);
  }

  // 解密UID（新增：用于登录时验证）
  static String? decryptUID(String ciphertext, String password) {
    try {
      final bytes = _customBaseDecode(ciphertext);
      if (bytes.length < 16) return null;

      // 将List<int>转换为Uint8List
      final allBytes = Uint8List.fromList(bytes);
      final ivBytes = allBytes.sublist(0, 16);
      final encryptedBytes = allBytes.sublist(16);

      final paddedPassword = password.padRight(32).substring(0, 32);
      final key = encrypt.Key.fromUtf8(paddedPassword);
      final iv = encrypt.IV(ivBytes);
      final encrypter = encrypt.Encrypter(encrypt.AES(key));

      final encrypted = encrypt.Encrypted(encryptedBytes);
      return encrypter.decrypt(encrypted, iv: iv);
    } catch (_) {
      return null;
    }
  }

  /// 加密密码本身（使用静态密钥，区别于以密码为密钥的 UID 加密）
  static String encryptPassword(String plain) {
    final key = _passwordKey();
    final iv = encrypt.IV(Uint8List.fromList(Uint8List(16))); // 固定 IV
    final encrypter = encrypt.Encrypter(encrypt.AES(key));
    final encrypted = encrypter.encrypt(plain);
    final combined = Uint8List.fromList(iv.bytes + encrypted.bytes);
    return _customBaseEncode(combined);
  }

  /// 解密密码
  static String? decryptPassword(String cipher) {
    try {
      final bytes = _customBaseDecode(cipher);
      if (bytes.length < 16) return null;
      final allBytes = Uint8List.fromList(bytes);
      final ivBytes = allBytes.sublist(0, 16);
      final encryptedBytes = allBytes.sublist(16);

      final key = _passwordKey();
      final iv = encrypt.IV(ivBytes);
      final encrypter = encrypt.Encrypter(encrypt.AES(key));
      final encrypted = encrypt.Encrypted(encryptedBytes);
      return encrypter.decrypt(encrypted, iv: iv);
    } catch (_) {
      return null;
    }
  }

  /// 判断字段值是否已加密
  static bool isPasswordEncrypted(String value) {
    try {
      final bytes = _customBaseDecode(value);
      return bytes.length >= 16;
    } catch (_) {
      return false;
    }
  }

  // --- 静态密钥（用于密码加密，独立于用户密码） ---
  static encrypt.Key _passwordKey() {
    final keyBytes = Uint8List(16);
    for (int i = 0; i < 16; i++) {
      keyBytes[i] = 0x6a;
    }
    return encrypt.Key(Uint8List.fromList(keyBytes));
  }

  // --- 自定义Base编码 ---
  static String _customBaseEncode(List<int> bytes) {
    if (bytes.isEmpty) return '';
    BigInt big = BigInt.zero;
    for (var byte in bytes) {
      big = (big << 8) | BigInt.from(byte);
    }
    if (big == BigInt.zero) {
      return _customBaseChars[0];
    }
    final base = BigInt.from(_customBase);
    final buffer = StringBuffer();
    while (big > BigInt.zero) {
      final remainder = big % base;
      buffer.write(_customBaseChars[remainder.toInt()]);
      big = big ~/ base;
    }
    return buffer.toString().split('').reversed.join();
  }

  // 新增：自定义Base解码（与编码对应）
  static List<int> _customBaseDecode(String str) {
    if (str.isEmpty) return [];
    BigInt big = BigInt.zero;
    for (final char in str.split('')) {
      final index = _customBaseChars.indexOf(char);
      if (index == -1) return []; // 非法字符返回空列表
      big = big * BigInt.from(_customBase) + BigInt.from(index);
    }

    final bytes = <int>[];
    if (big == BigInt.zero) {
      bytes.add(0);
    } else {
      while (big > BigInt.zero) {
        bytes.add((big & BigInt.from(0xff)).toInt());
        big = big >> 8;
      }
    }
    return bytes.reversed.toList();
  }
}