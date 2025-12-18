import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter_code_editor/flutter_code_editor.dart';
import 'package:highlight/languages/dart.dart';
import 'package:zzcc/presentation/providers/workbench_provider.dart';
import 'package:flutter/services.dart';
import 'package:highlight/highlight.dart' show Mode;
import 'package:highlight/languages/python.dart';
import 'package:highlight/languages/cpp.dart';
import 'package:highlight/languages/java.dart';
import 'package:highlight/languages/javascript.dart';
import 'package:highlight/languages/typescript.dart';
import 'package:highlight/languages/lua.dart';
import 'package:highlight/languages/go.dart';
import 'package:highlight/languages/rust.dart';
import 'package:highlight/languages/php.dart';
import 'package:highlight/languages/xml.dart' as xml_lang;
import 'package:highlight/languages/css.dart' as css_lang;
import 'package:highlight/languages/json.dart';
import 'package:highlight/languages/yaml.dart';
import 'package:highlight/languages/markdown.dart';
import 'package:path/path.dart' as path;
import 'package:universal_html/html.dart' as html;
import 'package:url_launcher/url_launcher.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:video_player/video_player.dart';
import 'package:audioplayers/audioplayers.dart';
import 'package:path_provider/path_provider.dart';
import 'package:zzcc/data/models/file_tree_model.dart';
import 'package:zzcc/core/services/audio_event_handler.dart';
import 'package:flutter/scheduler.dart';
import 'package:zzcc/core/utils/lrc_parser.dart';
import 'package:zzcc/presentation/pages/workbench/widgets/lyrics_display.dart';
import 'package:zzcc/presentation/pages/workbench/widgets/audio_visualizer.dart';
import 'dart:developer';

bool get isWeb {
  return identical(0, 0.0); // 简单的检测Web平台的方法
}

// 添加 SettingsPanel 定义
class SettingsPanel extends StatelessWidget {
  const SettingsPanel({super.key});

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Text('设置面板'),
    );
  }
}

class WorkbenchPage extends ConsumerStatefulWidget {
  const WorkbenchPage({super.key});

  @override
  ConsumerState<WorkbenchPage> createState() => _WorkbenchPageState();
}

class _WorkbenchPageState extends ConsumerState<WorkbenchPage> {
  Timer? _fileWatcherTimer;
  Timer? _debounceTimer;
  final ScrollController _tabScrollController = ScrollController();
  String? _rootPath;

