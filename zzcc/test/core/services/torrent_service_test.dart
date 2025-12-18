// test/core/services/torrent_service_test.dart
import 'dart:ffi';
import 'dart:io';
import 'dart:async';
import 'package:ffi/ffi.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as path;
import 'dart:developer';

// extension SafeIterable<E> on Iterable<E> {
//   E? firstOrNull() => isEmpty ? null : first;
// }

DynamicLibrary _safeLoadLibrary(String dllPath, String depsPath) {
  if (Platform.isWindows) {
    // 方法1：直接加载
    try {
      return DynamicLibrary.open(dllPath);
    } catch (e) {
      log('直接加载失败: $e');
    }

    // 方法2：使用 SetDllDirectory 设置搜索路径
    try {
      final kernel32 = DynamicLibrary.open('kernel32.dll');
      final setDllDir = kernel32.lookupFunction<
        Int Function(Pointer<Utf8>),
        int Function(Pointer<Utf8>)
      >('SetDllDirectoryA');
      
      // 设置依赖库路径
      final depsPathPtr = depsPath.toNativeUtf8();
      setDllDir(depsPathPtr);
      malloc.free(depsPathPtr);
      
      // 再次尝试加载
      return DynamicLibrary.open(dllPath);
    } catch (e) {
      log('SetDllDirectory 失败: $e');
    }

    // 方法3：复制依赖到当前工作目录
    try {
      log('复制依赖库到当前目录...');
      final depsDir = Directory(depsPath);
      for (var file in depsDir.listSync()) {
        if (file is File && file.path.toLowerCase().endsWith('.dll')) {
          final dest = path.join(Directory.current.path, path.basename(file.path));
          file.copySync(dest);
          log('已复制: ${path.basename(file.path)}');
        }
      }
      return DynamicLibrary.open(dllPath);
    } catch (e) {
      log('复制依赖失败: $e');
      rethrow;
    }
  }
  return DynamicLibrary.open(dllPath);
}

final globalSymbols = <String>[];

String _getProjectRoot() {
  final currentDir = Directory.current.path;
  final testDir = path.dirname(Platform.script.toFilePath());
  
  if (testDir.contains('test')) {
    return path.normalize(path.join(testDir, '..', '..'));
  }
  return currentDir;
}

void main() {
  group('TorrentService Tests', () {
    late DynamicLibrary lib;
    late String dllPath;

    setUpAll(() {
      // 确定动态库路径
      final projectRoot = _getProjectRoot();
      log('projectRoot');
      log(projectRoot);
      if (Platform.isWindows) {
        final depsPath = path.join(
          projectRoot,
          'native',
          'windows',
        );

        final dllPath = path.join(
          projectRoot,
          'native',
          'windows',
          'torrent_ffi.dll'
        );
        
        log('安全加载动态库: $dllPath');
        lib = _safeLoadLibrary(dllPath, depsPath);
      } else if (Platform.isMacOS) {
        dllPath = 'torrent_ffi.dylib';
      } else {
        dllPath = 'torrent_ffi.so';
      }
      
      log('加载动态库: $dllPath');
      lib = DynamicLibrary.open(dllPath);
    });

    test('动态库加载成功', () {
      expect(lib, isNotNull);
      expect(lib.handle, isNot(0));
    });

    test('打印动态库内容', () async {
      final completer = Completer<void>();
      logDllExports(dllPath).then((_) {
        log('DLL 导出函数获取完成');
        completer.complete();
      }).catchError((e, stack) {
        log('获取 DLL 导出函数失败: $e');
        log(stack);
        completer.complete();
      });
      await completer.future;
    });

    test('测试简单函数是否存在', () {
      final testSymbols = [
        r'?add_torrent@session_handle@libtorrent@@QEAA?AUtorrent_handle@2@$$QEAUadd_torrent_params@v2@2@@Z',
        r'??0add_torrent_alert@v2@libtorrent@@QEAA@$$QEAU012@@Z',
        r'?0add_torrent_alert@v2@libtorrent@@QEAA@$$QEAU012@@Z',
        r'0add_torrent_alert@v2@libtorrent@@QEAA@$$QEAU012@@Z',
        r'add_torrent_alert@v2@libtorrent@@QEAA@$$QEAU012@@Z',
        r'??0add_torrent_alert'
      ];
      
      for (final symbol in testSymbols) {
        try {
          lib.lookup<NativeFunction>(symbol);
          log('✅ 找到符号: $symbol');
        } catch (e) {
          log('❌ 未找到符号: $symbol');
        }
      }
    });

    test('调用测试函数（如果存在）', () {
      try {
        final testAddPtr = lib.lookup<NativeFunction<TestAddNativeFunc>>('test_add');
        final testAdd = testAddPtr.asFunction<TestAddDartFunc>();
        final result = testAdd(2, 3);
        log('测试函数结果: 2 + 3 = $result');
        expect(result, 5);
      } catch (e) {
        log('未找到测试函数 test_add');
      }
    });

    // test('创建会话', () {
    //   try {
    //     final createSessionPtr = lib.lookup<NativeFunction<CreateSessionNativeFunc>>('create_session');
    //     final createSession = createSessionPtr.asFunction<CreateSessionDartFunc>();
    //     final session = createSession();
    //     expect(session, isNot(nullptr));
    //     log('会话创建成功: ${session.address}');
    //   } catch (e) {
    //     log('创建会话失败: $e');
    //     rethrow;
    //   }
    // });

    // test('添加种子', () {
    //   try {
    //     // 尝试查找不同名称的函数
    //     final addFuncNames = ['add_torrent', 'create_torrent', 'start_torrent'];
    //     Pointer<NativeFunction<AddTorrentNativeFunc>>? addFuncPtr;
    //     AddTorrentDartFunc? addFunc;
        
    //     for (final name in addFuncNames) {
    //       try {
    //         addFuncPtr = lib.lookup<NativeFunction<AddTorrentNativeFunc>>(name);
    //         addFunc = addFuncPtr.asFunction<AddTorrentDartFunc>();
    //         log('使用函数: $name');
    //         break;
    //       } catch (_) {}
    //     }
        
    //     if (addFunc == null) throw Exception('未找到添加种子函数');
        
    //     final createSessionPtr = lib.lookup<NativeFunction<CreateSessionNativeFunc>>('create_session');
    //     final createSession = createSessionPtr.asFunction<CreateSessionDartFunc>();
    //     final session = createSession();
        
    //     final magnet = 'magnet:?xt=urn:btih:TESTHASH'.toNativeUtf8();
    //     final savePath = '/download/path'.toNativeUtf8();
        
    //     addFunc(session, magnet, savePath);
        
    //     malloc.free(magnet);
    //     malloc.free(savePath);
        
    //     log('种子添加成功');
    //   } catch (e) {
    //     log('添加种子失败: $e');
    //     rethrow;
    //   }
    // });
  });
}

