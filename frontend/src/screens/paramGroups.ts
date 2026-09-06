// Frontend-only grouping (docs/ui-spec.md section 7's accordions). The
// backend catalog doesn't carry a "group" field -- the groups are a UI
// concept, not a data property, so this mapping lives here.
export const PARAM_GROUPS: { name: string; keys: string[] }[] = [
  {
    name: 'Network',
    keys: ['network_availability', 'connection_type', 'network_latency', 'packet_loss', 'bandwidth', 'jitter'],
  },
  {
    name: 'CPU & Memory',
    keys: [
      'cpu_cores', 'cpu_quota', 'ram_limit', 'memory_pressure', 'swap',
      'cpu_architecture', 'os', 'os_version', 'kernel_version',
    ],
  },
  { name: 'Locale & Time', keys: ['locale', 'timezone'] },
  {
    name: 'Filesystem',
    keys: [
      'filesystem_type', 'disk_space_limit', 'disk_read_latency',
      'disk_write_latency', 'read_only_filesystem', 'case_sensitivity',
    ],
  },
  {
    name: 'Process / Runtime',
    keys: ['process_timeout', 'max_processes', 'thread_limit', 'fd_limit'],
  },
]
