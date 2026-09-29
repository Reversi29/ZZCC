// lib/presentation/pages/chat/brain_chat_page.dart
//
// Brain AI chat page — sends user messages to /brain/ask and renders
// cognition results as chat bubbles. Conversation history is kept in-memory.
// Brain AI is a global system service, no login required.

import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:dio/dio.dart';

import '../../../core/services/config_service.dart';
import '../../../core/di/service_locator.dart';
import '../../../data/models/chat_message.dart';
import '../../widgets/chat/message_bubble.dart';

/// A single turn in the brain conversation.
class _BrainTurn {
  final String userText;
  final String brainText;
  final String? decision;
  final double? confidence;
  final int reasoningLevel;
  final DateTime timestamp;

  _BrainTurn({
    required this.userText,
    required this.brainText,
    this.decision,
    this.confidence,
    required this.reasoningLevel,
    required this.timestamp,
  });
}

class BrainChatPage extends StatefulWidget {
  const BrainChatPage({super.key});

  @override
  State<BrainChatPage> createState() => _BrainChatPageState();
}

class _BrainChatPageState extends State<BrainChatPage> {
  final List<_BrainTurn> _turns = [];
  final TextEditingController _inputCtrl = TextEditingController();
  final ScrollController _scrollCtrl = ScrollController();
  final FocusNode _focusNode = FocusNode();
  bool _isThinking = false;
  String? _error;

  late final Dio _dio;

