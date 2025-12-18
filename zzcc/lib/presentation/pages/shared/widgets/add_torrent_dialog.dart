import 'package:flutter/material.dart';
import 'package:file_picker/file_picker.dart';
import 'package:zzcc/data/models/torrent_file.dart';
import 'package:zzcc/presentation/providers/shared_file_settings_provider.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:zzcc/core/services/torrent_metadata_service.dart';
import 'package:zzcc/core/di/service_locator.dart';
import 'package:zzcc/core/services/logger_service.dart';

class AddTorrentDialog extends StatefulWidget {
  final String torrentPath;
  final String? defaultSavePath;
  final String? lastUsedPath;
  final String? incompleteTorrentPath;
  final bool? defaultIsManualMode;
  final bool? defaultUseDifferentIncompletePath;
  final bool? defaultRememberLastPath;

  const AddTorrentDialog({
    super.key,
    required this.torrentPath,
    this.defaultSavePath,
    this.lastUsedPath,
    this.incompleteTorrentPath,
    this.defaultIsManualMode,
    this.defaultUseDifferentIncompletePath,
    this.defaultRememberLastPath,
  });

  @override
  State<AddTorrentDialog> createState() => _AddTorrentDialogState();
}

class _AddTorrentDialogState extends State<AddTorrentDialog> {
  // 管理模式
  late bool _isManualMode;

  // 保存路径设置
  late TextEditingController _savePathController;
  late bool _useDifferentIncompletePath;
  late TextEditingController _incompletePathController;
  late bool _rememberLastPath;

  String? _selectedCategory;
  bool _setAsDefaultCategory = false;
  final TextEditingController _tagsController = TextEditingController();
  bool _startTorrent = true;
  String? _stopCondition;
  bool _addToTopOfQueue = false;
  bool _skipHashCheck = false;
  bool _downloadInOrder = false;
  bool _downloadFirstLastPieces = false;
  String? _contentLayout;

  String _torrentName = '';
  String _torrentSize = '';
  int _fileCount = 0;
  String? _torrentComment;
  String? _torrentCreator;
  List<TorrentFile> _torrentFiles = [];
  bool _isLoading = false;
  bool _neverShowAgain = false;

  final List<String> _categories = ['视频', '音乐', '文档', '软件', '游戏'];
  final List<String> _stopConditions = ['从不', '达到分享率', '达到种子时间', '达到分享率或种子时间'];
  final List<String> _contentLayouts = ['原始', '创建子文件夹', '平展'];
  
  final LoggerService _logger = getIt<LoggerService>();

  @override
  void initState() {
    super.initState();
    
    // 初始化控制器，优先使用lastUsedPath
    _savePathController = TextEditingController(
      text: (widget.lastUsedPath?.isNotEmpty ?? false) 
        ? widget.lastUsedPath 
        : widget.defaultSavePath ?? ''
    );
    
    // 初始化不完整文件路径
    _incompletePathController = TextEditingController(
      text: widget.incompleteTorrentPath ?? ''
    );
    
    // 从参数初始化配置
    _isManualMode = widget.defaultIsManualMode ?? true;
    _useDifferentIncompletePath = widget.defaultUseDifferentIncompletePath ?? false;
    _rememberLastPath = widget.defaultRememberLastPath ?? true;

    // 加载Torrent信息
    _loadTorrentInfo();
  }

  @override
  void dispose() {
    _savePathController.dispose();
    _incompletePathController.dispose();
    _tagsController.dispose();
    super.dispose();
  }

