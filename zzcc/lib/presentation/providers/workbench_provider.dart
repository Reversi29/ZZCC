import 'dart:io';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter/services.dart';
import 'dart:async';
import 'package:zzcc/data/models/file_tree_model.dart';
import 'package:zzcc/core/services/net_service.dart';
import 'package:get_it/get_it.dart';
import 'package:zzcc/core/services/storage_service.dart';
import 'package:zzcc/core/di/service_locator.dart';
import 'dart:convert';
import 'package:charset_converter/charset_converter.dart';

final workbenchProvider = ChangeNotifierProvider((ref) => WorkbenchProvider());

class GitCommit {
  final String id;
  final String author;
  final String message;
  final DateTime date;

  GitCommit({
    required this.id,
    required this.author,
    required this.message,
    required this.date,
  });
}

enum SidebarContent {
  git,
  outline,
  search,
  debug
}

class OpenedFile {
  final String path;
  String content;
  final Uint8List? bytes;
  bool isModified;
  /// The content as it was on disk when opened or last saved. Used to
  /// determine whether the displayed content differs from the file's
  /// actual content (so cursor movement/selection won't mark modified).
  String originalContent;

  OpenedFile copyWith({String? content, bool? isModified, String? originalContent}) {
    return OpenedFile(
      path: path,
      content: content ?? this.content,
      bytes: bytes,
      isModified: isModified ?? this.isModified,
      originalContent: originalContent ?? this.originalContent,
    );
  }

  OpenedFile({
    required this.path,
    required this.content,
    this.bytes,
    this.isModified = false,
    this.originalContent = '',
  });
}

class WorkbenchProvider extends ChangeNotifier {
  String _currentFilePath = '';
  String _currentFileContent = '';
  Uint8List? _currentFileBytes;
  final String _currentBranch = 'main';
  final List<GitCommit> _commits = [];
  bool _isLoading = false;
  List<OpenedFile> _openedFiles = [];
  int _activeFileIndex = -1;
  // bool _isFileTreeVisible = true;
  bool _isSidebarVisible = true;
  int _activeSidebarTab = 0;
  double _sidebarWidth = 250;
  List<FileNode> _fileTree = [];
  String? _currentFolderPath;
  bool _isSettingsOpen = false;
  final Map<String, Duration> _audioPositions = {};
  Timer? _fileWatcherTimer;
  bool _fileTreeNeedsRefresh = false;
  final ApiService _apiService = GetIt.I<ApiService>();
  // Editor status
  int _editorLine = 1;
  int _editorColumn = 1;
  int _selectionCount = 0;
  String _encoding = 'utf-8';
  String _firstLineIndent = '';

  String get encoding => _encoding;

  int get editorLine => _editorLine;
  int get editorColumn => _editorColumn;
  int get selectionCount => _selectionCount;
  String get firstLineIndent => _firstLineIndent;

  /// Change decoding encoding for current file and attempt to re-decode
  /// the file content using the selected encoding.
  Future<void> setEncoding(String enc) async {
    _encoding = enc;
    // If there's an active file that's a text file, attempt decode
    if (_activeFileIndex >= 0 && _activeFileIndex < _openedFiles.length) {
      final of = _openedFiles[_activeFileIndex];
      try {
        final f = File(of.path);
        if (await f.exists()) {
          final bytes = await f.readAsBytes();
          try {
            final decoded = await CharsetConverter.decode(enc, bytes);
            of.content = decoded;
            // Do not change originalContent when re-decoding — originalContent
            // remains the on-disk/last-saved content in original encoding.
            // Mark modified only if decoded text differs from originalContent
            of.isModified = (of.content != of.originalContent);
            _currentFileContent = of.content;
            notifyListeners();
          } catch (e) {
            // decoding failed, keep existing content
            debugPrint('Decoding failed for encoding $enc: $e');
          }
        }
      } catch (e) {
        debugPrint('Failed to set encoding: $e');
      }
    }
    notifyListeners();
  }