  @override
  void initState() {
    super.initState();
    _startFileWatcher();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _preserveRootNode();
    });
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final provider = ref.read(workbenchProvider.notifier);
    
    // 检查是否需要刷新文件树
    if (provider.fileTreeNeedsRefresh) {
      // 使用 Future.microtask 确保在下一帧刷新
      Future.microtask(() {
        setState(() {
          // 标记刷新完成
          provider.fileTreeRefreshed();
        });
      });
    }
  }

  void _preserveRootNode() {
    final provider = ref.read(workbenchProvider.notifier);
    if (provider.currentFolderPath != null) {
      setState(() {
        _rootPath = provider.currentFolderPath;
      });
    }
  }

  @override
  void dispose() {
    _fileWatcherTimer?.cancel();
    _debounceTimer?.cancel();
    super.dispose();
  }

  void _startFileWatcher() {
    // 每5秒检查一次文件系统变化
    _fileWatcherTimer = Timer.periodic(const Duration(seconds: 5), (timer) {
      final provider = ref.read(workbenchProvider.notifier);
      if (provider.currentFolderPath != null) {
        provider.refreshFileTree();
      }
    });
  }

  Widget _buildActivityBarItem(BuildContext context, IconData icon, String tooltip, int index, 
                              WorkbenchProvider provider, WidgetRef ref) {
    final isActive = provider.activeSidebarTab == index && provider.isSidebarVisible;
    
    return IconButton(
      icon: Icon(icon),
      color: isActive ? Theme.of(context).primaryColor : Colors.grey[700],
      tooltip: tooltip,
      onPressed: () {
        if (index == 3) {
          ref.read(workbenchProvider.notifier).openSettings();
        } else {
          ref.read(workbenchProvider.notifier).toggleSidebar(index);
        }
      },
    );
  }

  Widget _buildSidebarContent(int activeTab, BuildContext context, WidgetRef ref) {
    switch (activeTab) {
      case 0: // 资源管理器
        return _buildExplorerSidebar(context, ref);
      case 1: // 搜索
        return _buildSearchSidebar();
      case 2: // 源代码管理
        return _buildSourceControlSidebar();
      default:
        return Container();
    }
  }

  Widget _buildExplorerSidebar(BuildContext context, WidgetRef ref) {
    final provider = ref.watch(workbenchProvider);
    
    return Container(
      constraints: const BoxConstraints(minWidth: 50.0),
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                const SizedBox(width: 8),
                const Expanded(
                  child: Text(
                    '资源管理器',
                    style: TextStyle(
                      fontWeight: FontWeight.bold,
                      fontSize: 14,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.more_vert, size: 20),
                  onPressed: () {},
                  tooltip: '更多操作',
                ),
              ],
            ),
          ),
          Expanded(
            child: provider.fileTree.isEmpty
                ? const Center(child: Text('请选择文件夹', style: TextStyle(fontSize: 12)))
                : _buildFileTree(provider.fileTree, ref),
          ),
        ],
      ),
    );
  }

  Widget _buildFileTree(List<FileNode> nodes, WidgetRef ref) {
    final provider = ref.read(workbenchProvider.notifier);
    final allNodes = _flattenTree(nodes);
    
    return ListView.builder(
      key: const PageStorageKey('fileTree'),
      shrinkWrap: true,
      physics: const AlwaysScrollableScrollPhysics(),
      itemCount: allNodes.length,
      itemBuilder: (context, index) {
        final flattenedNode = allNodes[index];
        final node = flattenedNode.node;
        final depth = flattenedNode.depth;
        
        // 通过路径比较确定根节点
        final isRootNode = node.path == _rootPath;
        
        if (isRootNode) {
          return _buildRootDirectoryTile(node, provider);
        }
        
        if (node.isDirectory) {
          return _buildDirectoryTile(node, provider, depth);
        } else {
          return _buildFileTile(node, provider, depth);
        }
      },
    );
  }

  Widget _buildRootDirectoryTile(FileNode node, WorkbenchProvider provider) {
    return ListTile(
      contentPadding: const EdgeInsets.only(left: 8, right: 4),
      minLeadingWidth: 0,
      minVerticalPadding: 0,
      dense: true,
      visualDensity: const VisualDensity(horizontal: -4, vertical: -4),
      leading: const Icon(Icons.folder, size: 16, color: Colors.blue),
      title: Text(
        node.name,
        style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold),
      ),
      trailing: node.isExpanded && node.children.isEmpty
          ? const SizedBox(
              width: 16,
              height: 16,
              child: CircularProgressIndicator(strokeWidth: 2),
            )
          : null,
      onTap: () => provider.expandDirectory(node.path),
    );
  }

  // 目录节点渲染
  Widget _buildDirectoryTile(FileNode node, WorkbenchProvider provider, int depth) {
    return ListTile(
      contentPadding: EdgeInsets.only(left: 8 + depth * 20, right: 4),
      minLeadingWidth: 0,
      minVerticalPadding: 0,
      dense: true,
      visualDensity: const VisualDensity(horizontal: -4, vertical: -4),
      leading: Icon(
        node.isExpanded ? Icons.expand_more : Icons.chevron_right,
        size: 16,
      ),
      title: Row(
        children: [
          Icon(
            node.isExpanded ? Icons.folder_open : Icons.folder,
            size: 16,
            color: Colors.blue,
          ),
          const SizedBox(width: 4),
          Text(node.name, style: const TextStyle(fontSize: 12)),
        ],
      ),
      trailing: node.isExpanded && node.children.isEmpty
          ? const SizedBox(
              width: 16,
              height: 16,
              child: CircularProgressIndicator(strokeWidth: 2),
            )
          : null,
      onTap: () => provider.expandDirectory(node.path),
    );
  }

  // 文件节点渲染
  Widget _buildFileTile(FileNode node, WorkbenchProvider provider, int depth) {
    return ListTile(
      contentPadding: EdgeInsets.only(left: 8 + depth * 20, right: 4),
      minLeadingWidth: 0,
      minVerticalPadding: 0,
      dense: true,
      leading: const Icon(Icons.insert_drive_file, size: 16),
      title: Padding(
        padding: const EdgeInsets.only(left: 4),
        child: Text(node.name, style: const TextStyle(fontSize: 12)),
      ),
      onTap: () => _debounceOpenFile(provider, node.path),
    );
  }

  void _debounceOpenFile(WorkbenchProvider provider, String path) {
    _debounceTimer?.cancel();
    _debounceTimer = Timer(const Duration(milliseconds: 300), () {
      provider.openFileByName(path);
    });
  }

  List<FlattenedNode> _flattenTree(List<FileNode> nodes, {int depth = 0}) {
    final List<FlattenedNode> result = [];
    
    for (final node in nodes) {
      result.add(FlattenedNode(node, depth));
      
      if (node.isExpanded && node.children.isNotEmpty) {
        result.addAll(_flattenTree(node.children, depth: depth + 1));
      }
    }
    
    return result;
  }

  Widget _buildSearchSidebar() {
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.all(16),
          child: TextField(
            decoration: InputDecoration(
              hintText: '搜索',
              prefixIcon: const Icon(Icons.search),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
              ),
            ),
          ),
        ),
        const Expanded(
          child: Center(
            child: Text('搜索功能'),
          ),
        ),
      ],
    );
  }

  Widget _buildSourceControlSidebar() {
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              const Text('源代码管理', style: TextStyle(fontWeight: FontWeight.bold)),
              const Spacer(),
              ElevatedButton.icon(
                icon: const Icon(Icons.commit),
                label: const Text('提交'),
                onPressed: () {},
              ),
            ],
          ),
        ),
        const Expanded(
          child: Center(
            child: Text('源代码管理功能'),
          ),
        ),
      ],
    );
  }

  Widget _buildMenuBar(BuildContext context, WidgetRef ref) {
    final provider = ref.read(workbenchProvider.notifier);
    
    return Container(
      height: 35,
      color: Colors.grey[100],
      child: Row(
        children: [
          PopupMenuButton<String>(
            offset: const Offset(0, 35),
            itemBuilder: (context) => const [
              PopupMenuItem(
                height: 25,
                value: 'new',
                child: Text('新建文件', style: TextStyle(fontSize: 12)),
              ),
              PopupMenuItem(
                height: 25,
                value: 'new_folder',
                child: Text('新建文件夹', style: TextStyle(fontSize: 12)),
              ),
              PopupMenuItem(
                height: 25,
                value: 'open_folder',
                child: Text('打开文件夹', style: TextStyle(fontSize: 12)),
              ),
              PopupMenuItem(
                height: 25,
                value: 'open',
                child: Text('打开文件', style: TextStyle(fontSize: 12)),
              ),
              PopupMenuItem(
                height: 25,
                value: 'save',
                child: Text('保存', style: TextStyle(fontSize: 12)),
              ),
              PopupMenuItem(
                height: 25,
                value: 'save_all',
                child: Text('全部保存', style: TextStyle(fontSize: 12)),
              ),
              PopupMenuItem(
                height: 25,
                value: 'close',
                child: Text('关闭文件', style: TextStyle(fontSize: 12)),
              ),
              PopupMenuItem(
                height: 25,
                value: 'close_folder',
                child: Text('关闭文件夹', style: TextStyle(fontSize: 12)),
              ),
            ],
            onSelected: (value) async {
              switch (value) {
                case 'new':
                  provider.createNewFile();
                  break;
                case 'new_folder':
                  await provider.createNewDirectory();
                  break;
                case 'open_folder':
                  await provider.openFolder(context);
                  break;
                case 'open':
                  provider.openFile(context);
                  break;
                case 'save':
                  provider.saveCurrentFile(context);
                  break;
                case 'save_all':
                  provider.saveAllFiles(context);
                  break;
                case 'close':
                  if (provider.activeFileIndex != -1) {
                    provider.closeFile(provider.activeFileIndex);
                  }
                  break;
                case 'close_folder':
                  provider.closeFolder();
                  break;
              }
            },
            child: const MouseRegion(cursor: SystemMouseCursors.click, child: Padding(
              padding: EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              child: Text('文件', style: TextStyle(fontSize: 12)),
            )),
          ),
          
          PopupMenuButton<String>(
            offset: const Offset(0, 35),
            itemBuilder: (context) => const [
              PopupMenuItem(
                height: 25,
                value: 'undo',
                child: Text('撤销', style: TextStyle(fontSize: 12)),
              ),
              PopupMenuItem(
                height: 25,
                value: 'redo',
                child: Text('重做', style: TextStyle(fontSize: 12)),
              ),
              PopupMenuItem(
                height: 25,
                value: 'cut',
                child: Text('剪切', style: TextStyle(fontSize: 12)),
              ),
              PopupMenuItem(
                height: 25,
                value: 'copy',
                child: Text('复制', style: TextStyle(fontSize: 12)),
              ),
              PopupMenuItem(
                height: 25,
                value: 'paste',
                child: Text('粘贴', style: TextStyle(fontSize: 12)),
              ),
            ],
            onSelected: (value) {},
            child: const MouseRegion(cursor: SystemMouseCursors.click, child: Padding(
              padding: EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              child: Text('编辑', style: TextStyle(fontSize: 12)),
            )),
          ),
          
          PopupMenuButton<String>(
            offset: const Offset(0, 35),
            itemBuilder: (context) => const [
              PopupMenuItem(
                height: 25,
                value: 'zoom_in',
                child: Text('放大', style: TextStyle(fontSize: 12)),
              ),
              PopupMenuItem(
                height: 25,
                value: 'zoom_out',
                child: Text('缩小', style: TextStyle(fontSize: 12)),
              ),
              PopupMenuItem(
                height: 25,
                value: 'reset_zoom',
                child: Text('重置缩放', style: TextStyle(fontSize: 12)),
              ),
            ],
            onSelected: (value) {},
            child: const MouseRegion(cursor: SystemMouseCursors.click, child: Padding(
              padding: EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              child: Text('视图', style: TextStyle(fontSize: 12)),
            )),
          ),
          
          PopupMenuButton<String>(
            offset: const Offset(0, 35),
            itemBuilder: (context) => const [
              PopupMenuItem(
                height: 25,
                value: 'run',
                child: Text('运行', style: TextStyle(fontSize: 12)),
              ),
              PopupMenuItem(
                height: 25,
                value: 'debug',
                child: Text('调试', style: TextStyle(fontSize: 12)),
              ),
            ],
            onSelected: (value) {},
            child: const MouseRegion(cursor: SystemMouseCursors.click, child: Padding(
              padding: EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              child: Text('运行', style: TextStyle(fontSize: 12)),
            )),
          ),
        ],
      ),
    );
  }

  Widget _buildTabBar(WorkbenchProvider provider, BuildContext context, WidgetRef ref) {
    final notifier = ref.read(workbenchProvider.notifier);
    
    return Container(
      height: 40,
      color: Colors.grey[200],
      child: Listener(
        onPointerSignal: (event) {
          if (event is PointerScrollEvent) {
            final delta = event.scrollDelta.dy;
            _tabScrollController.jumpTo(_tabScrollController.offset + delta);
          }
        },
        child: RawScrollbar(
          controller: _tabScrollController,
          thumbVisibility: true,
          thickness: 4,
          radius: const Radius.circular(2),
          child: ListView.builder(
            controller: _tabScrollController,
            scrollDirection: Axis.horizontal,
            physics: const ClampingScrollPhysics(),
            itemCount: provider.openedFiles.length,
            itemBuilder: (context, index) {
              final file = provider.openedFiles[index];
              final isActive = provider.activeFileIndex == index;
              final isSettings = file.path == 'settings://';
              
              final displayName = notifier.getFileName(file.path);
              
              return GestureDetector(
                onTap: () => notifier.setActiveFile(index),
                child: Tooltip(
                  message: file.path,
                  child: Container(
                    constraints: const BoxConstraints(maxWidth: 200),
                    decoration: BoxDecoration(
                      color: isActive ? Colors.white : Colors.grey[300],
                      border: Border(
                        bottom: BorderSide(
                          color: isActive ? Theme.of(context).primaryColor : Colors.transparent,
                          width: 2,
                        ),
                      ),
                    ),
                    padding: const EdgeInsets.symmetric(horizontal: 16),
                    child: Row(
                      children: [
                        if (isSettings) const Icon(Icons.settings, size: 16),
                        Expanded(
                          child: Text(
                            displayName,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              color: isActive ? Colors.black : Colors.grey[700],
                            ),
                          ),
                        ),
                        const SizedBox(width: 8),
                        InkWell(
                          onTap: () {
                            if (isSettings) {
                              notifier.closeSettings();
                            } else {
                              notifier.closeFile(index);
                            }
                          },
                          child: file.isModified
                              ? Container(
                                  width: 12,
                                  height: 12,
                                  margin: const EdgeInsets.symmetric(vertical: 6),
                                  decoration: BoxDecoration(
                                    color: Theme.of(context).primaryColor,
                                    shape: BoxShape.circle,
                                  ),
                                )
                              : const Icon(Icons.close, size: 16),
                        ),
                      ],
                    ),
                  ),
                ),
              );
            },
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final provider = ref.watch(workbenchProvider);
    
    return Scaffold(
      body: Column(
        children: [
          _buildMenuBar(context, ref),
          _buildTabBar(provider, context, ref),
          Expanded(
            child: Row(
              children: [
                Container(
                  width: 48,
                  color: Colors.grey[200],
                  child: Column(
                    children: [
                      _buildActivityBarItem(context, Icons.explore, '资源管理器', 0, provider, ref),
                      _buildActivityBarItem(context, Icons.search, '搜索', 1, provider, ref),
                      _buildActivityBarItem(context, Icons.source, '源代码管理', 2, provider, ref),
                      const Spacer(),
                      _buildActivityBarItem(context, Icons.settings, '设置', 3, provider, ref),
                    ],
                  ),
                ),
                if (provider.isSidebarVisible) ...[
                  AnimatedContainer(
                    duration: const Duration(milliseconds: 200),
                    curve: Curves.easeInOut,
                    width: provider.sidebarWidth,
                    child: _buildSidebarContent(provider.activeSidebarTab, context, ref),
                  ),
                  MouseRegion(
                    cursor: SystemMouseCursors.resizeLeftRight,
                    child: GestureDetector(
                      behavior: HitTestBehavior.translucent,
                      onHorizontalDragUpdate: (details) {
                        double newWidth = provider.sidebarWidth + details.delta.dx;
                        newWidth = newWidth.clamp(120.0, 400.0);
                        ref.read(workbenchProvider.notifier).updateSidebarWidth(newWidth);
                      },
                      child: Container(
                        width: 6,
                        color: Colors.grey[300],
                      ),
                    ),
                  ),
                ],
                Expanded(child: _EditorArea(provider: provider)),
              ],
            ),
          ),
          // Bottom status bar showing editor/file metadata
          Container(
            height: 28,
            color: Colors.grey[100],
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: Row(
              children: [
                const Icon(Icons.code, size: 16),
                const SizedBox(width: 8),
                Expanded(
                  child: Row(
                    children: [
                      Expanded(child: Text('行: ${provider.editorLine} 列: ${provider.editorColumn}  选中: ${provider.selectionCount}  缩进: ${provider.firstLineIndent}', style: const TextStyle(fontSize: 12))),
                      const SizedBox(width: 8),
                      // Encoding selector
                      PopupMenuButton<String>(
                        tooltip: '文件编码',
                        initialValue: provider.encoding,
                        onSelected: (v) {
                          ref.read(workbenchProvider.notifier).setEncoding(v);
                        },
                        itemBuilder: (context) => const [
                          PopupMenuItem(value: 'utf-8', child: Text('utf-8')), 
                          PopupMenuItem(value: 'gbk', child: Text('gbk')),
                          PopupMenuItem(value: 'utf-16le', child: Text('utf-16le')),
                          PopupMenuItem(value: 'utf-16be', child: Text('utf-16be')),
                          PopupMenuItem(value: 'windows-1252', child: Text('windows-1252')),
                        ],
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Icon(Icons.language, size: 14),
                            const SizedBox(width: 4),
                            Text(provider.encoding, style: const TextStyle(fontSize: 12)),
                            const Icon(Icons.arrow_drop_down, size: 16),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 12),
                Text(provider.activeFileIndex >= 0 && provider.activeFileIndex < provider.openedFiles.length ? '大小: ${_humanFileSize(provider.openedFiles[provider.activeFileIndex].path)}' : '', style: const TextStyle(fontSize: 12)),
              ],
            ),
          ),
        ],
      ),
    );
  }

  String _humanFileSize(String path) {
    try {
      final file = File(path);
      if (!file.existsSync()) return '';
      final len = file.lengthSync();
        if (len < 1024) return '$len B';
      if (len < 1024 * 1024) return '${(len / 1024).toStringAsFixed(1)} KB';
      return '${(len / (1024 * 1024)).toStringAsFixed(2)} MB';
    } catch (e) {
      return '';
    }
  }
}

class _EditorArea extends StatelessWidget { // 改为 StatelessWidget
  final WorkbenchProvider provider;
  
  const _EditorArea({required this.provider});

  @override
  Widget build(BuildContext context) {
    if (provider.isLoading) {
      return const Center(child: CircularProgressIndicator());
    }
    
    if (provider.openedFiles.isEmpty) {
      return _buildEmptyState();
    }
    
    if (provider.activeFileIndex < 0 || 
        provider.activeFileIndex >= provider.openedFiles.length) {
      return _buildEmptyState();
    }
    
    final file = provider.openedFiles[provider.activeFileIndex];
    final path = file.path.toLowerCase();
    final ext = path.split('.').last;
    
    if (const [
      'dart', 'py', 'c', 'cpp', 'h', 'hpp', 'java', 'js', 'ts', 
      'lua', 'go', 'rs', 'php', 'html', 'css', 'xml', 'json', 'yaml', 'yml', 'md'
    ].contains(ext)) {
      return _CodeEditor(content: file.content, language: _getLanguageFromExtension(ext), provider: provider, filePath: file.path);
    } 
    else if (const [
      'hive',
    ].contains(ext)) {
      return _CodeEditor(content: file.content, language: json, provider: provider, filePath: file.path);
    }
    else if (const [
      'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'ico', 'jfif'
    ].contains(ext)) {
      return file.bytes != null 
          ? _ImagePreview(bytes: file.bytes!)
          : const Center(child: Text('图片加载失败'));
    }
    else if (const [
      'mp4', 'mov', 'avi', 'mkv', 'webm', 'mp3', 'wav', 'flac', 'aac', 'ogg', 'm4a'
    ].contains(ext)) {
      return _MediaPlayer(filePath: file.path, bytes: file.bytes);
    }
    else if (const ['txt', 'log', 'ini', 'conf', 'cfg', 'env'].contains(ext)) {
      return _TextEditor(content: file.content, provider: provider, filePath: file.path);
    } 
    else if (const ['ppt', 'pptx', 'doc', 'docx', 'xls', 'xlsx'].contains(ext)) {
      return _OfficeFilePreview(filePath: file.path, bytes: file.bytes);
    }
    else if (path == 'settings://') {
      return const SettingsPanel();
    } 
    else if (const ['obj', 'stl', 'glb', 'gltf'].contains(ext)) {
      return _ModelViewer(filePath: file.path, bytes: file.bytes);
    }
    else {
      return _UnsupportedFilePreview(path: file.path);
    }
  }

  Mode _getLanguageFromExtension(String ext) {
    switch (ext) {
      case 'py': return python;
      case 'c': case 'h': case 'cpp': case 'hpp': return cpp;
      case 'java': return java;
      case 'js': return javascript;
      case 'ts': return typescript;
      case 'lua': return lua;
      case 'go': return go;
      case 'rs': return rust;
      case 'php': return php;
      case 'css': return css_lang.css;
      case 'xml': case 'html': return xml_lang.xml;
      case 'json': return json;
      case 'yaml': case 'yml': return yaml;
      case 'md': return markdown;
      case 'hive': return json;
      default: return dart;
    }
  }

  Widget _buildEmptyState() {
    return const Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.description, size: 80, color: Colors.grey),
          SizedBox(height: 20),
          Text('打开或创建文件开始工作', style: TextStyle(fontSize: 18)),
        ],
      ),
    );
  }
}

class _ImagePreview extends StatelessWidget {
  final Uint8List bytes;
  
  const _ImagePreview({required this.bytes});

  @override
  Widget build(BuildContext context) {
    return Container(
      color: Colors.grey[100],
      child: Center(
        child: Image.memory(
          bytes,
          fit: BoxFit.contain,
          errorBuilder: (context, error, stackTrace) {
            return Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Icon(Icons.broken_image, size: 48, color: Colors.grey),
                const SizedBox(height: 10),
                Text('图片加载失败: $error'),
              ],
            );
          },
        ),
      ),
    );
  }
}

