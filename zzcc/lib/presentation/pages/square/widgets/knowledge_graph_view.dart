export 'knowledge_graph_view_stub.dart'
    if (dart.library.io) 'knowledge_graph_view_native.dart'
    if (dart.library.html) 'knowledge_graph_view_web.dart';