// 函数类型定义
typedef TestAddNativeFunc = Int32 Function(Int32, Int32);
typedef TestAddDartFunc = int Function(int, int);

typedef CreateSessionNativeFunc = Pointer<Void> Function();
typedef CreateSessionDartFunc = Pointer<Void> Function();

typedef AddTorrentNativeFunc = Void Function(Pointer<Void>, Pointer<Utf8>, Pointer<Utf8>);
typedef AddTorrentDartFunc = void Function(Pointer<Void>, Pointer<Utf8>, Pointer<Utf8>);


Future<void> logDllExports(String dllPath) async {
  if (Platform.isWindows) {
    await _logWindowsDllExports(dllPath);
  } else if (Platform.isLinux) {
    await _logLinuxSoExports(dllPath);
  } else if (Platform.isMacOS) {
    await _logMacDylibExports(dllPath);
  } else {
    log('Unsupported platform');
  }
}

Future<void> _logWindowsDllExports(String dllPath) async {
  try {
    final result = await Process.run(
      r'F:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Tools\MSVC\14.41.34120\bin\Hostx64\x64\dumpbin.exe',
      ['/EXPORTS', dllPath],
      runInShell: true
    );
    
    if (result.exitCode != 0) {
      log('Error running dumpbin (exit code ${result.exitCode}): ${result.stderr}');
      return;
    }
    
    final output = result.stdout as String;
    log('Windows DLL Exports for $dllPath:');
    
    // 解析 dumpbin 输出
    final lines = output.split('\n');
    bool inExportSection = false;
    bool passedHeader = false;
    
    for (final line in lines) {
      // 检测是否进入导出部分
      if (line.contains('ordinal') && line.contains('hint') && line.contains('RVA') && line.contains('name')) {
        inExportSection = true;
        passedHeader = false;
        log('  > Found exports section');
        continue;
      }
      
      // 跳过空白行
      if (line.trim().isEmpty) {
        if (inExportSection && passedHeader) {
          log('  > End of exports section');
          break;
        }
        continue;
      }
      
      if (inExportSection) {
        // 检查是否已跳过表头
        if (!passedHeader) {
          // 检查下一行是否是表头分隔符（通常是 "----" 或类似）
          if (line.contains(RegExp(r'^-+$'))) {
            passedHeader = true;
            log('  > Passed header separator');
          }
          continue;
        }

        // final parts = line.trim().split(RegExp(r'\s+'));
        // if (parts.length >= 4) {
        //   final ordinal = parts[0];
        //   final hint = parts[1];
        //   final rva = parts[2];
        //   final name = parts[3];
          
        //   log('  - Ordinal: $ordinal, Hint: $hint, RVA: 0x$rva');
        //   log('    Full Name: $name');
          
        //   // 添加原始名称
        //   globalSymbols.add(name);
          
        //   // 尝试解析 C++ 修饰名
        //   final cppName = name
        //     .replaceAll('@', '_')
        //     .replaceAll('?', 'Q');
          
        //   // 尝试提取可能的函数名
        //   final possibleNames = <String>[
        //     cppName,
        //     name.split('@').firstOrNull?.replaceFirst('?', '') ?? '',
        //     name.split('=').firstOrNull?.trim() ?? '',
        //   ].where((n) => n.isNotEmpty).toList();
          
        //   if (possibleNames.isNotEmpty) {
        //     log('    Possible names: ${possibleNames.join(', ')}');
        //     globalSymbols.addAll(possibleNames.where((n) => n.length > 3));
        //   }
        // } else {
        //   log('  - Unparsed: $line');
        // }
        
        // 使用更精确的正则表达式解析导出行
        // 格式示例: "     1    0 000148A0 ??0add_torrent_alert@v2@libtorrent@@QEAA@$$QEAU012@@Z"
        final match = RegExp(r'^\s*(\d+)\s+([0-9A-F]+)\s+([0-9A-F]+)\s+([^\s]+)(?:\s*=\s*.*)?$').firstMatch(line);
        if (match != null) {
          log('debug');
          final ordinal = match.group(1) ?? 'unknown';
          final hint = match.group(2) ?? 'unknown';
          final rva = match.group(3) ?? 'unknown';
          final name = match.group(4);
          
          if (name != null) {
            log('  - Ordinal: $ordinal, Hint: $hint, RVA: 0x$rva');
            log('    Full Name: $name');
            
            // 尝试添加原始名称到符号列表
            globalSymbols.add(name);
            
            // 尝试解析 C++ 修饰名
            final cppName = name
              .replaceAll('@', '_')
              .replaceAll('?', 'Q');
            
            // 尝试提取可能的函数名
            final possibleNames = <String>[
              cppName,
              name.split('@').firstOrNull?.replaceFirst('?', '') ?? '',
              name.split('=').firstOrNull?.trim() ?? '',
            ].where((n) => n.isNotEmpty).toList();
            
            if (possibleNames.isNotEmpty) {
              log('    Possible names: ${possibleNames.join(', ')}');
              globalSymbols.addAll(possibleNames.where((n) => n.length > 3));
            }
          } else {
            log('  - Unparsed (name missing): $line');
          }
        } else {
          // 如果正则不匹配，尝试简单提取名称
          final simpleMatch = RegExp(r'^\s*\d+\s+\d+\s+[0-9A-F]+\s+([^\s]+)').firstMatch(line);
          if (simpleMatch != null) {
            final name = simpleMatch.group(1);
            if (name != null) {
              log('  - Simple match: $name');
              globalSymbols.add(name);
            } else {
              log('  - Unparsed: $line');
            }
          } else {
            log('  - Unparsed: $line');
          }
        }
      } else {
        // 记录其他信息
        log('  > $line');
      }
    }
    
    log('  > Total symbols found: ${globalSymbols.length}');
    if (globalSymbols.isNotEmpty) {
      log('  > First 5 symbols: ${globalSymbols.take(5).join(', ')}');
    } else {
      log('  > No valid symbols found');
    }
  } catch (e) {
    log('Error in _logWindowsDllExports: $e');
  }
}

Future<void> _logLinuxSoExports(String soPath) async {
  final result = await Process.run('nm', ['-D', '--defined-only', soPath]);
  if (result.exitCode != 0) {
    log('Error running nm: ${result.stderr}');
    return;
  }
  
  final output = result.stdout as String;
  log('Linux SO Exports for $soPath:');
  
  final lines = output.split('\n');
  for (final line in lines) {
    // 查找 T 类型（代码段）的函数
    if (line.contains(' T ')) {
      final parts = line.split(' ');
      if (parts.length >= 3) {
        log('  - ${parts[2]}');
      }
    }
  }
}

Future<void> _logMacDylibExports(String dylibPath) async {
  final result = await Process.run('nm', ['-gU', dylibPath]);
  if (result.exitCode != 0) {
    log('Error running nm: ${result.stderr}');
    return;
  }
  
  final output = result.stdout as String;
  log('macOS Dylib Exports for $dylibPath:');
  
  final lines = output.split('\n');
  for (final line in lines) {
    // 查找 T 类型（代码段）的函数
    if (line.contains(' T ')) {
      final parts = line.split(' ');
      if (parts.length >= 3) {
        log('  - ${parts[2]}');
      }
    }
  }
}