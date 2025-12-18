// lib/core/services/torrent_metadata_service.dart
import 'dart:typed_data';
import 'dart:io';
import 'dart:convert';
import 'package:crypto/crypto.dart';
import 'package:zzcc/core/services/logger_service.dart';

// 原生Bencode解码器（兼容Dart3）
class BencodeDecoder {
  int _position = 0;
  late Uint8List _data;

  dynamic decode(Uint8List data) {
    _data = data;
    _position = 0;
    return _decodeNext();
  }

  dynamic _decodeNext() {
    final byte = _data[_position];
    switch (byte) {
      case 0x64: // 'd' - dictionary
        _position++;
        final dict = <dynamic, dynamic>{};
        while (_data[_position] != 0x65) { // 'e'
          final key = _decodeNext();
          final value = _decodeNext();
          dict[key] = value;
        }
        _position++;
        return dict;
      case 0x6c: // 'l' - list
        _position++;
        final list = <dynamic>[];
        while (_data[_position] != 0x65) { // 'e'
          list.add(_decodeNext());
        }
        _position++;
        return list;
      case 0x69: // 'i' - integer
        _position++;
        final end = _findByte(0x65); // 'e'
        final numStr = utf8.decode(_data.sublist(_position, end));
        _position = end + 1;
        return int.parse(numStr);
      default: // string (starts with 0-9)
        if (byte >= 0x30 && byte <= 0x39) {
          final colon = _findByte(0x3a); // ':'
          final lengthStr = utf8.decode(_data.sublist(_position, colon));
          final length = int.parse(lengthStr);
          _position = colon + 1;
          final strBytes = _data.sublist(_position, _position + length);
          _position += length;
          // Decode using UTF-8. Many torrent metadata strings are UTF-8 encoded.
          // allowMalformed ensures we don't throw on invalid sequences; malformed
          // bytes will be replaced with the Unicode replacement character.
          return utf8.decode(strBytes, allowMalformed: true);
        }
        throw FormatException('Invalid bencode data at position $_position');
    }
  }

  int _findByte(int byte) {
    for (int i = _position; i < _data.length; i++) {
      if (_data[i] == byte) return i;
    }
    throw FormatException('Byte $byte not found');
  }
}

class TorrentMetadataService {
  final LoggerService _logger;

  TorrentMetadataService(this._logger);

  // 工具方法：将dynamic字典转为String键字典（递归转换）
  Map<String, dynamic> _convertDynamicMap(Map<dynamic, dynamic> dynamicMap) {
    final temStringMap = <String, dynamic>{};
    dynamicMap.forEach((key, value) {
      final String keyStr = key.toString();
      if (value is Map<dynamic, dynamic>) {
        temStringMap[keyStr] = _convertDynamicMap(value);
      } else if (value is List<dynamic>) {
        temStringMap[keyStr] = _convertDynamicList(value);
      } else {
        temStringMap[keyStr] = value;
      }
    });
    return temStringMap;
  }

  // 工具方法：将dynamic列表转为强类型列表
  List<dynamic> _convertDynamicList(List<dynamic> dynamicList) {
    final List<dynamic> typedList = [];
    for (var item in dynamicList) {
      if (item is Map<dynamic, dynamic>) {
        typedList.add(_convertDynamicMap(item));
      } else if (item is List<dynamic>) {
        typedList.add(_convertDynamicList(item));
      } else {
        typedList.add(item);
      }
    }
    return typedList;
  }

  // 从torrent文件路径解析元数据
  Future<Map<String, dynamic>> parseTorrentFile(String filePath) async {
    try {
      final file = File(filePath);
      final bytes = await file.readAsBytes();
      return _parseTorrentBytes(bytes);
    } catch (e) {
      _logger.error('Failed to parse torrent file: $e');
      rethrow;
    }
  }

  // 从磁力链接解析元数据（简单模拟）
  Future<Map<String, dynamic>> parseMagnetLink(String magnetUrl) async {
    try {
      final infoHash = _extractInfoHashFromMagnet(magnetUrl);
      if (infoHash == null) {
        throw Exception('无法从磁力链接中提取infoHash');
      }

      _logger.info('从磁力链接获取元数据: $magnetUrl');
      await Future.delayed(const Duration(seconds: 1));
      return {
        'name': '磁力链接资源_$infoHash',
        'comment': '',
        'created by': '',
        'files': [
          {
            'name': '未知文件_$infoHash',
            'length': 1024 * 1024 * 100,
          }
        ],
        'length': 1024 * 1024 * 100,
      };
    } catch (e) {
      _logger.error('Failed to parse magnet link: $e');
      rethrow;
    }
  }

