import 'dart:js' as js;
import 'dart:convert';

String getInitialPath() {
  try {
    // Captured by web/index.html before Flutter boots (after history.replaceState),
    // so we do not need to traverse window.location via dart:js proxies.
    final raw = js.context['__autoRegisterInitialPath'];
    if (raw == null) return '/home';
    final path = raw.toString();
    return path.isEmpty ? '/home' : path;
  } catch (_) {
    return '/home';
  }
}

Map<String, String> getAutoRegisterParams() {
  // Read the JSON string captured by web/index.html.
  // NOTE: window.__autoRegisterParams is a JsObject proxy, which has no keys()
  // method in dart:js, so iterating it throws NoSuchMethodError at runtime.
  // Decoding the string form avoids that entirely.
  try {
    final raw = js.context['__autoRegisterParamsJson'];
    if (raw == null) return {};
    final decoded = json.decode(raw.toString());
    if (decoded is! Map) return {};
    final result = <String, String>{};
    decoded.forEach((k, v) => result[k.toString()] = v?.toString() ?? '');
    return result;
  } catch (_) {
    return {};
  }
}
