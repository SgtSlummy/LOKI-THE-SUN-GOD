from __future__ import annotations

import sys

sys.dont_write_bytecode = True

if __package__:
    from .windows_service_common import NativeServiceFramework, ServiceSpec, handle_command_line
else:  # pragma: no cover - direct service-management invocation
    from windows_service_common import NativeServiceFramework, ServiceSpec, handle_command_line


DASHBOARD_SERVICE_SPEC = ServiceSpec(
    service_name="LokiTHESunGodDashboard",
    display_name="Loki THE SUN GOD Dashboard",
    description="LOKI local operator dashboard",
    script_name="dashboard_app.py",
    environment={
        "DASHBOARD_HOST": "127.0.0.1",
        "DASHBOARD_PORT": "5000",
        "PORT": "5000",
    },
    log_name="dashboard-service.log",
)


class LokiDashboardService(NativeServiceFramework):
    _svc_name_ = DASHBOARD_SERVICE_SPEC.service_name
    _svc_display_name_ = DASHBOARD_SERVICE_SPEC.display_name
    _svc_description_ = DASHBOARD_SERVICE_SPEC.description
    service_spec = DASHBOARD_SERVICE_SPEC


def main() -> int:
    return handle_command_line(LokiDashboardService)


if __name__ == "__main__":
    raise SystemExit(main())