  Future<void> _loadTorrentInfo() async {
    try {
      setState(() => _isLoading = true);
      
      final metadataService = getIt<TorrentMetadataService>();
      Map<String, dynamic> metadata;
      
      if (widget.torrentPath.startsWith('magnet:')) {
        metadata = await metadataService.parseMagnetLink(widget.torrentPath);
      } else {
        metadata = await metadataService.parseTorrentFile(widget.torrentPath);
      }

      setState(() {
        _torrentName = metadata['name'] as String;
        _torrentComment = metadata['comment'] as String? ?? '';
        _torrentCreator = metadata['created by'] as String? ?? '';
        _fileCount = (metadata['files'] as List).length;
        _torrentSize = _formatSize(metadata['length'] as int);
        _torrentFiles = _buildFileTree(metadata['files'] as List<dynamic>);
      });
    } catch (e) {
      _logger.error('加载Torrent元数据失败: $e');
      if (mounted) {
        String errorMsg = '加载失败';
        if (e.toString().contains('type cast')) {
          errorMsg = 'Torrent文件格式错误：不支持的类型格式';
        } else if (e.toString().contains('FormatException')) {
          errorMsg = 'Torrent文件损坏或格式不正确';
        } else if (e.toString().contains('infoHash')) {
          errorMsg = '磁力链接格式错误，无法提取infoHash';
        } else {
          errorMsg = '加载Torrent信息失败: $e';
        }
        
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(errorMsg), backgroundColor: Colors.red),
        );
      }
    } finally {
      if (mounted) {
        setState(() => _isLoading = false);
      }
    }
  }

  List<Widget> _buildFileWidgets() {
    return _torrentFiles.map((file) {
      return ListTile(
        title: Text(file.name),
        subtitle: Text(file.size),
        leading: Checkbox(
          value: file.selected,
          onChanged: (value) => _toggleFileSelection(file.id, value),
        ),
        trailing: file.isFolder ? const Icon(Icons.folder) : const Icon(Icons.file_copy),
      );
    }).toList();
  }

  // 构建文件树结构的辅助方法
  List<TorrentFile> _buildFileTree(List<dynamic> fileEntries) {
    return fileEntries.map((entry) {
      final entryMap = entry as Map<String, dynamic>;
      final length = (entryMap['length'] as int);
      return TorrentFile(
        id: DateTime.now().microsecondsSinceEpoch.toString(),
        name: entryMap['name'] as String,
        size: _formatSize(length),
        length: length,
        selected: true,
        isFolder: false,
      );
    }).toList();
  }

  // 生成唯一文件ID
  // String _generateFileId() {
  //   return DateTime.now().microsecondsSinceEpoch.toString();
  // }

  // 格式化文件大小
  String _formatSize(int bytes) {
    if (bytes >= 1024 * 1024 * 1024) {
      return '${(bytes / (1024 * 1024 * 1024)).toStringAsFixed(2)} GB';
    } else if (bytes >= 1024 * 1024) {
      return '${(bytes / (1024 * 1024)).toStringAsFixed(2)} MB';
    } else if (bytes >= 1024) {
      return '${(bytes / 1024).toStringAsFixed(2)} KB';
    } else {
      return '$bytes B';
    }
  }

  // 计算文件夹总大小
  // String _calculateFolderSize(List<TorrentFile> files) {
  //   int totalBytes = 0;
    
  //   for (var file in files) {
  //     final sizeMatch = RegExp(r'(\d+\.?\d*)\s*([KMG])B').firstMatch(file.size);
  //     if (sizeMatch != null) {
  //       final num = double.parse(sizeMatch.group(1)!);
  //       final unit = sizeMatch.group(2);
        
  //       switch (unit) {
  //         case 'K': totalBytes += (num * 1024).toInt(); break;
  //         case 'M': totalBytes += (num * 1024 * 1024).toInt(); break;
  //         case 'G': totalBytes += (num * 1024 * 1024 * 1024).toInt(); break;
  //         default: totalBytes += num.toInt();
  //       }
  //     }
  //   }
    
  //   return _formatSize(totalBytes);
  // }

  // void _calculateTotalSizeAndCount() {
  //   int fileCount = 0;
  //   int totalBytes = 0;
    
  //   void traverseFiles(List<TorrentFile> files) {
  //     for (var file in files) {
  //       if (file.isFolder && file.children.isNotEmpty) {
  //         traverseFiles(file.children);
  //       } else {
  //         fileCount++;
  //         final sizeMatch = RegExp(r'(\d+\.?\d*)\s*([KMG])B').firstMatch(file.size);
  //         if (sizeMatch != null) {
  //           final num = double.parse(sizeMatch.group(1)!);
  //           final unit = sizeMatch.group(2);
            
  //           switch (unit) {
  //             case 'K': totalBytes += (num * 1024).toInt(); break;
  //             case 'M': totalBytes += (num * 1024 * 1024).toInt(); break;
  //             case 'G': totalBytes += (num * 1024 * 1024 * 1024).toInt(); break;
  //           }
  //         }
  //       }
  //     }
  //   }
    
  //   traverseFiles(_torrentFiles);
  //   _fileCount = fileCount;
    
  //   if (totalBytes >= 1024 * 1024 * 1024) {
  //     _torrentSize = '${(totalBytes / (1024 * 1024 * 1024)).toStringAsFixed(2)} GB';
  //   } else if (totalBytes >= 1024 * 1024) {
  //     _torrentSize = '${(totalBytes / (1024 * 1024)).toStringAsFixed(2)} MB';
  //   } else if (totalBytes >= 1024) {
  //     _torrentSize = '${(totalBytes / 1024).toStringAsFixed(2)} KB';
  //   } else {
  //     _torrentSize = '$totalBytes B';
  //   }
  // }

  Future<void> _selectSavePath() async {
    String? path = await FilePicker.platform.getDirectoryPath();
    if (path != null) {
      _savePathController.text = path;
    }
  }

  Future<void> _selectIncompletePath() async {
    String? path = await FilePicker.platform.getDirectoryPath();
    if (path != null) {
      _incompletePathController.text = path;
    }
  }

  void _toggleFileSelection(String fileId, bool? value) {
    setState(() {
      final index = _torrentFiles.indexWhere((f) => f.id == fileId);
      if (index != -1) {
        _torrentFiles[index] = _torrentFiles[index].copyWith(
          selected: value ?? false,
        );
      }
    });
  }

  // bool _updateFileSelection(List<TorrentFile> files, String fileId, bool selected) {
  //   for (var i = 0; i < files.length; i++) {
  //     if (files[i].id == fileId) {
  //       files[i].selected = selected;
        
  //       if (files[i].isFolder && files[i].children.isNotEmpty) {
  //         _updateChildrenSelection(files[i].children, selected);
  //       }
  //       return true;
  //     }
      
  //     if (files[i].isFolder && files[i].children.isNotEmpty) {
  //       bool found = _updateFileSelection(files[i].children, fileId, selected);
  //       if (found) {
  //         files[i].selected = files[i].children.every((child) => child.selected);
  //         return true;
  //       }
  //     }
  //   }
  //   return false;
  // }

  // void _updateChildrenSelection(List<TorrentFile> children, bool selected) {
  //   for (var child in children) {
  //     child.selected = selected;
  //     if (child.isFolder && child.children.isNotEmpty) {
  //       _updateChildrenSelection(child.children, selected);
  //     }
  //   }
  // }

  void _submit() {
    if (_savePathController.text.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('请选择保存路径')),
      );
      return;
    }
    
    List<String> selectedFileIds = [];
    void collectSelectedIds(List<TorrentFile> files) {
      for (var file in files) {
        if (file.selected && !file.isFolder) {
          selectedFileIds.add(file.id);
        }
        // 修复：添加空安全检查
        if (file.isFolder && file.children != null && file.children!.isNotEmpty) {
          collectSelectedIds(file.children!); // 添加非空断言
        }
      }
    }
    collectSelectedIds(_torrentFiles);
    // 计算已选中文件总字节数
    int selectedTotalBytes = 0;
    void accumulateSelected(List<TorrentFile> files) {
      for (var f in files) {
        if (f.selected && !f.isFolder) selectedTotalBytes += f.length;
        if (f.isFolder && f.children != null && f.children!.isNotEmpty) accumulateSelected(f.children!);
      }
    }
    accumulateSelected(_torrentFiles);
    final String selectedSizeReadable = _formatSize(selectedTotalBytes);
    
    // 核心修正：正确获取 Notifier
    final container = ProviderScope.containerOf(context);
    final settingsNotifier = container.read(sharedFileSettingsNotifierProvider.notifier);
    
    // 同步设置到本地存储
    settingsNotifier.updateIsManualMode(_isManualMode);
    settingsNotifier.updateUseDifferentIncompletePath(_useDifferentIncompletePath);
    settingsNotifier.updateRememberLastPath(_rememberLastPath);
    if (_rememberLastPath) {
      settingsNotifier.updateLastUsedPath(_savePathController.text);
    }
    if (_useDifferentIncompletePath) {
      settingsNotifier.updateIncompleteTorrentPath(_incompletePathController.text);
    }
    
    Navigator.of(context).pop({
      'isManualMode': _isManualMode,
      'savePath': _savePathController.text,
      'useDifferentIncompletePath': _useDifferentIncompletePath,
      'incompletePath': _incompletePathController.text,
      'rememberLastPath': _rememberLastPath,
      'category': _selectedCategory,
      'setAsDefaultCategory': _setAsDefaultCategory,
      'tags': _tagsController.text.split(',').map((e) => e.trim()).where((e) => e.isNotEmpty).toList(),
      'startTorrent': _startTorrent,
      'stopCondition': _stopCondition,
      'addToTopOfQueue': _addToTopOfQueue,
      'skipHashCheck': _skipHashCheck,
      'downloadInOrder': _downloadInOrder,
      'downloadFirstLastPieces': _downloadFirstLastPieces,
      'contentLayout': _contentLayout,
      'selectedFileIds': selectedFileIds,
      'selectedTotalBytes': selectedTotalBytes,
      'selectedSize': selectedSizeReadable,
      'neverShowAgain': _neverShowAgain,
    });
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
      ),
      insetPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 24),
      child: LayoutBuilder(
        builder: (context, constraints) {
          return ConstrainedBox(
            constraints: BoxConstraints(
              minHeight: constraints.minHeight * 0.9,
              maxHeight: constraints.maxHeight * 0.9,
              minWidth: constraints.minWidth * 0.9,
              maxWidth: constraints.maxWidth * 0.9,
            ),
            child: Column(
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                  decoration: BoxDecoration(
                    color: Theme.of(context).primaryColor,
                    borderRadius: const BorderRadius.only(
                      topLeft: Radius.circular(12),
                      topRight: Radius.circular(12),
                    ),
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text(
                        '添加 Torrent',
                        style: TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.bold,
                          color: Colors.white,
                        ),
                      ),
                      Row(
                        children: [
                          TextButton(
                            onPressed: () => Navigator.of(context).pop(),
                            style: TextButton.styleFrom(
                              foregroundColor: Colors.white,
                            ),
                            child: const Text('取消'),
                          ),
                          const SizedBox(width: 8),
                          ElevatedButton(
                            onPressed: _submit,
                            style: ElevatedButton.styleFrom(
                              backgroundColor: Colors.white,
                              foregroundColor: Theme.of(context).primaryColor,
                            ),
                            child: const Text('确定'),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
                
                Expanded(
                  child: SingleChildScrollView(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        _buildSectionTitle('Torrent 管理模式'),
                        const SizedBox(height: 8),
                        Row(
                          children: [
                            Radio<bool>(
                              value: true,
                              groupValue: _isManualMode,
                              onChanged: (value) => setState(() => _isManualMode = value!),
                            ),
                            const Text('手动模式'),
                            const SizedBox(width: 24),
                            Radio<bool>(
                              value: false,
                              groupValue: _isManualMode,
                              onChanged: (value) => setState(() => _isManualMode = value!),
                            ),
                            const Text('自动模式'),
                          ],
                        ),
                        const Divider(height: 24),
                        
                        _buildSectionTitle('保存位置'),
                        const SizedBox(height: 8),
                        
                        Row(
                          children: [
                            Expanded(
                              child: TextField(
                                controller: _savePathController,
                                readOnly: true,
                                enabled: _isManualMode,
                                decoration: InputDecoration(
                                  labelText: '保存路径',
                                  border: const OutlineInputBorder(),
                                  isDense: true,
                                  enabled: _isManualMode,
                                ),
                              ),
                            ),
                            const SizedBox(width: 8),
                            ElevatedButton(
                              onPressed: _isManualMode ? _selectSavePath : null,
                              style: ElevatedButton.styleFrom(
                                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                              ),
                              child: const Text('浏览...'),
                            ),
                          ],
                        ),
                        const SizedBox(height: 8),
                        
                        CheckboxListTile(
                          title: const Text('对不完整的Torrent使用另一个路径'),
                          value: _useDifferentIncompletePath,
                          onChanged: _isManualMode ? (value) => setState(() => _useDifferentIncompletePath = value!) : null,
                          controlAffinity: ListTileControlAffinity.leading,
                          contentPadding: EdgeInsets.zero,
                          dense: true,
                        ),
                        
                        Padding(
                          padding: const EdgeInsets.only(left: 16, right: 16, bottom: 8),
                          child: Row(
                            children: [
                              Expanded(
                                child: TextField(
                                  controller: _incompletePathController,
                                  readOnly: true,
                                  enabled: _isManualMode && _useDifferentIncompletePath,
                                  decoration: InputDecoration(
                                    labelText: '不完整文件路径',
                                    border: const OutlineInputBorder(),
                                    isDense: true,
                                    enabled: _isManualMode && _useDifferentIncompletePath,
                                  ),
                                ),
                              ),
                              const SizedBox(width: 8),
                              ElevatedButton(
                                onPressed: _isManualMode && _useDifferentIncompletePath ? _selectIncompletePath : null,
                                style: ElevatedButton.styleFrom(
                                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                                ),
                                child: const Text('浏览...'),
                              ),
                            ],
                          ),
                        ),
                        
                        CheckboxListTile(
                          title: const Text('记住上次使用的保存路径'),
                          value: _rememberLastPath,
                          onChanged: _isManualMode ? (value) => setState(() => _rememberLastPath = value!) : null,
                          controlAffinity: ListTileControlAffinity.leading,
                          contentPadding: EdgeInsets.zero,
                          dense: true,
                        ),
                        const Divider(height: 24),
                        
                        _buildSectionTitle('Torrent 选项'),
                        const SizedBox(height: 8),
                        
                        Row(
                          children: [
                            const Text('分类:'),
                            const SizedBox(width: 8),
                            Expanded(
                              child: DropdownButtonFormField<String>(
                                value: _selectedCategory,
                                items: _categories
                                    .map((category) => DropdownMenuItem(
                                          value: category,
                                          child: Text(category),
                                        ))
                                    .toList(),
                                onChanged: (value) => setState(() => _selectedCategory = value),
                                decoration: const InputDecoration(
                                  border: OutlineInputBorder(),
                                  isDense: true,
                                  hintText: '选择分类',
                                ),
                              ),
                            ),
                            const SizedBox(width: 8),
                            Checkbox(
                              value: _setAsDefaultCategory,
                              onChanged: (value) => setState(() => _setAsDefaultCategory = value!),
                            ),
                            const Text('设为默认'),
                          ],
                        ),
                        const SizedBox(height: 8),
                        
                        TextField(
                          controller: _tagsController,
                          decoration: InputDecoration(
                            labelText: '标签 (用逗号分隔)',
                            border: const OutlineInputBorder(),
                            isDense: true,
                            hintText: '例如: 重要,工作,个人',
                          ),
                        ),
                        const SizedBox(height: 8),
                        
                        CheckboxListTile(
                          title: const Text('添加后立即开始下载'),
                          value: _startTorrent,
                          onChanged: (value) => setState(() => _startTorrent = value!),
                          controlAffinity: ListTileControlAffinity.leading,
                          contentPadding: EdgeInsets.zero,
                          dense: true,
                        ),
                        
                        Row(
                          children: [
                            const Text('停止条件:'),
                            const SizedBox(width: 8),
                            Expanded(
                              child: DropdownButtonFormField<String>(
                                value: _stopCondition,
                                items: _stopConditions
                                    .map((condition) => DropdownMenuItem(
                                          value: condition,
                                          child: Text(condition),
                                        ))
                                    .toList(),
                                onChanged: (value) => setState(() => _stopCondition = value),
                                decoration: const InputDecoration(
                                  border: OutlineInputBorder(),
                                  isDense: true,
                                  hintText: '选择停止条件',
                                ),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 8),
                        
                        Wrap(
                          spacing: 16,
                          runSpacing: 8,
                          children: [
                            _buildCheckbox('添加到队列顶部', _addToTopOfQueue, (value) => setState(() => _addToTopOfQueue = value!)),
                            _buildCheckbox('跳过哈希校验', _skipHashCheck, (value) => setState(() => _skipHashCheck = value!)),
                            _buildCheckbox('按顺序下载', _downloadInOrder, (value) => setState(() => _downloadInOrder = value!)),
                            _buildCheckbox('先下载首尾文件块', _downloadFirstLastPieces, (value) => setState(() => _downloadFirstLastPieces = value!)),
                          ],
                        ),
                        
                        const SizedBox(height: 8),
                        Row(
                          children: [
                            const Text('内容布局:'),
                            const SizedBox(width: 8),
                            Expanded(
                              child: DropdownButtonFormField<String>(
                                value: _contentLayout,
                                items: _contentLayouts
                                    .map((layout) => DropdownMenuItem(
                                          value: layout,
                                          child: Text(layout),
                                        ))
                                    .toList(),
                                onChanged: (value) => setState(() => _contentLayout = value),
                                decoration: const InputDecoration(
                                  border: OutlineInputBorder(),
                                  isDense: true,
                                  hintText: '选择内容布局',
                                ),
                              ),
                            ),
                          ],
                        ),
                        const Divider(height: 24),
                        
                        _buildSectionTitle('Torrent 信息'),
                        const SizedBox(height: 8),
                        
                        if (_isLoading)
                          const Center(child: CircularProgressIndicator())
                        else
                          Column(
                            children: [
                              _buildInfoRow('名称', _torrentName),
                              _buildInfoRow('总大小', _torrentSize),
                              _buildInfoRow('文件数量', '$_fileCount 个'),
                              // 修复：添加空安全检查
                              if (_torrentComment != null && _torrentComment!.isNotEmpty)
                                _buildInfoRow('注释', _torrentComment!), // 添加非空断言
                              if (_torrentCreator != null && _torrentCreator!.isNotEmpty)
                                _buildInfoRow('创建者', _torrentCreator!), // 添加非空断言
                            ],
                          ),
                        const Divider(height: 24),
                        
                        _buildSectionTitle('选择要下载的文件'),
                        const SizedBox(height: 8),
                        
                        if (_isLoading)
                          const Center(child: CircularProgressIndicator())
                        else if (_torrentFiles.isEmpty)
                          const Center(child: Text('没有文件可显示'))
                        else
                          Container(
                            constraints: const BoxConstraints(maxHeight: 200),
                            child: SingleChildScrollView(
                              child: Column(
                                children: _buildFileWidgets(),
                              ),
                            ),
                          ),
                        const Divider(height: 24),
                        
                        _buildSectionTitle('其他选项'),
                        const SizedBox(height: 8),
                        
                        CheckboxListTile(
                          title: const Text('不再显示此对话框（使用默认设置）'),
                          value: _neverShowAgain,
                          onChanged: (value) => setState(() => _neverShowAgain = value!),
                          controlAffinity: ListTileControlAffinity.leading,
                          contentPadding: EdgeInsets.zero,
                          dense: true,
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _buildSectionTitle(String title) {
    return Text(
      title,
      style: const TextStyle(
        fontSize: 16,
        fontWeight: FontWeight.bold,
        color: Colors.black87,
      ),
    );
  }

  Widget _buildInfoRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(width: 80, child: Text('$label：', style: const TextStyle(fontWeight: FontWeight.bold))),
          Expanded(child: Text(value)),
        ],
      ),
    );
  }

  Widget _buildCheckbox(String label, bool value, Function(bool?) onChanged) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Checkbox(
          value: value,
          onChanged: onChanged,
          materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
        ),
        Text(label),
      ],
    );
  }
}