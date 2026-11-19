import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../api_client.dart';
import '../../auth_state.dart';
import 'chat_model.dart';

class TanyaAiPage extends StatefulWidget {
  const TanyaAiPage({super.key});

  @override
  State<TanyaAiPage> createState() => _TanyaAiPageState();
}

class _TanyaAiPageState extends State<TanyaAiPage> {
  final _input = TextEditingController();
  final _scroll = ScrollController();
  final List<ChatMessage> _messages = [
    ChatMessage(
      'Halo! Saya siap membantu perawatan stroberi hidroponik Anda.',
      fromAi: true,
    ),
  ];
  bool _waiting = false;

  static const _suggestions = [
    'Kenapa daun stroberi menguning?',
    'Jadwal penyiraman yang ideal?',
    'Cara mencegah embun tepung?',
  ];

  @override
  void dispose() {
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _send([String? suggestion]) async {
    final text = (suggestion ?? _input.text).trim();
    if (text.isEmpty || text.length > 1000 || _waiting) return;
    _input.clear();
    setState(() {
      _messages.add(ChatMessage(text, fromAi: false));
      _waiting = true;
    });
    _scrollToEnd();
    try {
      final history = _messages.length > 1
          ? _messages
                .sublist(0, _messages.length - 1)
                .reversed
                .take(10)
                .toList()
                .reversed
                .toList()
          : <ChatMessage>[];
      final answer = await askAi(context.read<AuthState>().api, text, history);
      if (mounted)
        setState(() => _messages.add(ChatMessage(answer, fromAi: true)));
    } on ApiException catch (error) {
      if (mounted)
        setState(
          () =>
              _messages.add(ChatMessage('Gagal: ${error.pesan}', fromAi: true)),
        );
    } finally {
      if (mounted) {
        setState(() => _waiting = false);
        _scrollToEnd();
      }
    }
  }

  void _scrollToEnd() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.animateTo(
          _scroll.position.maxScrollExtent,
          duration: const Duration(milliseconds: 250),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        if (_messages.length == 1)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
            child: Wrap(
              spacing: 8,
              runSpacing: 8,
              children: _suggestions
                  .map(
                    (suggestion) => ActionChip(
                      label: Text(suggestion),
                      onPressed: () => _send(suggestion),
                    ),
                  )
                  .toList(),
            ),
          ),
        Expanded(
          child: ListView.builder(
            controller: _scroll,
            padding: const EdgeInsets.all(16),
            itemCount: _messages.length + (_waiting ? 1 : 0),
            itemBuilder: (_, index) {
              if (_waiting && index == _messages.length) {
                return const Align(
                  alignment: Alignment.centerLeft,
                  child: Padding(
                    padding: EdgeInsets.all(12),
                    child: CircularProgressIndicator(),
                  ),
                );
              }
              final message = _messages[index];
              return Align(
                alignment: message.fromAi
                    ? Alignment.centerLeft
                    : Alignment.centerRight,
                child: Container(
                  constraints: const BoxConstraints(maxWidth: 340),
                  margin: const EdgeInsets.only(bottom: 10),
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: message.fromAi
                        ? Theme.of(context).colorScheme.surfaceContainerHighest
                        : Theme.of(context).colorScheme.primary,
                    borderRadius: BorderRadius.circular(16),
                  ),
                  child: Text(
                    message.text,
                    style: TextStyle(
                      color: message.fromAi
                          ? null
                          : Theme.of(context).colorScheme.onPrimary,
                    ),
                  ),
                ),
              );
            },
          ),
        ),
        SafeArea(
          top: false,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(12, 4, 12, 12),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Expanded(
                  child: TextField(
                    controller: _input,
                    maxLines: 4,
                    minLines: 1,
                    maxLength: 1000,
                    decoration: const InputDecoration(
                      hintText: 'Tanyakan tentang greenhouse...',
                    ),
                    onSubmitted: (_) => _send(),
                  ),
                ),
                IconButton(
                  onPressed: _waiting ? null : _send,
                  icon: const Icon(Icons.send),
                  tooltip: 'Kirim',
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}
