export interface User {
  id: number;
  username: string;
  email: string;
  is_active: boolean;
  is_platform_admin: boolean;
}
export interface RecordBase {
  id: string;
  created_at: string;
}
export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}
export interface Team extends RecordBase {
  name: string;
}
export interface Member extends RecordBase {
  user_id: number;
  team_id: string;
}
export interface Application extends RecordBase {
  slug: string;
  name: string;
  description: string;
  owning_team_id: string;
  owner_user_id: number;
  data_owner_user_id: number;
  repository_url: string;
  bundle_root: string;
  repository_verified_at: string | null;
  lifecycle: string;
  version: number;
  updated_at: string;
  created_by: number;
}
export interface Capabilities {
  edit_metadata: boolean;
  manage_access: boolean;
  manage_bindings: boolean;
  operate: boolean;
}
export interface Role extends RecordBase {
  user_id: number | null;
  team_id: string | null;
  role: string;
}
export interface Environment extends RecordBase {
  name: string;
  workspace_ref: string;
  enabled: boolean;
  allowed_executor: "simulated";
  allowed_bundle_targets: string[];
  allow_self_approval: boolean;
  version: number;
  updated_at: string;
}
export interface Binding extends RecordBase {
  application_id: string;
  environment_id: string;
  environment: Environment;
  bundle_target: string;
  config: {
    schema_version: number;
    synthetic_row_count: number;
    max_runtime_seconds: number;
  };
  version: number;
  usable: boolean;
}
export interface Audit extends RecordBase {
  actor_user_id: number | null;
  actor_kind: string;
  action: string;
  target_type: string;
  target_id: string;
  outcome: string;
  request_id: string;
  details: Record<string, unknown>;
}
export interface Operation extends RecordBase {
  application_id: string;
  kind: string;
  status: string;
  execution_mode: string;
  attempt_count: number;
  max_attempts: number;
  cancel_requested: boolean;
  diagnostic_code: string | null;
  observed_at: string | null;
  heartbeat_at: string | null;
  lease_expires_at: string | null;
  available_at: string;
  requested_by: number;
  retry_of: string | null;
}
export interface Attempt extends RecordBase {
  phase: string;
  correlation_id: string;
  outcome: string;
  diagnostic_code: string | null;
  finished_at: string | null;
}