class _MediaPlayer extends StatefulWidget {
  final String filePath;
  final Uint8List? bytes;

  const _MediaPlayer({required this.filePath, this.bytes});

  @override
  State<_MediaPlayer> createState() => _MediaPlayerState();
}

class _MediaPlayerState extends State<_MediaPlayer> {
  VideoPlayerController? _videoController;
  AudioPlayer? _audioPlayer;
  // ignore: unused_field
  AudioEventHandler? _audioEventHandler;
  Map<Duration, String> lyrics = {};
  bool isLoadingLyrics = false;
  bool _isPlaying = false;
  Duration _duration = Duration.zero;
  Duration _position = Duration.zero;
  bool _isInitialized = false;
  bool _isDisposing = false;
  File? _tempVideoFile;
  bool _isBuffering = false;
  String? _errorMessage;
  String? _webVideoUrl;
  RootIsolateToken? _isolateToken;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _isolateToken = RootIsolateToken.instance;
      _initializePlayer();
    });
  }

  Future<void> _executeOnMainThread(Future<void> Function() action) async {
    final completer = Completer<void>();
    SchedulerBinding.instance.scheduleTask(() async {
      try {
        await action();
        completer.complete();
      } catch (e) {
        debugPrint('操作失败: $e');
        completer.completeError(e);
      }
    }, Priority.animation);
    return completer.future;
  }

  Future<void> _play() async {
    await _executeOnMainThread(() async {
      if (_audioPlayer != null && mounted) {
        await _audioPlayer!.resume();
      }
      _loadLyrics(path.setExtension(widget.filePath, '.lrc'));
    });
  }

  Future<void> _pause() async {
    await _executeOnMainThread(() async {
      if (_audioPlayer != null && mounted) {
        await _audioPlayer!.pause();
      }
    });
  }

  Future<void> _loadLyrics(String audioFilePath) async {
    final lrcPath = audioFilePath.replaceFirst(RegExp(r'\.[^\.]+$'), '.lrc');
    try {
      final file = File(lrcPath);
      if (await file.exists()) {
        final lrcContent = await file.readAsString();
        final parsedLyrics = LrcParser.parseLrc(lrcContent);
        setState(() {
          lyrics = parsedLyrics;
        });
      }
    } catch (e) {
      log('Failed to load lyrics: $e');
    } finally {
      setState(() {
        isLoadingLyrics = false;
      });
    }
  }

  Future<File> _createTempVideoFile(Uint8List bytes) async {
    final tempDir = await getTemporaryDirectory();
    final tempFile = File('${tempDir.path}/temp_video_${DateTime.now().millisecondsSinceEpoch}.mp4');
    await tempFile.writeAsBytes(bytes);
    return tempFile;
  }

  Future<void> _initializePlayer() async {
    if (_isolateToken != null) {
      BackgroundIsolateBinaryMessenger.ensureInitialized(_isolateToken!);
    }
    await _executeOnMainThread(() async {
      await _disposePlayers();
      _errorMessage = null;
      _webVideoUrl = null;
      
      try {
        if (_isVideoFile(widget.filePath)) {
          if (isWeb) { 
            // Web平台的替代解决方案
            if (widget.bytes != null) {
              final html.Blob blob = html.Blob([widget.bytes!], 'video/mp4');
              _webVideoUrl = html.Url.createObjectUrl(blob);
            } else {
              _webVideoUrl = widget.filePath;
            }
            setState(() => _isInitialized = true);
            return;
          }
          
          setState(() => _isBuffering = true);
          
          if (widget.bytes != null) {
            // 修复问题1: 确保传递非空的字节数据
            _tempVideoFile = await _createTempVideoFile(widget.bytes!);
            // 修复问题2: 确保传递非空的文件对象
            _videoController = VideoPlayerController.file(_tempVideoFile!);
          } else {
            final file = File(widget.filePath);
            final exists = await file.exists();
            if (!exists) throw Exception('文件不存在: ${widget.filePath}');
            _videoController = VideoPlayerController.file(file);
          }
          
          await _videoController!.initialize().then((_) {
            if (!mounted) return;
            setState(() {
              _duration = _videoController!.value.duration;
              _isInitialized = true;
              _isBuffering = false;
            });
            // 自动播放
            _videoController!.play();
            setState(() => _isPlaying = true);
          }).catchError((error) {
            if (!mounted) return;
            setState(() {
              _errorMessage = _getErrorMessage(error);
              _isInitialized = true;
              _isBuffering = false;
            });
          });

          _videoController!.addListener(_updateVideoProgress);
          
        } else if (_isAudioFile(widget.filePath)) {
          _audioPlayer = AudioPlayer();

          debugPrint('test1');
          
          if (widget.bytes != null) {
            await _audioPlayer!.setSource(BytesSource(widget.bytes!));
          } else {
            final file = File(widget.filePath);
            final exists = await file.exists();
            if (!exists) throw Exception('文件不存在: ${widget.filePath}');
            debugPrint('test2');
            await _audioPlayer!.setSource(DeviceFileSource(file.path));
          }

          debugPrint('test3');
          
          // 创建并保存AudioEventHandler实例
          _audioEventHandler = AudioEventHandler(
            player: _audioPlayer!,
            onDurationChanged: (duration) {
              _safeSetState(() => _duration = duration);
            },
            onPositionChanged: (position) {
              _safeSetState(() => _position = position);
            },
            onPlayerStateChanged: (state) {
              if (mounted) setState(() => _isPlaying = state == PlayerState.playing);
            },
            onPlayerComplete: () {
              if (mounted) setState(() => _isPlaying = false);
            }
          );
          
          // 直接获取音频时长
          final duration = await _audioPlayer!.getDuration();
          if (duration != null && mounted) {
            setState(() => _duration = duration);
          }

          if (!mounted) return;
          setState(() => _isInitialized = true);
        }
      } catch (e) {
        if (!mounted) return;
        setState(() {
          _errorMessage = _getErrorMessage(e);
          _isInitialized = true;
          _isBuffering = false;
        });
      }
    });
  }

  String _getErrorMessage(dynamic error) {
    if (error is UnimplementedError) {
      return '视频播放失败: 当前平台不支持该视频格式';
    } else if (error is PlatformException) {
      return '平台异常: ${error.message}';
    } else {
      return error.toString();
    }
  }

  void _safeSetState(void Function() fn) {
    if (!mounted) return;
    
    SchedulerBinding.instance.scheduleTask(
      () {
        if (mounted) setState(fn);
      },
      Priority.animation,
    );
  }

  void _updateVideoProgress() {
    if (!mounted || _videoController == null) return;
    
    _safeSetState(() {
      _position = _videoController!.value.position;
      _duration = _videoController!.value.duration;
      _isPlaying = _videoController!.value.isPlaying;
      _isBuffering = _videoController!.value.isBuffering;
    });
  }

  bool _isVideoFile(String path) {
    final ext = path.toLowerCase().split('.').last;
    return ['mp4', 'mov', 'avi', 'mkv', 'webm'].contains(ext);
  }

  bool _isAudioFile(String path) {
    final ext = path.toLowerCase().split('.').last;
    return ['mp3', 'wav', 'flac', 'aac', 'ogg', 'm4a'].contains(ext);
  }

  Future<void> _disposePlayers() async {
    if (_isDisposing) return;
    _isDisposing = true;
    
    try {
      if (_videoController != null) {
        _videoController!.removeListener(_updateVideoProgress);
        await _videoController?.dispose();
        _videoController = null;
      }
      
      if (_audioPlayer != null) {
        await _audioPlayer?.dispose();
        _audioPlayer = null;
      }
      
      // 清理Web URL
      if (_webVideoUrl != null) {
        html.Url.revokeObjectUrl(_webVideoUrl!);
        _webVideoUrl = null;
      }
    } finally {
      _isDisposing = false;
    }
    
    if (mounted) {
      setState(() {
        _isPlaying = false;
        _duration = Duration.zero;
        _position = Duration.zero;
      });
    }
  }

  @override
  void dispose() {
    _audioEventHandler = null;
    _disposePlayers().then((_) {
      if (_tempVideoFile != null && _tempVideoFile!.existsSync()) {
        _tempVideoFile!.deleteSync();
      }
    });
    // _audioEventHandler.dispose(); // 释放事件处理器资源
    super.dispose();
  }

  @override
  void didUpdateWidget(covariant _MediaPlayer oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.filePath != oldWidget.filePath || 
        widget.bytes != oldWidget.bytes) {
      _initializePlayer();
    }
  }

  Widget _buildInfoItem(String title, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8.0),
      child: Row(
        children: [
          Text(
            '$title: ',
            style: const TextStyle(fontWeight: FontWeight.bold),
          ),
          Text(value),
        ],
      ),
    );
  }
  
  // 计算振幅（模拟）
  double _calculateAmplitude() {
    return (_position.inMilliseconds % 1000) / 10.0;
  }
  
  // 计算音调（模拟）
  double _calculatePitch() {
    return 440.0 + (_position.inMilliseconds % 1000) / 10.0;
  }
  
  // 描述音色（模拟）
  String _describeTimbre() {
    final progress = _position.inMilliseconds / _duration.inMilliseconds;
    if (progress < 0.3) return "明亮";
    if (progress < 0.6) return "温暖";
    return "深沉";
  }

  @override
  Widget build(BuildContext context) {
    if (!_isInitialized) {
      return const Center(child: CircularProgressIndicator());
    }
    
    if (widget.filePath.isEmpty) {
      return const Center(child: Text('请选择一个文件'));
    }
    
    if (_errorMessage != null) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error, size: 48, color: Colors.red),
            const SizedBox(height: 16),
            Text('ERROR: $_errorMessage', textAlign: TextAlign.center),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: _initializePlayer,
              child: const Text('重试'),
            ),
          ],
        ),
      );
    }

    if (_isAudioFile(widget.filePath)) {
      // _audioPlayer = AudioPlayer();
      // 使用AudioEventHandler包装器
      AudioEventHandler(
        player: _audioPlayer!,
        onDurationChanged: (duration) {
          _safeSetState(() => _duration = duration); // 使用安全的状态更新
        },
        onPositionChanged: (position) {
          _safeSetState(() => _position = position); // 使用安全的状态更新
        },
        onPlayerStateChanged: (state) {
          if (mounted) setState(() => _isPlaying = state == PlayerState.playing);
        },
        onPlayerComplete: () { // 使用新的回调名称
          if (mounted) setState(() => _isPlaying = false);
        }
      );
    }
    // Web视频替代方案
    if (_webVideoUrl != null) {
      return Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(Icons.videocam, size: 100),
          const SizedBox(height: 20),
          const Text('当前浏览器不支持内置视频播放', style: TextStyle(fontSize: 16)),
          const SizedBox(height: 10),
          Text('视频格式: ${widget.filePath.split('.').last}'),
          const SizedBox(height: 20),
          ElevatedButton(
            onPressed: () {
              launchUrl(Uri.parse(_webVideoUrl!));
            },
            child: const Text('在新标签页中打开视频'),
          ),
        ],
      );
    }
    
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        if (_isVideoFile(widget.filePath) && 
            _videoController != null && 
            _videoController!.value.isInitialized)
          Expanded(
            child: AspectRatio(
              aspectRatio: _videoController!.value.aspectRatio,
              child: Stack(
                children: [
                  VideoPlayer(_videoController!),
                  if (_isBuffering)
                    const Center(child: CircularProgressIndicator()),
                  if (!_videoController!.value.isPlaying && !_isBuffering)
                    Center(
                      child: Container(
                        padding: const EdgeInsets.all(8),
                        decoration: BoxDecoration(
                          color: Colors.black54,
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: const Icon(Icons.play_arrow, size: 50, color: Colors.white),
                      ),
                    ),
                ],
              ),
            ),
          )
        else if (_isAudioFile(widget.filePath))
          Padding(
            padding: const EdgeInsets.all(16.0),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                AudioVisualizer(
                  audioPlayer: _audioPlayer!,
                  height: 50,
                ),
                // 振幅信息
                _buildInfoItem('振幅', '${_calculateAmplitude()} dB'),
                
                // 音调信息
                _buildInfoItem('主音调', '${_calculatePitch()} Hz'),
                
                // 音色信息
                _buildInfoItem('音色特征', _describeTimbre()),
                
                // 其他音频信息
                _buildInfoItem('采样率', '44.1 kHz'),
                _buildInfoItem('位深度', '16 bit'),
                _buildInfoItem('声道', '立体声'),
              ],
            ),
          ),
          const SizedBox(height: 20),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              IconButton(
                icon: const Icon(Icons.skip_previous),
                onPressed: () {},
              ),
              IconButton(
                icon: Icon(_isPlaying ? Icons.pause : Icons.play_arrow),
                onPressed: _isPlaying ? _pause : _play,
              ),
              IconButton(
                icon: const Icon(Icons.skip_next),
                onPressed: () {},
              ),
            ],
          ),
          if (_duration.inMilliseconds > 0)
            Slider(
              value: _position.inMilliseconds.toDouble(),
              min: 0,
              max: _duration.inMilliseconds.toDouble(),
              onChanged: (value) async {
                await _executeOnMainThread(() async {
                  await _audioPlayer!.seek(Duration(milliseconds: value.toInt()));
                });
              },
            )
          else
            const LinearProgressIndicator(),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16.0),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(_formatDuration(_position)),
                Text(_formatDuration(_duration)),
              ],
            ),
          ),
          Expanded(
            child: isLoadingLyrics
                ? const Center(child: CircularProgressIndicator())
                : LyricsDisplay(
                    lyrics: lyrics,
                    currentPosition: _position,
                  ),
          ),
      ],
    );
  }
  
  String _formatDuration(Duration duration) {
    String twoDigits(int n) => n.toString().padLeft(2, '0');
    final hours = duration.inHours;
    final minutes = duration.inMinutes.remainder(60);
    final seconds = duration.inSeconds.remainder(60);
    
    return hours > 0 
      ? '${twoDigits(hours)}:${twoDigits(minutes)}:${twoDigits(seconds)}' 
      : '${twoDigits(minutes)}:${twoDigits(seconds)}';
  }
}

