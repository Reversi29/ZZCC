// lib/core/services/torrent_service.dart
//
// Conditional import: uses FFI version on native, stub on web.
export 'torrent_service_stub.dart'
    if (dart.library.ffi) 'torrent_service_io.dart';
