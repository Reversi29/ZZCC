// lib/presentation/pages/shared/widgets/shared_file_screen.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:file_picker/file_picker.dart';
import 'package:get_it/get_it.dart';
import 'package:zzcc/core/services/torrent_service.dart';
import 'package:zzcc/core/services/logger_service.dart';
import 'package:zzcc/data/models/torrent_model.dart';
import 'package:zzcc/presentation/providers/download_provider.dart';
import 'package:zzcc/presentation/pages/shared/widgets/add_torrent_dialog.dart';
import 'package:zzcc/presentation/providers/torrent_settings_provider.dart';
import 'package:zzcc/presentation/providers/shared_file_settings_provider.dart';
import 'package:zzcc/data/models/shared_file_settings_model.dart';

class SharedFileScreen extends ConsumerStatefulWidget {
  const SharedFileScreen({super.key});

  @override
  ConsumerState<SharedFileScreen> createState() => _SharedFileScreenState();
}

class _SharedFileScreenState extends ConsumerState<SharedFileScreen> {
  final TextEditingController _magnetController = TextEditingController();
  final TextEditingController _searchController = TextEditingController();
  late final TorrentService _torrentService;
  late final LoggerService _logger;
  final Set<String> _activeTasks = {};
  final Map<String, bool> _pausedStatus = {};
  final Set<String> _selectedTasks = {};
  final Map<String, GlobalKey> _rowKeys = {};
  bool _isDragging = false;
  Offset? _dragStart;
  Offset? _dragCurrent;
  final ScrollController _sidebarScrollController = ScrollController();
  double _sidebarWidth = 240;
  bool _sidebarHidden = false;
  
  // 当前筛选条件
  String _currentFilter = "全部";
  bool _searchMode = false;