class _UnsupportedFilePreview extends StatelessWidget {
  final String path;
  
  const _UnsupportedFilePreview({required this.path});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(Icons.block, size: 80, color: Colors.grey),
          const SizedBox(height: 20),
          Text('不支持的文件类型: ${path.split('.').last}'),
          const SizedBox(height: 10),
          Text(path, style: const TextStyle(fontSize: 12)),
        ],
      ),
    );
  }
}

class _CodeEditor extends StatefulWidget {
  final String content;
  final Mode language;
  final WorkbenchProvider provider;
  final String filePath;
  
  const _CodeEditor({required this.content, required this.language, required this.provider, required this.filePath});

  @override
  State<_CodeEditor> createState() => _CodeEditorState();
}

class _CodeEditorState extends State<_CodeEditor> {
  late final CodeController controller;
  final ScrollController _scrollController = ScrollController();
  bool _internalUpdate = false;

  @override
  void initState() {
    super.initState();
    controller = CodeController(
      language: widget.language,
      text: widget.content,
    );

    // register controller so menu actions (cut/copy/paste) can act on it
    widget.provider.registerEditorController(widget.filePath, controller);

    controller.addListener(() {
      if (_internalUpdate) return;
      final text = controller.text;
      // push content changes to provider
      widget.provider.updateFileContent(text);

      // selection and cursor
      final sel = controller.selection;
      final offset = sel.baseOffset.clamp(0, text.length);
      final prefix = text.substring(0, offset);
      final lines = prefix.split('\n');
      final line = lines.length;
      final column = lines.isNotEmpty ? lines.last.length + 1 : 1;
      final selectionCount = (sel.end - sel.start).abs();

      // first non-empty line indentation
      final firstLine = text.split('\n').firstWhere((l) => l.trim().isNotEmpty, orElse: () => '');
      final indentMatch = RegExp(r'^[ \t]*').firstMatch(firstLine);
      final firstIndent = indentMatch?.group(0) ?? '';

      widget.provider.updateEditorStatus(
        line: line,
        column: column,
        selectionCount: selectionCount,
        firstLineIndent: firstIndent,
      );
    });
  }

