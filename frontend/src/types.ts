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
export interface TemplateParameter {
  name: string;
  kind: string | null;
  label: string | null;
  description: string;
  example: string | null;
  source: string | null;
}
export interface Template {
  name: string;
  version: string;
  title: string;
  summary: string;
  active: boolean;
  content_digest: string;
  payload_version: number;
  tool_versions: Record<string, string>;
  supplied_parameters: TemplateParameter[];
  derived_parameters: TemplateParameter[];
  produces: string[];
}
export interface Artifact extends RecordBase {
  application_id: string;
  digest: string;
  size_bytes: number;
  media_type: string;
  kind: "generated_bundle" | "validation_report";
  provenance: {
    template_name?: string;
    template_version?: string;
    template_content_digest?: string;
    parameter_digest?: string;
    parameters?: Record<string, string>;
    scope?: string;
    revision_id?: string;
  };
  created_by: number;
  operation_id: string | null;
}
export interface Revision extends RecordBase {
  application_id: string;
  source_kind: string;
  artifact_id: string;
  artifact_digest: string;
  template_version_id: string;
  binding_id: string;
  binding_version: number;
  bundle_target: string;
  binding_snapshot: {
    id?: string;
    version?: number;
    bundle_target?: string;
    environment?: {
      id?: string;
      version?: number;
      workspace_ref?: string;
      enabled?: boolean;
      allowed_executor?: string;
      allow_self_approval?: boolean;
    };
  };
  config_snapshot: {
    schema_version: number;
    synthetic_row_count: number;
    max_runtime_seconds: number;
  };
  config_digest: string;
  scope_digest: string;
  execution_mode: string;
  requested_by: number;
}
export interface Validation extends RecordBase {
  revision_id: string;
  operation_id: string;
  scope: "offline";
  validator: string;
  validator_version: string;
  tool_versions: Record<string, string>;
  result: "passed" | "failed" | null;
  check_summary: {
    result?: string;
    passed?: number;
    total?: number;
    failed?: string[];
  };
  report_artifact_id: string | null;
  observed_at: string | null;
  requested_by: number;
}
