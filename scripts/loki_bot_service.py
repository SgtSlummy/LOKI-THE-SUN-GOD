from __future__ import annotations

import sys

sys.dont_write_bytecode = True

if __package__:
    from .windows_service_common import NativeServiceFramework, ServiceSpec, handle_command_line
else:  # pragma: no cover - direct service-management invocation
    from windows_service_common import NativeServiceFramework, ServiceSpec, handle_command_line


BOT_SERVICE_SPEC = ServiceSpec(
    service_name="LokiTHESunGodBot",
    display_name="Loki THE SUN GOD Bot",
    description="LOKI Discord gateway and local health runtime",
    script_name="local_loki_runtime.py",
    arguments=("--mode", "full", "--host", "127.0.0.1", "--port", "9101"),
    log_name="bot-service.log",
)


class LokiBotService(NativeServiceFramework):
    _svc_name_ = BOT_SERVICE_SPEC.service_name
    _svc_display_name_ = BOT_SERVICE_SPEC.display_name
    _svc_description_ = BOT_SERVICE_SPEC.description
    service_spec = BOT_SERVICE_SPEC


def main() -> int:
    return handle_command_line(LokiBotService)


if __name__ == "__main__":
    raise SystemExit(main())