  @override
  void didUpdateWidget(covariant _CodeEditor oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.content != controller.text) {
      _internalUpdate = true;
      controller.text = widget.content;
      _internalUpdate = false;
    }
  }

  @override
  void dispose() {
    widget.provider.unregisterEditorController(widget.filePath);
    controller.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      controller: _scrollController,
      child: CodeTheme(
        data: CodeThemeData(styles: const {
          'keyword': TextStyle(color: Colors.blue),
          'comment': TextStyle(color: Colors.green),
          'string': TextStyle(color: Colors.red),
          'number': TextStyle(color: Colors.purple),
          'class': TextStyle(color: Colors.orange),
          'function': TextStyle(color: Colors.teal),
        }),
        child: CodeField(
          controller: controller,
          textStyle: const TextStyle(fontFamily: 'monospace', fontSize: 16),
        ),
      ),
    );
  }
}

class _TextEditor extends StatefulWidget {
  final String content;
  final WorkbenchProvider provider;
  final String filePath;

  const _TextEditor({required this.content, required this.provider, required this.filePath});

  @override
  State<_TextEditor> createState() => _TextEditorState();
}

class _TextEditorState extends State<_TextEditor> {
  late final TextEditingController _controller;
  bool _internalUpdate = false;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: widget.content);
    widget.provider.registerEditorController(widget.filePath, _controller);
    _controller.addListener(() {
      if (_internalUpdate) return;
      final text = _controller.text;
      widget.provider.updateFileContent(text);

      final sel = _controller.selection;
      final offset = sel.baseOffset.clamp(0, text.length);
      final prefix = text.substring(0, offset);
      final lines = prefix.split('\n');
      final line = lines.length;
      final column = lines.isNotEmpty ? lines.last.length + 1 : 1;
      final selectionCount = (sel.end - sel.start).abs();

      final firstLine = text.split('\n').firstWhere((l) => l.trim().isNotEmpty, orElse: () => '');
      final indentMatch = RegExp(r'^[ \t]*').firstMatch(firstLine);
      final firstIndent = indentMatch?.group(0) ?? '';

      widget.provider.updateEditorStatus(line: line, column: column, selectionCount: selectionCount, firstLineIndent: firstIndent);
    });
  }

  @override
  void didUpdateWidget(covariant _TextEditor oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.content != _controller.text) {
      _internalUpdate = true;
      _controller.text = widget.content;
      _internalUpdate = false;
    }
  }

  @override
  void dispose() {
    widget.provider.unregisterEditorController(widget.filePath);
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        return SingleChildScrollView(
          child: ConstrainedBox(
            constraints: BoxConstraints(
              minHeight: constraints.maxHeight,
            ),
            child: IntrinsicHeight(
              child: TextField(
                controller: _controller,
                maxLines: null,
                expands: true,
                decoration: const InputDecoration(
                  border: InputBorder.none,
                  contentPadding: EdgeInsets.all(16),
                ),
                style: const TextStyle(fontFamily: 'monospace', fontSize: 16),
              ),
            ),
          ),
        );
      },
    );
  }
}

