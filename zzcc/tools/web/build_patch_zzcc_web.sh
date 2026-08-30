#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
/opt/homebrew/share/flutter/bin/flutter build web --release
node "$(dirname "$0")/patch_flutter_bootstrap.js" build/web/flutter_bootstrap.js