  // 解析torrent字节数据（修复类型转换）
  Map<String, dynamic> _parseTorrentBytes(Uint8List bytes) {
    final decoder = BencodeDecoder();
    final dynamic decodedData = decoder.decode(bytes);
    if (decodedData is! Map<dynamic, dynamic>) {
      throw FormatException('Torrent文件格式错误：不是有效的字典结构');
    }
    final data = _convertDynamicMap(decodedData);
    final info = data['info'] as Map<String, dynamic>;
    final result = <String, dynamic>{};

    result['name'] = info['name'] as String;
    result['comment'] = data['comment'] as String? ?? '';
    result['created by'] = data['created by'] as String? ?? '';

    if (info.containsKey('files')) {
      final files = info['files'] as List<dynamic>;
      result['files'] = files.map((file) {
        final fileMap = file as Map<String, dynamic>;
        final pathParts = fileMap['path'] as List<dynamic>;
        return {
          'name': pathParts.join('/'),
          'length': fileMap['length'] as int,
        };
      }).toList();
      result['length'] = files.fold(0, (sum, file) => sum + (file['length'] as int));
    } else {
      result['files'] = [
        {'name': info['name'] as String, 'length': info['length'] as int}
      ];
      result['length'] = info['length'] as int;
    }

    return result;
  }

  // 从磁力链接提取infoHash
  String? _extractInfoHashFromMagnet(String magnetUrl) {
    try {
      final uri = Uri.parse(magnetUrl);
      final xtParam = uri.queryParameters.values
          .firstWhere((param) => param.startsWith('urn:btih:'), orElse: () => '');
      if (xtParam.isNotEmpty) return xtParam.substring(9);
    } catch (e) {
      _logger.warning('Failed to extract infoHash from magnet: $e');
    }
    return null;
  }

  // 计算torrent文件的info-hash（SHA1 of bencoded 'info' dict)
  Future<String> computeInfoHashFromFile(String filePath) async {
    try {
      final file = File(filePath);
      if (!await file.exists()) throw Exception('Torrent file not found');
      final bytes = await file.readAsBytes();
      final decoder = BencodeDecoder();
      final dynamic decoded = decoder.decode(bytes);
      if (decoded is! Map<dynamic, dynamic>) throw Exception('Invalid torrent file');
      final data = _convertDynamicMap(decoded);
      if (!data.containsKey('info')) throw Exception('Torrent missing info dict');
      final info = data['info'] as Map<String, dynamic>;
      final encoded = _bencode(info);
      final digest = sha1.convert(encoded);
      return digest.bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
    } catch (e) {
      _logger.error('Failed to compute infoHash from file: $e');
      rethrow;
    }
  }

  // Bencode encoder for supported types (String, int, List, Map)
  Uint8List _bencode(dynamic value) {
    final builder = BytesBuilder();

    void writeString(String s) {
      final bytes = utf8.encode(s);
      builder.add(utf8.encode('${bytes.length}:'));
      builder.add(bytes);
    }

    void writeInt(int i) {
      builder.add([0x69]); // 'i'
      builder.add(utf8.encode(i.toString()));
      builder.add([0x65]); // 'e'
    }

    int compareUtf8(String a, String b) {
      final A = utf8.encode(a);
      final B = utf8.encode(b);
      final len = A.length < B.length ? A.length : B.length;
      for (var i = 0; i < len; i++) {
        if (A[i] != B[i]) return A[i] - B[i];
      }
      return A.length - B.length;
    }

    void addValue(dynamic v) {
      if (v is String) {
        writeString(v);
        return;
      }
      if (v is int) {
        writeInt(v);
        return;
      }
      if (v is Uint8List) {
        final bytes = v;
        builder.add(utf8.encode('${bytes.length}:'));
        builder.add(bytes);
        return;
      }
      if (v is List) {
        builder.add([0x6c]); // 'l'
        for (final item in v) {
          addValue(item);
        }
        builder.add([0x65]); // 'e'
        return;
      }
      if (v is Map) {
        final map = Map<String, dynamic>.from(v);
        builder.add([0x64]); // 'd'
        final keys = map.keys.toList();
        keys.sort(compareUtf8);
        for (final k in keys) {
          writeString(k);
          addValue(map[k]);
        }
        builder.add([0x65]); // 'e'
        return;
      }

      writeString(v.toString());
    }

    addValue(value);
    return builder.toBytes();
  }
}
