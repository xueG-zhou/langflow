export interface ManagedComponentMetadata {
  namespaced_id: string;
  class_name: string;
  display_name: string;
  description: string;
  documentation?: string | null;
  icon?: string | null;
  inputs: Array<Record<string, unknown>>;
  outputs: Array<Record<string, unknown>>;
}

export interface ManagedComponentBundle {
  id: string;
  bundle_name: string;
  extension_id: string;
  version: string;
  description?: string | null;
  components: ManagedComponentMetadata[];
  status: "ACTIVE" | "DISABLED" | "ERROR";
  origin: "SYSTEM" | "MANAGED";
  can_disable: boolean;
  error?: string | null;
  uploaded_by?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ManagedComponentUsage {
  id: string;
  name: string;
  node_count: number;
}

export interface ManagedComponentDetail extends ManagedComponentBundle {
  source_code: string;
  usage_count: number;
  usages: ManagedComponentUsage[];
}
