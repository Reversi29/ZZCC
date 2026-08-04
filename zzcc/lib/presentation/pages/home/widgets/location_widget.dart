import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:latlong2/latlong.dart';

import 'package:zzcc/presentation/providers/geo_provider.dart';

class LocationWidget extends ConsumerWidget {
  const LocationWidget({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final geo = ref.watch(geoProvider);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Row(
              children: [
                Icon(Icons.location_on, size: 30),
                SizedBox(width: 10),
                Text('位置信息', style: TextStyle(fontSize: 18)),
              ],
            ),
            const SizedBox(height: 12),
            Container(
              height: 200,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(8),
                color: Colors.grey[200],
              ),
              clipBehavior: Clip.antiAlias,
              child: geo.when(
                loading: () => const Center(child: CircularProgressIndicator()),
                error: (e, _) => Center(
                  child: Padding(
                    padding: const EdgeInsets.all(12.0),
                    child: Text('位置获取失败：$e',
                        style: const TextStyle(color: Colors.red),
                        textAlign: TextAlign.center),
                  ),
                ),
                data: (g) => FlutterMap(
                  options: MapOptions(
                    initialCenter: LatLng(g.latitude, g.longitude),
                    initialZoom: 11.0,
                    interactionOptions: const InteractionOptions(
                      flags: InteractiveFlag.none, // 仅展示，不交互
                    ),
                  ),
                  children: [
                    TileLayer(
                      urlTemplate:
                          'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                      userAgentPackageName: 'com.zzcc.app',
                    ),
                    MarkerLayer(
                      markers: [
                        Marker(
                          point: LatLng(g.latitude, g.longitude),
                          width: 40,
                          height: 40,
                          child: const Icon(Icons.location_pin,
                              color: Colors.red, size: 40),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 10),
            if (geo.hasValue)
              Row(
                children: [
                  const Icon(Icons.location_pin, size: 16),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(geo.value!.displayName),
                  ),
                ],
              ),
          ],
        ),
      ),
    );
  }
}
