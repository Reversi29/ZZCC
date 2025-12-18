class FileTreeResponse {
  final List<FileNode> nodes;
  final String? rootPath;

  FileTreeResponse({required this.nodes, this.rootPath});
}

class FileNode {
  final String name;
  final String path;
  final bool isDirectory;
  List<FileNode> children;
  bool isExpanded;
  int depth;

  FileNode({
    required this.name,
    required this.path,
    required this.isDirectory,
    this.children = const [],
    this.isExpanded = false,
    this.depth = 0,
  });
}