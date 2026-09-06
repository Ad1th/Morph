"""Capture orchestrator: runs all collectors and assembles an EnvironmentProfile."""

from morph.profiler.collectors.cpu import collect_cpu
from morph.profiler.collectors.filesystem import collect_filesystem
from morph.profiler.collectors.locale_info import collect_locale
from morph.profiler.collectors.memory import collect_memory
from morph.profiler.collectors.os_info import collect_os
from morph.profiler.collectors.process_limits import collect_process_limits
from morph.schema.profile import EnvironmentProfile


def capture_environment() -> EnvironmentProfile:
    """Collects the current machine's environment into a structured profile."""
    return EnvironmentProfile(
        os=collect_os(),
        cpu=collect_cpu(),
        memory=collect_memory(),
        locale=collect_locale(),
        filesystem=collect_filesystem(),
        process=collect_process_limits(),
    )


if __name__ == "__main__":
    print(capture_environment().model_dump_json(indent=2))
