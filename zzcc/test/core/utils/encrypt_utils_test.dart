// test/core/utils/encrypt_utils_test.dart
// EncryptUtils 测试 - 测试加解密正确性

import 'package:flutter_test/flutter_test.dart';
import 'package:zzcc/core/utils/encrypt_utils.dart';

void main() {
  group('EncryptUtils', () {
    test('encryptUID and decryptUID should be reversible', () {
      final uid = 'test_uid_123';
      final password = 'password123';

      final cipher = EncryptUtils.encryptUID(uid, password);
      final decrypted = EncryptUtils.decryptUID(cipher, password);

      expect(decrypted, uid);
    });

    test('wrong password should fail decryption', () {
      final uid = 'test_uid_123';
      final password = 'password123';
      final wrongPassword = 'wrong_password';

      final cipher = EncryptUtils.encryptUID(uid, password);
      final decrypted = EncryptUtils.decryptUID(cipher, wrongPassword);

      expect(decrypted, isNull);
    });

    test('should handle special characters in UID', () {
      final uid = 'uid_with-special.chars=123';
      final password = 'pass';

      final cipher = EncryptUtils.encryptUID(uid, password);
      final decrypted = EncryptUtils.decryptUID(cipher, password);

      expect(decrypted, uid);
    });

    test('should handle long UIDs', () {
      final uid = 'a' * 100;
      final password = 'password';

      final cipher = EncryptUtils.encryptUID(uid, password);
      final decrypted = EncryptUtils.decryptUID(cipher, password);

      expect(decrypted, uid);
    });

    test('should handle short password', () {
      final uid = 'user123';
      final password = '123456'; // 6 chars -> padded to 32 bytes

      final cipher = EncryptUtils.encryptUID(uid, password);
      final decrypted = EncryptUtils.decryptUID(cipher, password);

      expect(decrypted, uid);
    });

    test('different UIDs should produce different ciphertexts', () {
      final password = 'same_password';
      final cipher1 = EncryptUtils.encryptUID('uid1', password);
      final cipher2 = EncryptUtils.encryptUID('uid2', password);

      expect(cipher1, isNot(cipher2));
    });

    test('should handle empty ciphertext gracefully', () {
      final result = EncryptUtils.decryptUID('', 'password');
      expect(result, isNull);
    });

    test('should handle invalid ciphertext', () {
      final result = EncryptUtils.decryptUID('invalid!!!cipher', 'password');
      expect(result, isNull);
    });

    test('should handle single char password', () {
      final uid = 'test_user';
      final password = 'x'; // 1 char -> padded to 32 bytes

      final cipher = EncryptUtils.encryptUID(uid, password);
      final decrypted = EncryptUtils.decryptUID(cipher, password);

      expect(decrypted, uid);
    });

    test('should handle numeric UID', () {
      final uid = '123456789';
      final password = 'my_secret';

      final cipher = EncryptUtils.encryptUID(uid, password);
      final decrypted = EncryptUtils.decryptUID(cipher, password);

      expect(decrypted, uid);
    });
  });
}