class _OfficeFilePreview extends StatelessWidget {
  final String filePath;
  final Uint8List? bytes;

  const _OfficeFilePreview({required this.filePath, this.bytes});

  @override
  Widget build(BuildContext context) {
    final fileName = path.basename(filePath);
    final extension = path.extension(filePath).toLowerCase();
    
    IconData icon;
    switch (extension) {
      case '.ppt':
      case '.pptx':
        icon = Icons.slideshow;
        break;
      case '.doc':
      case '.docx':
        icon = Icons.description;
        break;
      case '.xls':
      case '.xlsx':
        icon = Icons.table_chart;
        break;
      default:
        icon = Icons.insert_drive_file;
    }

    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 80, color: Colors.grey),
          const SizedBox(height: 20),
          Text(fileName, style: const TextStyle(fontSize: 16)),
          const SizedBox(height: 10),
          const Text('Office文件预览需要外部应用'),
          const SizedBox(height: 20),
          ElevatedButton.icon(
            icon: const Icon(Icons.open_in_new),
            label: const Text('用外部应用打开'),
            onPressed: () => _openWithExternalApp(context),
          ),
        ],
      ),
    );
  }

  Future<void> _openWithExternalApp(BuildContext context) async {
    try {
      final file = File(filePath);
      if (!await file.exists() && context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('文件不存在')),
        );
        return;
      }

      await launchUrl(Uri.file(filePath));
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('打开失败: $e')),
        );
      }
    }
  }
}