  @override
  void initState() {
    super.initState();
    final config = getIt<ConfigService>();

    // Brain AI 是全局系统服务，不需要 chat auth token
    _dio = Dio(BaseOptions(
      baseUrl: config.nebulaApiBaseUrl,
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 60),
      headers: {'Content-Type': 'application/json'},
    ));
  }

  bool get _isAuthed => true;  // Brain AI 无需登录

  @override
  void dispose() {
    _inputCtrl.dispose();
    _scrollCtrl.dispose();
    _focusNode.dispose();
    _dio.close();
    super.dispose();
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollCtrl.hasClients) {
        _scrollCtrl.animateTo(
          _scrollCtrl.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  Future<void> _send() async {
    final text = _inputCtrl.text.trim();
    if (text.isEmpty || _isThinking) return;

    _inputCtrl.clear();
    _focusNode.requestFocus();
    setState(() {
      _isThinking = true;
      _error = null;
    });

    try {
      final resp = await _dio.post('brain/ask', data: jsonEncode({
        'question': text,
        'execute_actions': true,
      }));

      final data = resp.data as Map<String, dynamic>;
      final cognition = (data['cognition'] as Map<String, dynamic>?) ?? {};
      final decision = cognition['decision'] as String? ?? 'unknown';
      final confidence = (cognition['confidence'] as num?)?.toDouble();
      final reasoning = cognition['reasoning'] as String? ?? '';
      final reasoningLevel = cognition['reasoning_level'] as int? ?? 0;

      // 从 action_results / actions 提取回复文本
      // LLM 把用户可见回复放在 action.reason（chat_reply/reply 类型）
      String? replyText;
      final actionResults = (data['action_results'] as List?) ?? [];
      for (final ar in actionResults) {
        if (ar is Map && (ar['action'] == 'chat_reply' || ar['action'] == 'reply')) {
          replyText = (ar['reply_text'] as String?) ?? (ar['reason'] as String?) ?? null;
          if (replyText != null && replyText.isNotEmpty) break;
        }
      }
      if (replyText == null || replyText.isEmpty) {
        final actions = (cognition['actions'] as List?) ?? [];
        for (final a in actions) {
          if (a is Map && (a['type'] == 'chat_reply' || a['type'] == 'reply')) {
            replyText = (a['reason'] as String?) ?? null;
            if (replyText != null && replyText.isNotEmpty) break;
          }
        }
      }

      // 只展示用户可见文本（LLM 回复或推理文本），不暴露内部元信息
      final displayText = (replyText != null && replyText.isNotEmpty)
          ? replyText
          : (reasoning.isNotEmpty ? reasoning : '');

      setState(() {
        _turns.add(_BrainTurn(
          userText: text,
          brainText: displayText,
          decision: decision,
          confidence: confidence,
          reasoningLevel: reasoningLevel,
          timestamp: DateTime.now(),
        ));
        _isThinking = false;
      });
      _scrollToBottom();
    } on DioException catch (e) {
      final resp = e.response;
      final detail = resp != null && resp.data is Map
          ? (resp.data['detail'] ?? '')
          : '';
      final msg = detail.isNotEmpty ? detail.toString() : (e.message ?? e.type.name);
      setState(() {
        _isThinking = false;
        _error = msg;
      });
    } catch (e) {
      setState(() {
        _isThinking = false;
        _error = '错误: $e';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Row(
          children: [
            CircleAvatar(
              radius: 16,
              backgroundColor: const Color(0xFF00d4ff),
              child: const Icon(Icons.psychology, size: 18, color: Colors.white),
            ),
            const SizedBox(width: 8),
            const Text('Brain AI'),
          ],
        ),
        actions: [
          // Brain AI 就绪状态指示
          Container(
            margin: const EdgeInsets.symmetric(horizontal: 4, vertical: 8),
            decoration: BoxDecoration(
              color: Colors.green.withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(8),
            ),
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            child: Text(
              '就绪',
              style: TextStyle(
                fontSize: 11,
                color: Colors.green,
                fontWeight: FontWeight.w500,
              ),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.info_outline),
            onPressed: () => _showInfo(context),
          ),
        ],
      ),
      body: Column(
        children: [
          if (_error != null)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              color: Colors.red.withValues(alpha: 0.1),
              child: Row(
                children: [
                  const Icon(Icons.error_outline, color: Colors.red, size: 16),
                  const SizedBox(width: 8),
                  Expanded(child: Text(_error!, style: const TextStyle(color: Colors.red, fontSize: 12))),
                  IconButton(
                    icon: const Icon(Icons.close, size: 14),
                    onPressed: () => setState(() => _error = null),
                    padding: EdgeInsets.zero,
                    constraints: const BoxConstraints(minWidth: 20),
                  ),
                ],
              ),
            ),
          Expanded(child: _buildConversation()),
          _buildInput(),
        ],
      ),
    );
  }

  Widget _buildConversation() {
    if (_turns.isEmpty && !_isThinking) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.psychology, size: 64, color: Colors.grey[400]),
            const SizedBox(height: 16),
            Text(
              'Brain AI 已就绪',
              style: TextStyle(fontSize: 18, color: Colors.grey[500]),
            ),
            const SizedBox(height: 8),
            Text(
              '输入问题或描述场景，Brain 会进行推理并返回决策',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 13, color: Colors.grey[400]),
            ),
            const SizedBox(height: 16),
            // Quick suggestion chips
            Wrap(
              spacing: 8,
              children: [
                _suggestionChip('今天有什么需要决策的？'),
                _suggestionChip('分析一下当前系统状态'),
                _suggestionChip('有什么可以优化的？'),
              ],
            ),
          ],
        ),
      );
    }

    return ListView.builder(
      controller: _scrollCtrl,
      padding: const EdgeInsets.symmetric(vertical: 8),
      itemCount: _turns.length + (_isThinking ? 1 : 0),
      itemBuilder: (context, index) {
        if (index == _turns.length && _isThinking) {
          return _buildThinkingBubble();
        }
        final turn = _turns[index];
        final userMsg = ChatMessage(
          eventId: 'u_$index',
          sender: '@me',
          timestamp: turn.timestamp.millisecondsSinceEpoch,
          body: turn.userText,
          isMe: true,
        );
        final brainMsg = ChatMessage(
          eventId: 'b_$index',
          sender: '@brain',
          timestamp: turn.timestamp.millisecondsSinceEpoch + 1,
          body: turn.brainText,
          isMe: false,
        );
        return Column(
          children: [
            MessageBubble(message: userMsg, showSender: false),
            MessageBubble(message: brainMsg, showSender: true),
          ],
        );
      },
    );
  }

  Widget _suggestionChip(String text) {
    return ActionChip(
      label: Text(text, style: const TextStyle(fontSize: 12)),
      onPressed: () {
        _inputCtrl.text = text;
        _focusNode.requestFocus();
        _send();
      },
      backgroundColor: Theme.of(context).colorScheme.surfaceContainerHighest,
    );
  }

  Widget _buildThinkingBubble() {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4, horizontal: 12),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surfaceContainerHighest,
          borderRadius: const BorderRadius.only(
            topLeft: Radius.circular(20),
            topRight: Radius.circular(20),
            bottomRight: Radius.circular(20),
            bottomLeft: Radius.circular(4),
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            SizedBox(
              width: 16,
              height: 16,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                color: Theme.of(context).primaryColor,
              ),
            ),
            const SizedBox(width: 8),
            Text(
              'Brain 思考中...',
              style: TextStyle(
                color: Theme.of(context).colorScheme.onSurface,
                fontSize: 14,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildInput() {
    return SafeArea(
      child: Container(
        padding: const EdgeInsets.all(8),
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surface,
          border: Border(
            top: BorderSide(
              color: Theme.of(context).colorScheme.outline.withValues(alpha: 0.2),
            ),
          ),
        ),
        child: Row(
          children: [
            Expanded(
              child: TextField(
                controller: _inputCtrl,
                focusNode: _focusNode,
                enabled: _isAuthed,
                decoration: InputDecoration(
                  hintText: _isAuthed ? '向 Brain AI 提问...' : '请先登录',
                  filled: true,
                  fillColor: Theme.of(context).colorScheme.surfaceContainerHighest,
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(24),
                    borderSide: BorderSide.none,
                  ),
                  contentPadding: const EdgeInsets.symmetric(
                    horizontal: 16,
                    vertical: 12,
                  ),
                ),
                textInputAction: TextInputAction.send,
                onSubmitted: (_) => _send(),
                maxLines: null,
              ),
            ),
            const SizedBox(width: 8),
            IconButton.filled(
              onPressed: (_isThinking || !_isAuthed) ? null : _send,
              icon: _isThinking
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: Colors.white,
                      ),
                    )
                  : const Icon(Icons.psychology),
            ),
          ],
        ),
      ),
    );
  }

  void _showInfo(BuildContext context) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Brain AI'),
        content: const Text(
          'Brain AI 是 ZZCC 类脑系统的推理接口。\n\n'
          '它通过 L1 规则 → L2 记忆推理 → L3 语义推理三层引擎，\n'
          '对输入信号进行分析并返回决策和置信度。\n\n'
          '对话不会存储到聊天服务器，仅在当前会话中保持。\n'
          '需要账号认证后才能使用。',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('知道了'),
          ),
        ],
      ),
    );
  }
}
