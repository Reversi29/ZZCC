<!-- Auto-crafted guidance to help AI coding agents become immediately productive in this repo. -->
# Copilot / AI Agent Instructions

Keep this short and actionable — focus on repository structure, essential workflows, and project-specific conventions.

- Architecture: Flutter app following a layered/domain-driven structure.
  - Key folders: `lib/data/` (models, repositories, data sources), `lib/domain/` (entities, usecases, repo interfaces), `lib/presentation/` (pages, widgets, `providers`), `lib/core/` (services, DI, routing, theme, utils).
  - Dependency injection: `get_it` service locator in `lib/core/di/service_locator.dart`. Register any new app-wide service here and ensure initialization happens before `runApp`.
  - State management: `flutter_riverpod` with generated providers (see `presentation/providers/*`). Providers are often overridden in `main.dart` during `ProviderScope` startup.

- Startup flow (important):
  - `lib/main.dart` calls `await setupServiceLocator();` — service locator initialization must complete before creating services that depend on `ConfigService`/`StorageService`.
  - `StorageService.init(configService.appDataPath)` is called during setup; many services rely on `configService.appDataPath` and on `StorageService` being registered.
  - Automatic login logic and provider overrides for `userProvider` and `appLocaleProvider` live in `main.dart` — inspect this file when debugging startup/login issues.

- Native and platform notes:
  - Windows-specific native integration uses FFI; see `native/include/torrent_c_api.h` (required when building custom `torrent-rasterbar.dll`).
  - There is a helper `windows/copy_dlls.bat` and `windows/zzcc_config.json` for packaging native DLLs. On Windows ensure DLLs are built and copied before running.
  - `main.dart` contains a Windows console exit handler that calls cleanup on `TorrentService` (via `kernel32.dll`). Be careful when changing service lifecycles.

- Code generation and build steps (must-run for dev):
  - Install deps: `flutter pub get`.
  - Generate Riverpod/hive/codegen artifacts: `flutter pub run build_runner build --delete-conflicting-outputs`.
  - Generate Flutter localizations (if needed): `flutter gen-l10n` (project has `l10n.yaml` and `lib/l10n` assets).
  - Typical run commands:
    - Debug on Windows: `flutter run -d windows` (ensure native DLLs are present)
    - Build release: `flutter build windows` / `flutter build apk` / `flutter build ios` as appropriate

- Testing and linting:
  - Run unit/widget tests: `flutter test`.
  - Project uses `flutter_lints` and `analysis_options.yaml` — run `dart analyze` or use IDE linter.

- Patterns & conventions you should follow (discoverable in code):
  - Services: create an abstract (if needed) and register in `service_locator.dart`. Initialize in `setupServiceLocator()` before `runApp`.
  - Providers: prefer Riverpod `Notifier`/`StateNotifier` patterns found under `presentation/providers/`. When instantiating app-level singletons override providers in `main.dart`.
  - Storage / Config: use `ConfigService` and `StorageService` for file paths and persisted state; do not hardcode paths — use `configService.appDataPath`.
  - Logging: use `LoggerService` obtained from `getIt<LoggerService>()` rather than print statements.

- Integration and cross-component calls:
  - `EventBus` is registered in the service locator — used for cross-cutting events.
  - `TorrentService` is a key long-lived service; dispose it on exit (see `main.dart` cleanup).

- Files and locations to inspect for context when making changes:
  - `lib/core/di/service_locator.dart` — service registration and initialization order.
  - `lib/main.dart` — startup sequence, provider overrides, auto-login flow, and platform-specific handling.
  - `lib/presentation/providers/` — Riverpod providers and patterns.
  - `lib/data/` and `lib/domain/` — data/repository boundaries and domain use-cases.
  - `native/include/torrent_c_api.h` and `windows/copy_dlls.bat` — native build / packaging hints.

If any of these files are unclear or you need run-time access to native DLLs or CI secrets, ask before making changes. Reply with which area (startup, DI, providers, native, or build pipeline) you want to modify and I will provide concrete, minimal edits.

<!-- End of file -->
