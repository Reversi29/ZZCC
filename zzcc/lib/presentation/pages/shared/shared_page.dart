// lib/presentation/pages/shared/shared_page.dart
import 'package:flutter/material.dart';
import 'package:zzcc/presentation/pages/shared/widgets/shared_file_screen.dart';
import 'package:zzcc/presentation/pages/shared/widgets/remote_control_screen.dart';
import 'package:zzcc/presentation/pages/shared/widgets/spu_screen.dart';

class SharedPage extends StatefulWidget {
  const SharedPage({super.key});

  @override
  State<SharedPage> createState() => _SharedPageState();
}

class _SharedPageState extends State<SharedPage> with SingleTickerProviderStateMixin {
  late TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 3, vsync: this); // 修改为3个标签
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Column(
        children: [
          TabBar(
            controller: _tabController,
            labelColor: Colors.blue,
            unselectedLabelColor: Colors.grey,
            tabs: const [
              Tab(icon: Icon(Icons.computer), text: '远程控制'),
              Tab(icon: Icon(Icons.folder_shared), text: '文件共享'),
              Tab(icon: Icon(Icons.memory), text: '算力共享'),
            ],
          ),
          Expanded(
            child: TabBarView(
              controller: _tabController,
              children: const [
                RemoteControlScreen(),
                SharedFileScreen(),
                SPUScreen(),
              ],
            ),
          ),
        ],
      ),
    );
  }
}