  /// Update editor cursor/selection and metadata. Called by editor widgets.
  void updateEditorStatus({required int line, required int column, required int selectionCount, String? encoding, String? firstLineIndent}) {
    _editorLine = line;
    _editorColumn = column;
    _selectionCount = selectionCount;
    if (encoding != null) _encoding = encoding;
    if (firstLineIndent != null) _firstLineIndent = firstLineIndent;
    notifyListeners();
  }
  

  String get currentFilePath => _currentFilePath;
  String get currentFileContent => _currentFileContent;
  Uint8List? get currentFileBytes => _currentFileBytes;
  String get currentBranch => _currentBranch;
  List<GitCommit> get commits => _commits;
  bool get isLoading => _isLoading;
  bool get isSidebarVisible => _isSidebarVisible;
  int get activeSidebarTab => _activeSidebarTab;
  double get sidebarWidth => _sidebarWidth;
  List<OpenedFile> get openedFiles => _openedFiles;
  int get activeFileIndex => _activeFileIndex;
  List<FileNode> get fileTree => _fileTree;
  String? get currentFolderPath => _currentFolderPath;
  bool get isSettingsOpen => _isSettingsOpen;
  bool get fileTreeNeedsRefresh => _fileTreeNeedsRefresh;

  Future<void> initialize() async {
    _isLoading = true;
    notifyListeners();
    
    await Future.delayed(const Duration(milliseconds: 500));
    
    _openedFiles = [
      OpenedFile(path: "文件1.dart", content: "// 示例代码"),
      OpenedFile(path: "文件2.dart", content: "// 示例代码"),
    ];
    _activeFileIndex = 0;
    
    _isLoading = false;
    notifyListeners();
  }

  void setFileTree(List<FileNode> newFileTree) {
    _fileTree = newFileTree;
    notifyListeners();
  }
  
  void toggleSidebar(int tabIndex) {
    if (_isSidebarVisible && _activeSidebarTab == tabIndex) {
      _isSidebarVisible = false;
    } else {
      _isSidebarVisible = true;
      _activeSidebarTab = tabIndex;
    }
    notifyListeners();
  }
  
  void updateSidebarWidth(double width) {
    final newWidth = width.clamp(120.0, 400.0);
    if (_sidebarWidth != newWidth) {
      _sidebarWidth = newWidth;
      notifyListeners();
    }
  }

