// lib/domain/models/torrent_file.dart
class TorrentFile {
  final String id;
  final String name;
  final String size; // human readable
  final int length; // raw bytes
  final bool selected;
  final bool isFolder;
  final List<TorrentFile>? children;

  TorrentFile({
    required this.id,
    required this.name,
    required this.size,
    required this.length,
    this.selected = true,
    this.isFolder = false,
    this.children,
  });

  TorrentFile copyWith({
    String? id,
    String? name,
    String? size,
    int? length,
    bool? selected,
    bool? isFolder,
    List<TorrentFile>? children,
  }) {
    return TorrentFile(
      id: id ?? this.id,
      name: name ?? this.name,
      size: size ?? this.size,
      length: length ?? this.length,
      selected: selected ?? this.selected,
      isFolder: isFolder ?? this.isFolder,
      children: children ?? this.children,
    );
  }
}