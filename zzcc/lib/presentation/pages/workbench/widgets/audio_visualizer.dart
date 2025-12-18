// lib/presentation/widgets/audio_visualizer.dart
import 'package:flutter/material.dart';
import 'package:audioplayers/audioplayers.dart';
import 'dart:math';

class AudioVisualizer extends StatefulWidget {
  final AudioPlayer audioPlayer;
  final double height;

  const AudioVisualizer({
    super.key,
    required this.audioPlayer,
    this.height = 200,
  });

  @override
  State<AudioVisualizer> createState() => _AudioVisualizerState();
}

class _AudioVisualizerState extends State<AudioVisualizer> {
  List<double> _waveformData = [];
  List<double> _spectrumData = [];
  bool _isActive = false;

  @override
  void initState() {
    super.initState();
    _startVisualization();
  }

  void _startVisualization() {
    setState(() => _isActive = true);
    _updateVisualizationData();
  }

  void _updateVisualizationData() {
    if (!_isActive) return;
    
    // 生成模拟波形数据（正弦波）
    _waveformData = List.generate(100, (index) {
      return sin(2 * pi * index / 100);
    });
    
    // 生成模拟频谱数据（随机）
    _spectrumData = List.generate(50, (index) => Random().nextDouble());
    
    setState(() {});
    
    // 每100毫秒更新一次数据
    Future.delayed(const Duration(milliseconds: 100), _updateVisualizationData);
  }

  @override
  void dispose() {
    _isActive = false;
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      height: widget.height,
      padding: const EdgeInsets.all(8),
      decoration: BoxDecoration(
        color: Colors.grey[200],
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        children: [
          // 波形可视化
          Expanded(
            child: _buildWaveformVisualizer(),
          ),
          const SizedBox(height: 8),
          // 频谱可视化
          Expanded(
            child: _buildSpectrumVisualizer(),
          ),
        ],
      ),
    );
  }
  
  Widget _buildWaveformVisualizer() {
    if (_waveformData.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }
    
    return CustomPaint(
      painter: WaveformPainter(data: _waveformData, color: Colors.blue),
    );
  }
  
  Widget _buildSpectrumVisualizer() {
    if (_spectrumData.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }
    
    return CustomPaint(
      painter: SpectrumPainter(data: _spectrumData, color: Colors.green),
    );
  }
}

class WaveformPainter extends CustomPainter {
  final List<double> data;
  final Color color;
  
  WaveformPainter({required this.data, required this.color});
  
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..strokeWidth = 2
      ..style = PaintingStyle.stroke;
    
    final path = Path();
    final xStep = size.width / (data.length - 1);
    
    path.moveTo(0, size.height / 2);
    
    for (int i = 0; i < data.length; i++) {
      final x = i * xStep;
      final y = size.height / 2 - data[i] * size.height / 4;
      path.lineTo(x, y);
    }
    
    canvas.drawPath(path, paint);
  }
  
  @override
  bool shouldRepaint(covariant WaveformPainter oldDelegate) {
    return oldDelegate.data != data;
  }
}

class SpectrumPainter extends CustomPainter {
  final List<double> data;
  final Color color;
  
  SpectrumPainter({required this.data, required this.color});
  
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.fill;
    
    final barWidth = size.width / data.length;
    
    for (int i = 0; i < data.length; i++) {
      final barHeight = data[i] * size.height;
      final x = i * barWidth;
      final y = size.height - barHeight;
      
      canvas.drawRect(
        Rect.fromLTWH(x, y, barWidth - 1, barHeight),
        paint,
      );
    }
  }
  
  @override
  bool shouldRepaint(covariant SpectrumPainter oldDelegate) {
    return oldDelegate.data != data;
  }
}