  Future<void> openFile(BuildContext context) async {
    try {
      FilePickerResult? result = await FilePicker.platform.pickFiles();
      if (result != null && result.files.single.path != null) {
        final filePath = result.files.single.path!;
        await openFileByName(filePath);
      }
    } catch (e) {
      debugPrint('打开文件失败: $e');
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('打开文件失败: $e')),
        );
      }
    }
  }

  Future<void> loadFileTree(String rootPath) async {
    try {
      _isLoading = true;
      notifyListeners();
      
      // 使用API调用替换原有本地遍历
      final response = await _apiService.getFileTree(rootPath);
      
      if (response.code == 200 && response.data != null) {
        // 使用API返回的数据
        setFileTree(response.data!.nodes);
        _currentFolderPath = response.data!.rootPath ?? rootPath;
      } else {
        throw Exception('Failed to load file tree: ${response.message}');
      }
    } catch (e) {
      debugPrint('加载文件树失败: $e');
      _fileTree = [];
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }
  
  Future<List<FileNode>> _traverseDirectory(Directory dir, {int depth = 0}) async {
    final List<FileNode> nodes = [];
    
    await for (var entity in dir.list()) {
      try {
        final stat = await entity.stat();
        final isDirectory = stat.type == FileSystemEntityType.directory;
        
        final node = FileNode(
          name: entity.path.split(Platform.pathSeparator).last,
          path: entity.path,
          isDirectory: isDirectory,
          depth: depth,
        );
        
        if (isDirectory) {
          node.children = await _traverseDirectory(
            Directory(entity.path), 
            depth: depth + 1
          );
        }
        
        nodes.add(node);
      } catch (e) {
        debugPrint('访问文件失败: ${entity.path} - $e');
      }
    }
    
    nodes.sort((a, b) {
      if (a.isDirectory && !b.isDirectory) return -1;
      if (!a.isDirectory && b.isDirectory) return 1;
      return a.name.compareTo(b.name);
    });
    
    return nodes;
  }

  void expandDirectory(String path) {
    bool shouldNotify = false;
    
    for (final node in _fileTree) {
      if (_expandNode(node, path)) {
        shouldNotify = true;
      }
    }
    
    if (shouldNotify) {
      notifyListeners();
    }
  }

  bool _expandNode(FileNode node, String path) {
    bool changed = false;
    
    if (node.path == path && node.isDirectory) {
      // 切换展开状态
      node.isExpanded = !node.isExpanded;
      changed = true;
      
      // 如果是第一次展开且子节点为空，则加载子节点
      if (node.isExpanded && node.children.isEmpty) {
        node.isExpanded = true; // 确保保持展开状态
        _loadDirectoryChildren(node).then((_) {
          notifyListeners(); // 加载完成后刷新UI
        });
      }
    } else if (node.isDirectory && node.children.isNotEmpty) {
      // 递归检查子节点
      for (final child in node.children) {
        if (_expandNode(child, path)) {
          changed = true;
        }
      }
    }
    
    return changed;
  }

  Future<void> _loadDirectoryChildren(FileNode node) async {
    try {
      final dir = Directory(node.path);
      node.children = await _traverseDirectory(dir);
    } catch (e) {
      debugPrint('加载子目录失败: ${node.path} - $e');
      node.children = [];
    }
  }
  
  void fileTreeRefreshed() {
    _fileTreeNeedsRefresh = false;
  }
  
  Future<void> refreshFileTree() async {
    if (_currentFolderPath != null) {
      _isLoading = true;
      // 只通知文件树需要刷新，不触发整个工作台刷新
      _fileTreeNeedsRefresh = true;
      
      try {
        // 1. 保存当前所有节点状态
        final Map<String, bool> expandedStateMap = {};
        if (_fileTree.isNotEmpty) {
          _collectExpandedState(_fileTree, expandedStateMap);
        }
        
        final dir = Directory(_currentFolderPath!);
        final children = await _traverseDirectory(dir);
        
        // 2. 重建根节点
        final rootNode = FileNode(
          name: dir.path.split(Platform.pathSeparator).last,
          path: dir.path,
          isDirectory: true,
          isExpanded: expandedStateMap[dir.path] ?? true, // 默认展开
          children: children,
        );
        
        // 3. 应用保存的展开状态
        _applyExpandedState(rootNode, expandedStateMap);
        
        _fileTree = [rootNode];
      } catch (e) {
        debugPrint('刷新文件树失败: $e');
      } finally {
        _isLoading = false;
        _fileTreeNeedsRefresh = false;
        notifyListeners();
      }
    }
  }
  
  // 递归收集所有节点展开状态
  void _collectExpandedState(List<FileNode> nodes, Map<String, bool> stateMap) {
    for (final node in nodes) {
      if (node.isDirectory) {
        stateMap[node.path] = node.isExpanded;
        _collectExpandedState(node.children, stateMap);
      }
    }
  }
  
  // 递归应用所有节点展开状态
  void _applyExpandedState(FileNode node, Map<String, bool> stateMap) {
    if (stateMap.containsKey(node.path)) {
      node.isExpanded = stateMap[node.path]!;
    }
    
    for (final child in node.children) {
      _applyExpandedState(child, stateMap);
    }
  }

  @override
  void dispose() {
    _fileWatcherTimer?.cancel();
    super.dispose();
  }

  Future<void> watchFileSystem(String rootPath) async {
    _fileWatcherTimer?.cancel();
    
    _fileWatcherTimer = Timer.periodic(const Duration(seconds: 5), (timer) {
      if (_currentFolderPath != null) {
        refreshFileTree();
      }
    });
  }

  Future<void> openFolder(BuildContext context) async {
    try {
      _isLoading = true;
      notifyListeners();
      
      final directory = await FilePicker.platform.getDirectoryPath();
      if (directory != null) {
        _currentFilePath = '';
        _currentFileContent = '';
        _currentFileBytes = null;
        _currentFolderPath = directory;

        watchFileSystem(directory);
        
        // 确保根目录节点存在
        if (_fileTree.isEmpty || _fileTree[0].path != directory) {
          final rootNode = FileNode(
            name: directory.split(Platform.pathSeparator).last,
            path: directory,
            isDirectory: true,
            isExpanded: true,
          );
          setFileTree([rootNode]); // 使用新方法设置文件树
        }
        
        // 刷新文件树
        await refreshFileTree();
        
        if (context.mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('已打开文件夹: $directory')),
          );
        }
      }
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('打开文件夹失败: $e')),
        );
      }
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  void updateCurrentFileContent(String content) {
    _currentFileContent = content;
    if (_activeFileIndex != -1) {
      final of = _openedFiles[_activeFileIndex];
      of.content = content;
      of.isModified = (of.content != of.originalContent);
    }
    notifyListeners();
  }

  Future<void> createNewFile() async {
    try {
      if (_currentFolderPath == null) return;
      
      // 创建唯一的文件名称
      String newFileName = '新建文件.txt';
      int counter = 1;
      
      while (await File('$_currentFolderPath/$newFileName').exists()) {
        newFileName = '新建文件($counter).txt';
        counter++;
      }
      
      final newFile = File('$_currentFolderPath/$newFileName');
      await newFile.writeAsString('// 新文件');
      
      // 刷新文件树
      await refreshFileTree();
    } catch (e) {
      debugPrint('创建文件失败: $e');
    }
  }

  Future<void> createNewDirectory() async {
    try {
      if (_currentFolderPath == null) return;
      
      // 创建唯一的文件夹名称
      String newDirName = '新建文件夹';
      int counter = 1;
      
      while (await Directory('$_currentFolderPath/$newDirName').exists()) {
        newDirName = '新建文件夹($counter)';
        counter++;
      }
      
      final newDir = Directory('$_currentFolderPath/$newDirName');
      await newDir.create();
      
      // 刷新文件树
      await refreshFileTree();
    } catch (e) {
      debugPrint('创建文件夹失败: $e');
    }
  }

  void updateFileContent(String content) {
    _currentFileContent = content;
    if (_activeFileIndex != -1) {
      final of = _openedFiles[_activeFileIndex];
      of.content = content;
      of.isModified = (of.content != of.originalContent);
    }
    notifyListeners();
  }
  
  Future<void> openFileByName(String path) async {
    try {
      _isLoading = true;
      notifyListeners();
      
      final normalizedPath = _normalizePath(path);
      final existingIndex = _openedFiles.indexWhere((f) => _normalizePath(f.path) == normalizedPath);
      if (existingIndex >= 0) {
        setActiveFile(existingIndex);
        _isLoading = false;
        notifyListeners();
        return;
      }
      
      final file = File(path);
      String content = '';
      Uint8List? bytes;
      final ext = path.toLowerCase().split('.').last;
      
      // 修复：添加文件存在性检查
      if (!await file.exists()) {
        throw Exception('文件不存在');
      }

      debugPrint('文件类型: $ext, 内容长度: ${content.length}');
      
      // 文本文件类型
      if (const [
        'dart', 'py', 'c', 'cpp', 'h', 'hpp', 'java', 'js', 'ts', 
        'lua', 'go', 'rs', 'php', 'html', 'css', 'xml', 'json', 
        'yaml', 'yml', 'md', 'txt', 'log', 'ini', 'conf', 'cfg', 'env',
      ].contains(ext)) {
        try {
          final fileLength = await file.length();
          const largeFileThreshold = 2 * 1024 * 1024; // 2 MB

          if (fileLength > largeFileThreshold) {
            // Create opened file entry immediately and stream content in chunks
            _openedFiles.add(OpenedFile(
              path: normalizedPath,
              content: '',
              bytes: null,
              isModified: false,
            ));
            setActiveFile(_openedFiles.length - 1);

            final stream = file.openRead().transform(utf8.decoder);
            final buffer = StringBuffer();
            int chunkCount = 0;
            await for (final chunk in stream) {
              buffer.write(chunk);
              chunkCount++;
              // update UI every 20 chunks to avoid too many rebuilds
              if (chunkCount % 20 == 0) {
                final idx = _activeFileIndex;
                if (idx >= 0 && idx < _openedFiles.length) {
                  _openedFiles[idx] = _openedFiles[idx].copyWith(content: buffer.toString());
                  _currentFileContent = buffer.toString();
                  notifyListeners();
                }
              }
            }

            content = buffer.toString();
          } else {
            content = await file.readAsString();
          }
        } catch (e) {
          debugPrint('流式读取失败或编码问题，回退到一次性读取: $e');
          content = await file.readAsString();
        }
      } 
      // 图片文件类型
      else if (const [
        'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'ico', 'jfif'
      ].contains(ext)) {
        bytes = await file.readAsBytes();
      } 
      // 媒体文件类型（包括视频）
      else if (const [
        'mp3', 'wav', 'flac', 'aac', 'ogg', 'm4a', 'mp4', 'mov', 'avi', 'mkv', 'webm'
      ].contains(ext)) {
        // 对于媒体文件，不读取字节数据（因为文件可能很大）媒体播放器会使用文件路径直接播放
        // bytes = await file.readAsBytes();
        content = ''; // 设置空内容
      } 
      // 数据库文件类型
      else if (const ['hive',].contains(ext)) {
        final storageService = getIt<StorageService>();
        final result = await storageService.readExternalHiveFile(path);
        if (result['success']) {
          content = const JsonEncoder.withIndent('  ').convert(result['data']);
        } else {
          content = result['message'];
        }
      }
      // 其他文件类型
      else {
        try {
          content = await file.readAsString();
        } catch (e) {
          bytes = await file.readAsBytes();
        }
      }
      
      // If streaming already created the opened file entry, update it; otherwise add.
      final alreadyIndex = _openedFiles.indexWhere((f) => f.path == normalizedPath);
      if (alreadyIndex >= 0) {
        _openedFiles[alreadyIndex] = _openedFiles[alreadyIndex].copyWith(content: content, isModified: false, originalContent: content);
        setActiveFile(alreadyIndex);
      } else {
        _openedFiles.add(OpenedFile(
          path: normalizedPath,
          content: content,
          bytes: bytes,
          isModified: false,
          originalContent: content,
        ));
        setActiveFile(_openedFiles.length - 1);
      }
      
      notifyListeners();
    } catch (e) {
      debugPrint('打开文件失败: $e');
      _openedFiles.add(OpenedFile(
        path: path,
        content: '无法打开文件: $e',
        bytes: null,
      ));
      setActiveFile(_openedFiles.length - 1);
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  String _normalizePath(String path) {
    // 统一路径分隔符
    String normalized = path.replaceAll(RegExp(r'[\\/]+'), Platform.pathSeparator);
    
    // 解析为绝对路径
    if (path.isNotEmpty && !path.startsWith(Platform.pathSeparator)) {
      normalized = File(path).absolute.path;
    }
    
    // 在 Windows 上统一为小写
    if (Platform.isWindows) {
      normalized = normalized.toLowerCase();
    }
    
    return normalized;
  }

  void closeFile(int index) {
    if (index < 0 || index >= _openedFiles.length) return;
    
    final wasActiveFile = _activeFileIndex == index;
    final wasSettings = _openedFiles[index].path == 'settings://';
    
    _openedFiles.removeAt(index);
    
    if (wasSettings) {
      _isSettingsOpen = false;
    }
    
    if (_openedFiles.isEmpty) {
      _activeFileIndex = -1;
      _currentFilePath = '';
      _currentFileContent = '';
      _currentFileBytes = null;
    } else {
      if (wasActiveFile) {
        _activeFileIndex = index < _openedFiles.length ? index : _openedFiles.length - 1;
        
        final OpenedFile newActiveFile = _openedFiles[_activeFileIndex];
        _currentFilePath = newActiveFile.path;
        _currentFileContent = newActiveFile.content;
        _currentFileBytes = newActiveFile.bytes;
      } else if (_activeFileIndex > index) {
        _activeFileIndex--;
      }
    }
    
    notifyListeners();
  }

  Future<void> closeFolder() async {
    _currentFolderPath = null;
    _fileTree = [];
    notifyListeners();
    
    while (_openedFiles.isNotEmpty) {
      closeFile(0);
    }
  }

  Future<void> _saveAsNewFile(BuildContext context) async {
    try {
      final result = await FilePicker.platform.saveFile(
        dialogTitle: '保存文件',
        fileName: 'new_file.txt',
        allowedExtensions: ['txt', 'dart'],
      );
      
      if (result != null && context.mounted) {
        _currentFilePath = result;
        await saveCurrentFile(context);
      }
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('保存失败: $e')),
        );
      }
    }
  }

  Future<void> saveCurrentFile(BuildContext context) async {
    if (_currentFilePath.isEmpty) {
      return _saveAsNewFile(context);
    }
    
    try {
      _isLoading = true;
      notifyListeners();
      
      final file = File(_currentFilePath);
      if (_currentFilePath.toLowerCase().endsWith('.txt') || 
          _currentFilePath.toLowerCase().endsWith('.dart')) {
        await file.writeAsString(_currentFileContent);
      } else if (_currentFileBytes != null) {
        await file.writeAsBytes(_currentFileBytes!);
      }
      
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('文件已保存')),
        );
      }
      // mark current opened file as saved
      if (_activeFileIndex >= 0 && _activeFileIndex < _openedFiles.length) {
        final of = _openedFiles[_activeFileIndex];
        of.isModified = false;
        of.originalContent = _currentFileContent;
      }
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('保存失败: $e')),
        );
      }
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> saveFile(String path, String content) async {
    try {
      final file = File(path);
      await file.writeAsString(content);
      // clear modified flag for matching opened file
      final idx = _openedFiles.indexWhere((f) => f.path == _normalizePath(path));
      if (idx >= 0) {
        _openedFiles[idx].isModified = false;
        _openedFiles[idx].originalContent = content;
      }
    } catch (e) {
      debugPrint('文件保存失败: $e');
      rethrow;
    }
  }

  Future<String> readFile(String path) async {
    try {
      return await File(path).readAsString();
    } catch (e) {
      debugPrint('文件读取失败: $e');
      return '';
    }
  }
  
  Future<void> saveAllFiles(BuildContext context) async {
    try {
      for (final _ in _openedFiles) {
        await Future.delayed(const Duration(milliseconds: 100));
      }
      
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('所有文件已保存')),
        );
      }
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('保存失败: $e')),
        );
      }
    }
  }

  void openSettings() {
    _isSettingsOpen = true;
    
    final existingIndex = _openedFiles.indexWhere((f) => f.path == 'settings://');
    if (existingIndex >= 0) {
      setActiveFile(existingIndex);
    } else {
      _openedFiles.add(OpenedFile(
        path: 'settings://',
        content: '工作台设置',
      ));
      setActiveFile(_openedFiles.length - 1);
    }
  }
  
  void closeSettings() {
    _isSettingsOpen = false;
    final index = _openedFiles.indexWhere((f) => f.path == 'settings://');
    if (index >= 0) {
      closeFile(index);
    }
  }

  void setActiveFile(int index) {
    if (index >= 0 && index < _openedFiles.length) {
      _activeFileIndex = index;
      final file = _openedFiles[index];
      _currentFilePath = file.path;
      _currentFileContent = file.content;
      _currentFileBytes = file.bytes;
      notifyListeners();
      // If the file is a Hive file, refresh its content from storage in case
      // the on-disk representation changed or was loaded lazily.
      _refreshOpenedFileContentIfNeeded(index);
    }
  }

  void _refreshOpenedFileContentIfNeeded(int index) async {
    if (index < 0 || index >= _openedFiles.length) return;
    final file = _openedFiles[index];
    final path = file.path;
    final ext = path.toLowerCase().split('.').last;
    if (ext == 'hive') {
      try {
        final storageService = getIt<StorageService>();
        final result = await storageService.readExternalHiveFile(path);
        if (result['success'] == true) {
          final newContent = const JsonEncoder.withIndent('  ').convert(result['data']);
          file.content = newContent;
          // If this is still the active file, update cached current content
          if (_activeFileIndex == index) {
            _currentFileContent = newContent;
            notifyListeners();
          }
        }
      } catch (e) {
        debugPrint('Failed to refresh hive content for $path: $e');
      }
    }
  }

  String getFileName(String path) {
    if (path == 'settings://') return ' 设置';
    
    final fileName = _extractFileName(path);
    final sameNameCount = openedFiles
        .where((f) => f.path != path && _extractFileName(f.path) == fileName)
        .length;
    
    if (sameNameCount > 0) {
      final segments = path.split(RegExp(r'[\\\/]'));
      if (segments.length > 2) {
        return '${segments[segments.length - 2]}${Platform.pathSeparator}$fileName';
      }
    }
    return fileName;
  }

  String _extractFileName(String path) {
    if (path == 'settings://') return ' 设置';
    final segments = path.split(RegExp(r'[\\\/]'));
    return segments.last;
  }

  // 保存音频位置
  void saveAudioPosition(String path, Duration position) {
    _audioPositions[path] = position;
    // 不需要通知监听器，因为UI不会立即响应这个变化
  }

  // Keep references to active editor controllers so menu actions can operate
  // on the focused editor (cut/copy/paste).
  final Map<String, TextEditingController> _editorControllers = {};

  void registerEditorController(String path, TextEditingController controller) {
    _editorControllers[_normalizePath(path)] = controller;
  }

  void unregisterEditorController(String path) {
    _editorControllers.remove(_normalizePath(path));
  }

  Future<void> performEditAction(String action) async {
    try {
      final path = _currentFilePath;
      if (path.isEmpty) return;
      final key = _normalizePath(path);
      final controller = _editorControllers[key];
      if (controller == null) return;

      final sel = controller.selection;
      final start = sel.start.clamp(0, controller.text.length);
      final end = sel.end.clamp(0, controller.text.length);

      switch (action) {
        case 'cut':
          final selected = controller.text.substring(start, end);
          await Clipboard.setData(ClipboardData(text: selected));
          controller.text = controller.text.replaceRange(start, end, '');
          controller.selection = TextSelection.collapsed(offset: start);
          break;
        case 'copy':
          final selected = controller.text.substring(start, end);
          await Clipboard.setData(ClipboardData(text: selected));
          break;
        case 'paste':
          final data = await Clipboard.getData('text/plain');
          final insert = data?.text ?? '';
          controller.text = controller.text.replaceRange(start, end, insert);
          controller.selection = TextSelection.collapsed(offset: start + insert.length);
          break;
        case 'undo':
          // Best-effort: if controller supports undo, try calling it.
          try {
            final maybe = controller as dynamic;
            if (maybe.undo != null) maybe.undo();
          } catch (_) {}
          break;
        case 'redo':
          try {
            final maybe = controller as dynamic;
            if (maybe.redo != null) maybe.redo();
          } catch (_) {}
          break;
      }
    } catch (e) {
      debugPrint('Edit action failed: $e');
    }
  }

  // 获取音频位置
  Duration? getAudioPosition(String path) {
    return _audioPositions[path];
  }
}