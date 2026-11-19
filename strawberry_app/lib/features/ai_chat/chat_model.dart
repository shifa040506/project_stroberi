import '../../api_client.dart';

class ChatMessage {
  ChatMessage(this.text, {required this.fromAi});

  final String text;
  final bool fromAi;
}

Future<String> askAi(
  ApiClient api,
  String prompt,
  List<ChatMessage> history,
) async {
  final response = await api.post('/api/ai/tanya', {
    'pesan': prompt,
    'riwayat': history
        .map(
          (message) => {
            'peran': message.fromAi ? 'model' : 'user',
            'teks': message.text,
          },
        )
        .toList(),
  }, timeout: const Duration(seconds: 45));
  return (response['jawaban'] ?? '').toString();
}
