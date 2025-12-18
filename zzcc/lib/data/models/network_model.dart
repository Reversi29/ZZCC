enum DeviceType {
  desktop,
  laptop,
  mobile,
  tablet,
  tv,
  nas,
  printer,
  other,
}

enum ServiceType {
  fileShare,
  remoteDesktop,
  mediaServer,
  webServer,
  ssh,
  ftp,
  other,
}

class NetworkInfo {
  final String ipAddress;
  final String subnetMask;
  final String gateway;
  final List<String> dnsServers;
  final String connectionType;
  final int signalStrength; // 0-100%
  final double uploadSpeed; // Mbps
  final double downloadSpeed; // Mbps
  final bool isConnected;

  const NetworkInfo({
    required this.ipAddress,
    required this.subnetMask,
    required this.gateway,
    required this.dnsServers,
    required this.connectionType,
    required this.signalStrength,
    required this.uploadSpeed,
    required this.downloadSpeed,
    required this.isConnected,
  });
}

class NetworkDevice {
  final String id;
  final String name;
  final String ipAddress;
  final String macAddress;
  final DeviceType deviceType;
  final bool isOnline;

  const NetworkDevice({
    required this.id,
    required this.name,
    required this.ipAddress,
    required this.macAddress,
    required this.deviceType,
    required this.isOnline,
  });

  // 添加fromJson工厂方法
  factory NetworkDevice.fromJson(Map<String, dynamic> json) {
    return NetworkDevice(
      id: json['id'] as String,
      name: json['name'] as String,
      ipAddress: json['ipAddress'] as String,
      macAddress: json['macAddress'] as String,
      deviceType: DeviceType.values.firstWhere(
        (e) => e.name == json['deviceType'],
        orElse: () => DeviceType.other,
      ),
      isOnline: json['isOnline'] as bool,
    );
  }
}

class NetworkService {
  final String name;
  final ServiceType type;
  final int port;
  final bool isAvailable;

  const NetworkService({
    required this.name,
    required this.type,
    required this.port,
    required this.isAvailable,
  });
}