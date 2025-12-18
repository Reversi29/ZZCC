// theme_selector.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_colorpicker/flutter_colorpicker.dart';
import 'package:zzcc/data/models/theme_model.dart';
import 'package:zzcc/presentation/providers/theme_provider.dart';
import 'package:zzcc/l10n/generated/app_localizations.dart';

class ThemeSelector extends ConsumerWidget {
  final List<CustomTheme> presetThemes;
  
  const ThemeSelector({super.key, required this.presetThemes});

  Widget _buildThemeCard(CustomTheme theme, CustomTheme currentTheme, VoidCallback onTap) {
    final isActive = theme.primaryColor == currentTheme.primaryColor;
    
    return InkWell(
      onTap: onTap,
      child: Container(
        width: 140,
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: isActive ? Colors.blue : Colors.grey, width: isActive ? 2 : 1),
        ),
        child: Column(
          children: [
            Container(
              height: 80,
              decoration: BoxDecoration(
                color: theme.primaryColor,
                borderRadius: BorderRadius.circular(8),
              ),
              child: Center(child: Text(theme.name, style: const TextStyle(color: Colors.white))),
            ),
            const SizedBox(height: 8),
            Text(theme.name, overflow: TextOverflow.ellipsis),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final currentTheme = ref.watch(themeProvider);
    final l10n = AppLocalizations.of(context)!;
    
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(l10n.presetThemes, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
        const SizedBox(height: 10),
        Wrap(
          spacing: 15,
          runSpacing: 15,
          children: presetThemes.map((theme) => 
            _buildThemeCard(theme, currentTheme, 
              () => ref.read(themeProvider.notifier).changeTheme(theme))
          ).toList(),
        ),
        const SizedBox(height: 20),
        Text(l10n.customTheme, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
        const SizedBox(height: 10),
        _buildCustomThemeCard(context, ref, currentTheme),
      ],
    );
  }

  Widget _buildCustomThemeCard(BuildContext context, WidgetRef ref, CustomTheme currentTheme) {
    final l10n = AppLocalizations.of(context)!;
    
    return Card(
      elevation: 2,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            _buildColorSelector(context, ref, l10n.primaryColorLabel, currentTheme.primaryColor,
              (color) => ref.read(themeProvider.notifier).changeTheme(currentTheme.copyWith(primaryColor: color))),
            const SizedBox(height: 12),
            _buildColorSelector(context, ref, l10n.leftSidebarColorLabel, currentTheme.leftSidebarColor ?? Colors.grey[300]!,
              (color) => ref.read(themeProvider.notifier).changeTheme(currentTheme.copyWith(leftSidebarColor: color))),
            const SizedBox(height: 12),
            _buildColorSelector(context, ref, l10n.rightPanelColorLabel, currentTheme.rightPanelColor ?? Colors.grey[100]!,
              (color) => ref.read(themeProvider.notifier).changeTheme(currentTheme.copyWith(rightPanelColor: color))),
          ],
        ),
      ),
    );
  }

  Widget _buildColorSelector(BuildContext context, WidgetRef ref, String title, Color currentColor, ValueChanged<Color> onColorChanged) {
    return ListTile(
      contentPadding: EdgeInsets.zero,
      leading: Container(width: 24, height: 24, color: currentColor),
      title: Text(title),
      trailing: const Icon(Icons.arrow_forward_ios, size: 16),
      onTap: () => _showColorPicker(context, ref, currentColor, onColorChanged),
    );
  }

  void _showColorPicker(BuildContext context, WidgetRef ref, Color currentColor, ValueChanged<Color> onColorChanged) {
    final l10n = AppLocalizations.of(context)!;
    Color selectedColor = currentColor;
    
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(l10n.chooseColor),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              ColorPicker(
                pickerColor: currentColor,
                onColorChanged: (color) => selectedColor = color,
                pickerAreaHeightPercent: 0.7,
              ),
            ],
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: Text(l10n.cancel)),
          ElevatedButton(
            onPressed: () {
              onColorChanged(selectedColor);
              Navigator.pop(context);
            },
            child: Text(l10n.apply),
          ),
        ],
      ),
    );
  }
}