  @override
  void initState() {
    super.initState();
    _torrentService = GetIt.I<TorrentService>();
    _logger = GetIt.I<LoggerService>();
    _initializeTorrentService();
    // After the first frame, populate local active task set from persisted tasks
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      try {
        final torrents = ref.read(downloadProvider).torrents;
        if (torrents.isNotEmpty) {
          setState(() {
            _activeTasks.addAll(torrents.map((t) => t.id));
          });

          // Register infoHash mappings in the torrent service so operations work after restart
          for (final t in torrents) {
            try {
              if (t.magnetUrl != null && t.magnetUrl!.isNotEmpty) {
                _torrentService.registerTaskInfoHash(t.id, t.magnetUrl!);
              }
            } catch (e) {
              _logger.warning('Failed to register task ${t.id} infoHash: $e');
            }
          }
        }
      } catch (e) {
        _logger.warning('Failed to populate active tasks from provider: $e');
      }
    });
  }

  Future<void> _initializeTorrentService() async {
    try {
      _logger.info('Initializing torrent service...');
      await _torrentService.initialize();
      _logger.info('Torrent service initialized successfully');
    } catch (e) {
      _logger.error('Torrent service initialization failed: $e');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Torrent服务初始化失败: $e')),
        );
      }
    }
  }

  @override
  void dispose() {
    _torrentService.dispose();
    _magnetController.dispose();
    _searchController.dispose();
    _sidebarScrollController.dispose();
    super.dispose();
  }

  // 筛选torrent列表
  List<TorrentInfo> _filterTorrents(List<TorrentInfo> torrents) {
    List<TorrentInfo> filtered = torrents;
    
    // 应用状态筛选
    switch (_currentFilter) {
      case "下载中":
        filtered = filtered.where((t) => t.progress != null && t.progress! > 0 && t.progress! < 1).toList();
        break;
      case "已完成":
        filtered = filtered.where((t) => t.progress == 1).toList();
        break;
      case "暂停中":
        filtered = filtered.where((t) => t.isPaused ?? false).toList();
        break;
      case "等待中":
        filtered = filtered.where((t) => t.progress == 0).toList();
        break;
      default: // 全部
        break;
    }
    
    // 应用搜索筛选
    if (_searchMode && _searchController.text.isNotEmpty) {
      final query = _searchController.text.toLowerCase();
      filtered = filtered.where((t) => 
        t.name.toLowerCase().contains(query) || 
        t.id.toLowerCase().contains(query)
      ).toList();
    }
    
    return filtered;
  }

  @override
  Widget build(BuildContext context) {
    final downloadState = ref.watch(downloadProvider);
    final savePath = downloadState.savePath;
    final allTorrents = downloadState.torrents;
    final filteredTorrents = _filterTorrents(allTorrents);

    return Scaffold(
      body: Row(
        children: [
          // 左侧筛选边栏
          _buildSidebar(),
          
          // 主内容区域
          Expanded(
            child: Column(
              children: [
                // 工具栏
                _buildToolbar(savePath),
                
                // 搜索栏
                _buildSearchBar(),
                
                // 下载列表
                Expanded(
                  child: _buildDownloadList(filteredTorrents),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // 左侧筛选边栏
  Widget _buildSidebar() {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 200),
      width: _sidebarHidden ? 0 : _sidebarWidth,
      decoration: BoxDecoration(
        color: Theme.of(context).cardColor,
        border: Border(
          right: BorderSide(color: Theme.of(context).dividerColor),
        ),
      ),
      child: Stack(
        children: [
          Scrollbar(
        controller: _sidebarScrollController, // 绑定控制器
        thumbVisibility: true,
        child: SingleChildScrollView(
          controller: _sidebarScrollController, // 与 Scrollbar 共享同一个控制器
          child: Column(
            children: [
              const Padding(
                padding: EdgeInsets.all(12.0),
                child: Text(
                  '状态',
                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
                ),
              ),
              _buildSidebarItem('全部', isSelected: _currentFilter == '全部'),
              _buildSidebarItem('下载中', isSelected: _currentFilter == '下载中'),
              _buildSidebarItem('已完成', isSelected: _currentFilter == '已完成'),
              _buildSidebarItem('暂停中', isSelected: _currentFilter == '暂停中'),
              _buildSidebarItem('等待中', isSelected: _currentFilter == '等待中'),
              
              const Divider(height: 1),
              const Padding(
                padding: EdgeInsets.all(12.0),
                child: Text(
                  '分类',
                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
                ),
              ),
              _buildSidebarItem('视频'),
              _buildSidebarItem('音频'),
              _buildSidebarItem('文档'),
              _buildSidebarItem('其他'),
              
              const Divider(height: 1),
              const Padding(
                padding: EdgeInsets.all(12.0),
                child: Text(
                  '标签',
                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
                ),
              ),
              _buildSidebarItem('工作'),
              _buildSidebarItem('娱乐'),
              _buildSidebarItem('个人'),
            ],
          ),
        ),
          ),
          // Drag handle
          if (!_sidebarHidden)
            Positioned(
              right: 0,
              top: 0,
              bottom: 0,
              width: 6,
              child: MouseRegion(
                cursor: SystemMouseCursors.resizeColumn,
                child: GestureDetector(
                  behavior: HitTestBehavior.translucent,
                  onHorizontalDragUpdate: (details) {
                    setState(() {
                      _sidebarWidth = (_sidebarWidth + details.delta.dx).clamp(120.0, 600.0);
                    });
                  },
                ),
              ),
            ),
        ],
      ),
    );
  }

  // 边栏筛选项
  Widget _buildSidebarItem(String title, {bool isSelected = false}) {
    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      title: Text(
        title,
        style: TextStyle(
          fontSize: 13,
          color: isSelected ? Theme.of(context).primaryColor : null,
        ),
      ),
      selected: isSelected,
      onTap: () {
        setState(() {
          _currentFilter = title;
        });
      },
    );
  }

  // 工具栏
  Widget _buildToolbar(String? savePath) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: Theme.of(context).appBarTheme.backgroundColor,
        border: Border(
          bottom: BorderSide(color: Theme.of(context).dividerColor),
        ),
      ),
      child: Row(
        children: [
          IconButton(
            icon: Icon(_sidebarHidden ? Icons.chevron_right : Icons.chevron_left, size: 18),
            tooltip: _sidebarHidden ? '显示边栏' : '隐藏边栏',
            onPressed: () => setState(() => _sidebarHidden = !_sidebarHidden),
          ),
          IconButton(
            icon: const Icon(Icons.link, size: 18),
            tooltip: '添加Torrent链接',
            onPressed: _showAddMagnetDialog,
          ),
          IconButton(
            icon: const Icon(Icons.file_upload, size: 18),
            tooltip: '添加Torrent文件',
            onPressed: _selectTorrentFile,
          ),
          IconButton(
            icon: const Icon(Icons.delete, size: 18),
            tooltip: '删除选中任务',
            onPressed: () => _removeSelectedTorrents(),
          ),
          IconButton(
            icon: const Icon(Icons.play_arrow, size: 18),
            tooltip: '开始选中任务',
            onPressed: () => _resumeSelectedTorrents(),
          ),
          IconButton(
            icon: const Icon(Icons.pause, size: 18),
            tooltip: '停止选中任务',
            onPressed: () => _pauseSelectedTorrents(),
          ),
          IconButton(
            icon: const Icon(Icons.settings, size: 18),
            tooltip: '设置',
            onPressed: _showSettingsDialog,
          ),
          IconButton(
            icon: const Icon(Icons.search, size: 18),
            tooltip: '搜索',
            onPressed: () {
              setState(() {
                _searchMode = !_searchMode;
                if (!_searchMode) {
                  _searchController.clear();
                }
              });
            },
          ),
          const Spacer(),
          if (savePath != null)
            Consumer(
              builder: (context, ref, child) {
                final defaultSavePath = ref.watch(sharedFileSettingsProvider).defaultSavePath;
                if (defaultSavePath != null) {
                  return Padding(
                    padding: const EdgeInsets.only(right: 8.0),
                    child: Row(
                      children: [
                        const Icon(Icons.folder, size: 16),
                        const SizedBox(width: 4),
                        Text(
                          defaultSavePath.split('/').last,
                          style: const TextStyle(fontSize: 12),
                        ),
                      ],
                    ),
                  );
                }
                return const SizedBox.shrink();
              },
            ),
        ],
      ),
    );
  }

  // 搜索栏
  Widget _buildSearchBar() {
    if (!_searchMode) return const SizedBox.shrink();
    
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: TextField(
        controller: _searchController,
        decoration: InputDecoration(
          hintText: '搜索种子...',
          prefixIcon: const Icon(Icons.search, size: 18),
          suffixIcon: IconButton(
            icon: const Icon(Icons.clear, size: 18),
            onPressed: () => _searchController.clear(),
          ),
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(4),
            borderSide: BorderSide(color: Theme.of(context).dividerColor),
          ),
          contentPadding: const EdgeInsets.symmetric(vertical: 8),
          isDense: true,
        ),
        onChanged: (value) => setState(() {}),
      ),
    );
  }

  // 显示添加磁力链接对话框
  void _showAddMagnetDialog() {
    showDialog(
      context: context,
      useRootNavigator: false,
      builder: (context) => AlertDialog(
        title: const Text('添加磁力链接'),
        content: TextField(
          controller: _magnetController,
          decoration: const InputDecoration(
            hintText: '输入磁力链接',
            border: OutlineInputBorder(),
          ),
          autofocus: true,
          maxLines: 3,
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('取消'),
          ),
          TextButton(
            onPressed: () async {
              // 先关闭当前对话框
              Navigator.pop(context);
              
              if (_magnetController.text.isNotEmpty) {
                // 确保已从本地持久化加载设置，再读取（避免首次打开为默认值）
                SharedFileSettingsModel settings;
                try {
                  settings = await ref.read(sharedFileSettingsFutureProvider.future);
                } catch (e) {
                  settings = ref.read(sharedFileSettingsProvider);
                }

                if (!mounted) return;

                // 确认对话框的 BuildContext 仍然有效（避免跨 async 间隔使用失效的 context）
                if (!context.mounted) return;

                // 显示添加Torrent对话框
                final dialogResult = await showDialog<Map<String, dynamic>>(
                  context: context,
                  useRootNavigator: false,
                  builder: (context) => AddTorrentDialog(
                    torrentPath: _magnetController.text,  // 传入磁力链接作为torrentPath
                    defaultSavePath: settings.defaultSavePath,
                    lastUsedPath: settings.lastUsedPath,
                    incompleteTorrentPath: settings.incompleteTorrentPath,
                    defaultIsManualMode: settings.isManualMode,
                    defaultUseDifferentIncompletePath: settings.useDifferentIncompletePath,
                    defaultRememberLastPath: settings.rememberLastPath,
                  ),
                );
                
                // 处理对话框结果
                if (dialogResult != null) {
                  await _handleTorrentDialogResult(_magnetController.text, dialogResult);
                }
              }
              
              // 清空输入
              _magnetController.clear();
            },
            child: const Text('确定'),
          ),
        ],
      ),
    );
  }

  // 显示设置对话框
  Future<void> _showSettingsDialog() async {
    if (!mounted) return;

    // 直接显示设置弹窗，不显示加载对话框
    String? tempSavePath;
    String tempDownloadSpeed = '无限制';
    String tempUploadSpeed = '无限制';

    // 确保本地持久化的设置已加载后再读取，避免首次打开时仍为默认值
    try {
      // 等待 FutureProvider 完成加载（如果尚未完成）
      final loaded = await ref.read(sharedFileSettingsFutureProvider.future);
      tempSavePath = loaded.defaultSavePath;
      tempDownloadSpeed = loaded.maxDownloadSpeed;
      tempUploadSpeed = loaded.maxUploadSpeed;
    } catch (e) {
      // 如果等待失败或没有值，则回退到当前状态或默认值
      try {
        final currentSettings = ref.read(sharedFileSettingsProvider);
        tempSavePath = currentSettings.defaultSavePath;
        tempDownloadSpeed = currentSettings.maxDownloadSpeed;
        tempUploadSpeed = currentSettings.maxUploadSpeed;
      } catch (_) {
        // 使用默认值
      }
    }

    if (!mounted) return;

    await showDialog(
      context: context,
      useRootNavigator: false,
      builder: (BuildContext dialogContext) {
        return StatefulBuilder(
          builder: (dialogContext, setState) {
            return AlertDialog(
              title: const Text('文件共享设置'),
              insetPadding: const EdgeInsets.symmetric(horizontal: 40, vertical: 24),
              content: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 500),
                child: SingleChildScrollView(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      ListTile(
                        title: const Text('默认保存路径'),
                        subtitle: Text(tempSavePath ?? '未设置'),
                        trailing: IconButton(
                          icon: const Icon(Icons.folder_open),
                          onPressed: () async {
                            String? path = await FilePicker.platform.getDirectoryPath();
                            if (path != null) {
                              setState(() => tempSavePath = path);
                            }
                          },
                        ),
                      ),
                      const Divider(height: 1),
                      ListTile(
                        title: const Text('最大下载速度'),
                        trailing: DropdownButton<String>(
                          value: tempDownloadSpeed,
                          items: const [
                            DropdownMenuItem(value: '无限制', child: Text('无限制')),
                            DropdownMenuItem(value: '1MB/s', child: Text('1MB/s')),
                            DropdownMenuItem(value: '5MB/s', child: Text('5MB/s')),
                            DropdownMenuItem(value: '10MB/s', child: Text('10MB/s')),
                          ],
                          onChanged: (value) {
                            if (value != null) {
                              setState(() => tempDownloadSpeed = value);
                            }
                          },
                        ),
                      ),
                      const Divider(height: 1),
                      ListTile(
                        title: const Text('最大上传速度'),
                        trailing: DropdownButton<String>(
                          value: tempUploadSpeed,
                          items: const [
                            DropdownMenuItem(value: '无限制', child: Text('无限制')),
                            DropdownMenuItem(value: '512KB/s', child: Text('512KB/s')),
                            DropdownMenuItem(value: '1MB/s', child: Text('1MB/s')),
                          ],
                          onChanged: (value) {
                            if (value != null) {
                              setState(() => tempUploadSpeed = value);
                            }
                          },
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.of(dialogContext).pop(),
                  child: const Text('取消'),
                ),
                TextButton(
                  onPressed: () {
                    ref.read(sharedFileSettingsNotifierProvider.notifier).updateSharedSettings(tempSavePath, tempDownloadSpeed, tempUploadSpeed);
                    
                    ScaffoldMessenger.of(dialogContext).showSnackBar(
                      const SnackBar(content: Text('设置已保存')),
                    );
                    Navigator.of(dialogContext).pop();
                  },
                  child: const Text('确认'),
                ),
              ],
            );
          },
        );
      },
    );
  }

  // 批量操作方法
  void _pauseSelectedTorrents() {
    // 实际实现中需要跟踪选中的torrent
    // 这里简化处理，暂停所有正在下载的
      for (final id in _selectedTasks.toList()) {
        final torrent = _getTorrentById(id);
        if (torrent != null && !(torrent.isPaused ?? false)) {
          _pauseTorrent(torrent);
        }
      }
  }

  void _resumeSelectedTorrents() {
    // 实际实现中需要跟踪选中的torrent
    // 这里简化处理，恢复所有暂停的
      for (final id in _selectedTasks.toList()) {
        final torrent = _getTorrentById(id);
        if (torrent != null && (torrent.isPaused ?? false)) {
          _pauseTorrent(torrent);
        }
      }
  }

  void _removeSelectedTorrents() {
    if (_selectedTasks.isEmpty) return;

    // Ask user whether to delete downloaded files as well
    showDialog<String>(
      context: context,
      builder: (ctx) {
        return AlertDialog(
          title: Text('删除任务'),
          content: Text('是否同时删除已下载的文件？\n选择“删除文件并移除任务”会同时删除磁盘上的文件。\n选择“仅移除任务”将保留已下载的文件。'),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop('cancel'),
              child: const Text('取消'),
            ),
            TextButton(
              onPressed: () => Navigator.of(ctx).pop('remove_only'),
              child: const Text('仅移除任务'),
            ),
            ElevatedButton(
              onPressed: () => Navigator.of(ctx).pop('delete_files'),
              child: const Text('删除文件并移除任务'),
            ),
          ],
        );
      },
    ).then((choice) async {
      if (choice == null || choice == 'cancel') return;

      final deleteFiles = choice == 'delete_files';

      for (final id in _selectedTasks.toList()) {
        final torrent = _getTorrentById(id);
        if (torrent != null) {
          try {
            await ref.read(downloadProvider.notifier).removeTorrentWithFiles(torrent.id, deleteFiles: deleteFiles);
          } catch (e) {
            _logger.error('Failed to remove torrent ${torrent.id}: $e');
          }
          _activeTasks.remove(torrent.id);
          setState(() {
            _selectedTasks.remove(torrent.id);
          });
        }
      }
    });
  }

    TorrentInfo? _getTorrentById(String id) {
      final torrents = ref.read(downloadProvider).torrents;
      for (final t in torrents) {
        if (t.id == id) return t;
      }
      return null;
    }

  // 原有方法保持不变（_selectTorrentFile, _selectSavePath, _addTorrentDownload等）
  Future<void> _selectTorrentFile() async {
    try {
      FilePickerResult? result = await FilePicker.platform.pickFiles(
        type: FileType.custom,
        allowedExtensions: ['torrent'],
      );

      if (result != null && result.files.single.path != null) {
        final file = result.files.single;

        // 确保已从本地持久化加载设置，再读取（避免首次打开为默认值）
        SharedFileSettingsModel settings;
        try {
          settings = await ref.read(sharedFileSettingsFutureProvider.future);
        } catch (e) {
          settings = ref.read(sharedFileSettingsProvider);
        }

          if (!mounted) return;

          // 确认对话框的 BuildContext 仍然有效（避免跨 async 间隔使用失效的 context）
          if (!context.mounted) return;

          final dialogResult = await showDialog<Map<String, dynamic>>(
            context: context,
            useRootNavigator: false,
            builder: (context) => AddTorrentDialog(
                torrentPath: file.path!,
                defaultSavePath: settings.defaultSavePath,
                lastUsedPath: settings.lastUsedPath,
                incompleteTorrentPath: settings.incompleteTorrentPath, // 修正参数名
                defaultIsManualMode: settings.isManualMode,
                defaultUseDifferentIncompletePath: settings.useDifferentIncompletePath,
                defaultRememberLastPath: settings.rememberLastPath,
              ),
            );

        if (file.path != null) {
          _logger.info('Selected torrent file: ${file.path}');
          // 显示添加Torrent对话框 - 添加mounted检查
          if (dialogResult != null) {
            await _handleTorrentDialogResult(file.path!, dialogResult);
          }
        }
      }
    } catch (e) {
      _logger.error('Failed to select torrent file: $e');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('选择种子文件失败: $e')),
        );
      }
    }
  }

  Future<void> _handleTorrentDialogResult(String torrentInput, Map<String, dynamic> result) async {
    try {
      final savePath = result['savePath'] as String;
      final useDifferentIncompletePath = result['useDifferentIncompletePath'] as bool;
      final incompletePath = result['incompletePath'] as String?;
      final startTorrent = result['startTorrent'] as bool;
      
      // 保存路径偏好设置
      if (result['rememberLastPath'] as bool) {
        ref.read(downloadProvider.notifier).setSavePath(savePath);
        if (useDifferentIncompletePath && incompletePath != null) {
          ref.read(downloadProvider.notifier).setIncompletePath(incompletePath);
        }
      }
      
      // 调用Torrent服务添加下载任务（同时支持文件路径和磁力链接）
      final taskId = await _torrentService.startDownload(
        torrentInput,  // 可能是文件路径或磁力链接
        savePath,
      );
      
      // 更新下载列表
      await ref.read(downloadProvider.notifier).addTorrentWithDetails(
        taskId: taskId,
        torrentPath: torrentInput,
        savePath: savePath,
        startImmediately: startTorrent,
        // 其他参数...
        selectedTotalBytes: result['selectedTotalBytes'] as int?,
        selectedSizeReadable: result['selectedSize'] as String?,
      );
      
      // 处理"不再显示"设置
      if (result['neverShowAgain'] as bool) {
        await ref.read(settingsProvider.notifier).setNeverShowAddTorrentDialog(true);
      }
      
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('已添加Torrent任务: ${torrentInput.split('/').last.split('&').first}')),
        );
      }
    } catch (e) {
      _logger.error('Failed to add torrent: $e');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('添加Torrent失败: $e')),
        );
      }
    }
  }

  // Future<void> _addTorrentDownload(String? torrentPath) async {
  //   if (torrentPath == null || torrentPath.isEmpty) return;
    
  //   final savePath = ref.read(downloadProvider).savePath;
  //   if (savePath == null) {
  //     _logger.warning('Save path not selected');
  //     if (mounted) {
  //       ScaffoldMessenger.of(context).showSnackBar(
  //         const SnackBar(content: Text('请先选择保存路径')),
  //       );
  //     }
  //     return;
  //   }

  //   try {
  //     final taskId = await _torrentService.startDownload(torrentPath, savePath);
      
  //     ref.read(downloadProvider.notifier).addTorrent(TorrentInfo(
  //       id: taskId,
  //       name: torrentPath.split('/').last,
  //       magnetUrl: torrentPath,
  //       savePath: savePath,
  //       progress: 0.0,
  //       totalSize: '0 B',
  //       downloadedSize: '0 B',
  //       peers: 0,
  //       seeds: 0,
  //     ));
      
  //     _activeTasks.add(taskId);
  //     _logger.info('Added torrent download: $torrentPath');
      
  //     if (mounted) {
  //       ScaffoldMessenger.of(context).showSnackBar(
  //         SnackBar(content: Text('已添加下载: ${torrentPath.split('/').last}')),
  //       );
  //     }
  //   } catch (e, stack) {
  //     _logger.error('Torrent add failed: $e\n$stack');
  //     if (mounted) {
  //       showDialog(
  //         context: context,
  //         builder: (ctx) => AlertDialog(
  //           title: const Text('添加失败'),
  //           content: Text('错误: ${e.toString()}'),
  //         )
  //       );
  //     }
  //   }
  // }

  // void _startDownload() async {
  //   if (_magnetController.text.isEmpty) return;
    
  //   final savePath = ref.read(downloadProvider).savePath;
  //   if (savePath == null) {
  //     _logger.warning('Save path not selected');
  //     if (mounted) {
  //       ScaffoldMessenger.of(context).showSnackBar(
  //         const SnackBar(content: Text('请先选择保存路径')),
  //       );
  //     }
  //     return;
  //   }

  //   try {
  //     _logger.info('Starting magnet download: ${_magnetController.text}');
  //     final taskId = await _torrentService.startDownload(
  //       _magnetController.text, 
  //       savePath
  //     );
  //     ref.read(downloadProvider.notifier).addTorrent(TorrentInfo(
  //       id: taskId,
  //       name: _magnetController.text.split('&').first.split('=').last,
  //       magnetUrl: _magnetController.text,
  //       savePath: savePath,
  //       progress: 0.0,
  //       totalSize: '0 B',
  //       downloadedSize: '0 B',
  //       peers: 0,
  //       seeds: 0,
  //     ));

  //     _activeTasks.add(taskId);
  //     _logger.info('Magnet download started successfully');
      
  //     if (mounted) {
  //       ScaffoldMessenger.of(context).showSnackBar(
  //         const SnackBar(content: Text('下载已开始')),
  //       );
  //     }
  //   } catch (e) {
  //     _logger.error('Failed to start magnet download: $e');
  //     if (mounted) {
  //       ScaffoldMessenger.of(context).showSnackBar(
  //         SnackBar(content: Text('下载失败: $e')),
  //       );
  //     }
  //   } finally {
  //     _magnetController.clear();
  //   }
  // }

  void _pauseTorrent(TorrentInfo torrent) {
    final isPaused = torrent.isPaused ?? false;
    
    try {
      if (isPaused) {
        // 恢复下载
        _pausedStatus[torrent.id] = false;
        _torrentService.resumeDownload(torrent.id);
        ref.read(downloadProvider.notifier).resumeTorrent(torrent.id);
        _logger.info('Resumed torrent: ${torrent.id}');
      } else {
        // 暂停下载
        _pausedStatus[torrent.id] = true;
        _torrentService.pauseDownload(torrent.id);
        ref.read(downloadProvider.notifier).pauseTorrent(torrent.id);
        _logger.info('Paused torrent: ${torrent.id}');
      }
      
      setState(() {});
    } catch (e) {
      _logger.error('Failed to pause/resume torrent: $e');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('操作失败: $e')),
        );
      }
    }
  }

  Widget _buildDownloadList(List<TorrentInfo> torrents) {
    // Always show table headers even when there are no tasks.
    final columns = const [
      DataColumn(label: Text('名称')),
      DataColumn(label: Text('已选择')),
      DataColumn(label: Text('进度')),
      DataColumn(label: Text('状态')),
      DataColumn(label: Text('做种数')),
      DataColumn(label: Text('用户')),
      DataColumn(label: Text('下载速度')),
      DataColumn(label: Text('上传速度')),
      DataColumn(label: Text('剩余时间')),
      DataColumn(label: Text('比率')),
      DataColumn(label: Text('分类')),
      DataColumn(label: Text('标签')),
      DataColumn(label: Text('可用性')),
      DataColumn(label: Text('已保存路径')),
    ];

    List<DataRow> rows;
    if (torrents.isEmpty) {
      // Provide a single empty row so headers remain visible
      rows = [
        DataRow(cells: List.generate(columns.length, (index) => const DataCell(Text('-')))),
      ];
    } else {
      rows = torrents.map((t) {
        final progressPercent = (t.progress ?? 0) * 100;
        _rowKeys.putIfAbsent(t.id, () => GlobalKey());
        return DataRow(
          selected: _selectedTasks.contains(t.id),
          onSelectChanged: (sel) {
            setState(() {
              if (sel == true) {
                _selectedTasks.add(t.id);
              } else {
                _selectedTasks.remove(t.id);
              }
            });
          },
          cells: [
            DataCell(SizedBox(width: 300, child: Container(key: _rowKeys[t.id], child: Text(t.name, overflow: TextOverflow.ellipsis)))),
            DataCell(Text(t.selectedSize ?? '-')),
            DataCell(Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('${progressPercent.toStringAsFixed(1)}%'),
                const SizedBox(height: 4),
                LinearProgressIndicator(value: (t.progress ?? 0)),
              ],
            )),
            DataCell(Text(t.status ?? (t.isPaused == true ? '已暂停' : '下载中'))),
            DataCell(Text('${t.seeds ?? 0}')),
            DataCell(Text('${t.peers ?? 0}')),
            DataCell(Text(t.downloadRate ?? '-')),
            DataCell(Text(t.uploadSpeed ?? '-')),
            DataCell(Text(t.remainingTime ?? '-')),
            DataCell(Text(t.ratio?.toStringAsFixed(2) ?? '-')),
            DataCell(Text(t.category ?? '-')),
            DataCell(Text((t.tags ?? []).join(', '))),
            DataCell(Text(t.availability ?? '-')),
            DataCell(Text(t.savePath ?? '-')),
          ],
        );
      }).toList();
    }

    // Wrap with GestureDetector to support drag selection
    return Stack(
      children: [
        GestureDetector(
          behavior: HitTestBehavior.translucent,
          onPanStart: (details) {
            setState(() {
              _isDragging = true;
              _dragStart = details.globalPosition;
              _dragCurrent = details.globalPosition;
            });
          },
          onPanUpdate: (details) {
            setState(() {
              _dragCurrent = details.globalPosition;
            });
            // While dragging, check which rows intersect the drag point and select them
            for (final entry in _rowKeys.entries) {
              final key = entry.value;
              final ctx = key.currentContext;
              if (ctx == null) continue;
              final box = ctx.findRenderObject() as RenderBox;
              final topLeft = box.localToGlobal(Offset.zero);
              final bottomRight = topLeft + Offset(box.size.width, box.size.height);
              final dragPoint = details.globalPosition;
              if (dragPoint.dx >= topLeft.dx && dragPoint.dx <= bottomRight.dx && dragPoint.dy >= topLeft.dy && dragPoint.dy <= bottomRight.dy) {
                setState(() => _selectedTasks.add(entry.key));
              }
            }
          },
          onPanEnd: (details) {
            setState(() {
              _isDragging = false;
              _dragStart = null;
              _dragCurrent = null;
            });
          },
          child: SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: ConstrainedBox(
              constraints: BoxConstraints(minWidth: MediaQuery.of(context).size.width - (_sidebarHidden ? 0 : _sidebarWidth)),
              child: DataTable(columns: columns, rows: rows),
            ),
          ),
        ),
        if (_isDragging && _dragStart != null && _dragCurrent != null)
          Positioned.fromRect(
            rect: Rect.fromPoints(_dragStart!, _dragCurrent!),
            child: Container(
              color: Color.fromRGBO(33,150,243,0.15),
            ),
          ),
      ],
    );
  }

  // NOTE: Individual card-style torrent item removed in favor of the DataTable view.
}