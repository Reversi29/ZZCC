#!/usr/bin/env python3
import argparse
import os
import sys
from typing import Any, Dict, List


def require_root() -> None:
    if os.geteuid() != 0:
        print("[ERROR] Run as root (use sudo).", file=sys.stderr)
        sys.exit(1)


def ensure_yaml():
    try:
        import yaml  # type: ignore
        return yaml
    except Exception:
        print("[ERROR] PyYAML is required. Run ./check_python_env.sh or install python3-yaml.", file=sys.stderr)
        sys.exit(1)


def read_config_yaml(path: str) -> List[Dict[str, Any]]:
    yaml = ensure_yaml()
    if not os.path.exists(path):
        print(f"[ERROR] Config file not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or []
    if isinstance(data, dict):
        seq = data.get("sequence") or data.get("installations") or []
    elif isinstance(data, list):
        seq = data
    else:
        seq = []
    return [item for item in seq if isinstance(item, dict) and item.get("name")]


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy/Uninstall sequence executor")
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument("-i", "--install", action="store_true", help="Run installation sequence")
    group.add_argument("-u", "--uninstall", action="store_true", help="Run uninstall sequence")
    parser.add_argument("-c", "--config", default=os.environ.get("CONFIG_YAML", "./config.yaml"), help="Path to YAML config")
    args = parser.parse_args()

    require_root()
    seq = read_config_yaml(args.config)

    # Lazy import to keep functions isolated
    import function as funcs  # type: ignore

    # Default to install if neither flag is provided
    if args.uninstall:
        for item in reversed(seq):
            name = str(item.get("name"))
            desc = item.get("description")
            if desc:
                print(f"[STEP] Uninstall {name}: {desc}")
            cfg = item.get("config") or {}
            fn_name = item.get("uninstall_function") or f"uninstall_{name.replace('-', '_')}"
            fn = getattr(funcs, fn_name, None)
            if fn is None:
                print(f"[WARN] Uninstall function not found: {fn_name}; skipping {name}", file=sys.stderr)
            else:
                fn(cfg)
            post_cmd = item.get("uninstall_command")
            if post_cmd:
                print(f"[INFO] Running post-uninstall command: {post_cmd}")
                funcs.run_sh(post_cmd)
        print("[OK] Uninstall sequence completed.")
    else:
        for item in seq:
            name = str(item.get("name"))
            desc = item.get("description")
            if desc:
                print(f"[STEP] {name}: {desc}")
            cfg = item.get("config") or {}
            fn_name = item.get("install_function") or f"install_{name.replace('-', '_')}"
            fn = getattr(funcs, fn_name, None)
            if fn is None:
                print(f"[WARN] Install function not found: {fn_name}; skipping {name}", file=sys.stderr)
            else:
                fn(cfg)
            post_cmd = item.get("command")
            if post_cmd:
                print(f"[INFO] Running post-install command: {post_cmd}")
                funcs.run_sh(post_cmd)
        print("[OK] Installation sequence completed.")


if __name__ == "__main__":
    main()