class _ModelViewer extends StatefulWidget {
  final String filePath;
  final Uint8List? bytes;

  const _ModelViewer({required this.filePath, this.bytes});

  @override
  State<_ModelViewer> createState() => _ModelViewerState();
}

class _ModelViewerState extends State<_ModelViewer> {
  late final WebViewController _controller;
  bool _isLoading = true;
  bool _hasError = false;

  @override
  void initState() {
    super.initState();
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted);
    _prepareModelViewer();
  }

  Future<void> _prepareModelViewer() async {
    try {
      setState(() {
        _isLoading = true;
        _hasError = false;
      });
      
      // 加载3D模型查看器
      _controller.loadRequest(Uri.parse('https://3dviewer.net'));
      
      setState(() {
        _isLoading = false;
      });
    } catch (e) {
      setState(() {
        _isLoading = false;
        _hasError = true;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoading) {
      return const Center(child: CircularProgressIndicator());
    }
    
    if (_hasError) {
      return const Center(child: Text('无法加载3D模型查看器'));
    }
    
    return Column(
      children: [
        Expanded(
          child: WebViewWidget(controller: _controller),
        ),
        Container(
          padding: const EdgeInsets.all(8),
          color: Colors.grey[200],
          child: Row(
            children: [
              const Icon(Icons.info_outline, size: 16),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  '文件: ${path.basename(widget.filePath)}',
                  style: const TextStyle(fontSize: 12),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class FlattenedNode {
  final FileNode node;
  final int depth;
  
  FlattenedNode(this.node, this.depth);
  
  bool get isDirectory => node.isDirectory;
  bool get isExpanded => node.isExpanded;
  String get name => node.name;
  String get path => node.path;
  List<FileNode> get children => node.children;
}