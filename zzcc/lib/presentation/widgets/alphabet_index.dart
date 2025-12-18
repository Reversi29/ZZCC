import 'package:flutter/material.dart';
import 'package:zzcc/data/models/message_model.dart'; // 修正导入路径

class AlphabetIndexListView extends StatefulWidget {
  final List<ContactGroup> groups;
  final VoidCallback onAddGroup;
  
  const AlphabetIndexListView({
    super.key,
    required this.groups,
    required this.onAddGroup,
  });

  @override
  State<AlphabetIndexListView> createState() => _AlphabetIndexListViewState();
}

class _AlphabetIndexListViewState extends State<AlphabetIndexListView> {
  final ScrollController _scrollController = ScrollController();
  final Map<String, GlobalKey> _sectionKeys = {};
  final List<String> _letters = [];

  @override
  void initState() {
    super.initState();
    _initLetters();
  }

  @override
  void didUpdateWidget(covariant AlphabetIndexListView oldWidget) {
    super.didUpdateWidget(oldWidget);
    // If the groups changed, rebuild letters and section keys so scrolling
    // targets remain valid. This prevents null contexts and freezes when
    // trying to ensureVisible on a section that was removed/replaced.
    if (oldWidget.groups != widget.groups) {
      _letters.clear();
      _sectionKeys.clear();
      _initLetters();
    }
  }

  void _initLetters() {
    for (var group in widget.groups) {
      if (group.name.isEmpty) continue;
      final firstLetter = group.name[0].toUpperCase();
      if (!_letters.contains(firstLetter)) {
        _letters.add(firstLetter);
      }
    }
    _letters.sort();
    
    // 为每个分组创建唯一键
    for (var group in widget.groups) {
      _sectionKeys[group.name] = GlobalKey();
    }
  }

  void _scrollToSection(String sectionName) {
    final key = _sectionKeys[sectionName];
    if (key == null) return;
    final ctx = key.currentContext;
    if (ctx == null) {
      // If the target context isn't available yet, schedule for next frame.
      WidgetsBinding.instance.addPostFrameCallback((_) {
        final retryCtx = key.currentContext;
        if (retryCtx != null) {
          try {
            Scrollable.ensureVisible(retryCtx, duration: const Duration(milliseconds: 300), curve: Curves.easeInOut);
          } catch (_) {}
        }
      });
      return;
    }

    try {
      Scrollable.ensureVisible(ctx, duration: const Duration(milliseconds: 300), curve: Curves.easeInOut);
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        // 联系人列表
        ListView.builder(
          controller: _scrollController,
          itemCount: widget.groups.length + 1, // +1 用于添加分组按钮
          itemBuilder: (context, index) {
            if (index == 0) return _buildAddGroupButton();
            
            final group = widget.groups[index - 1];
            return _buildContactGroup(group);
          },
        ),
        
        // 字母索引
        Positioned(
          right: 4,
          top: 0,
          bottom: 0,
          child: Container(
            padding: const EdgeInsets.symmetric(vertical: 8),
            alignment: Alignment.center,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                // 添加分组按钮
                InkWell(
                  onTap: widget.onAddGroup,
                  child: const Icon(Icons.add, size: 16),
                ),
                const SizedBox(height: 8),
                
                // 字母索引
                ..._letters.map((letter) => InkWell(
                  onTap: () => _scrollToSection(letter),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(vertical: 2),
                    child: Text(
                      letter,
                      style: const TextStyle(fontSize: 14),
                    ),
                  ),
                )),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildAddGroupButton() {
    return ListTile(
      leading: const Icon(Icons.add_circle_outline),
      title: const Text('添加新分组'),
      onTap: widget.onAddGroup,
    );
  }

  Widget _buildContactGroup(ContactGroup group) {
    return Column(
      key: _sectionKeys[group.name],
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // 分组标题
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          child: Text(
            group.name,
            style: const TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.bold,
            ),
          ),
        ),
        
        // 分组内联系人
        ...group.contacts.map((contact) => ListTile(
          leading: const CircleAvatar(
            backgroundImage: NetworkImage('https://picsum.photos/200'),
          ),
          title: Text(contact.name),
          subtitle: Text(contact.lastMessage),
          trailing: Text(contact.time),
          onTap: () {},
        )),
        
        const Divider(height: 1),
      ],
    );
  }
}