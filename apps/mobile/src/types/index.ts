export type FamilyRole = 'ADMIN' | 'ADULT_MEMBER' | 'CHILD_MEMBER';

export interface User {
  user_id: string;
  email: string;
  display_name: string;
  is_active: boolean;
  family_id: string;
  membership_id: string;
  family_role: FamilyRole;
  family_name: string;
}

export interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
}

export interface Message {
  id: string;
  sender_type: 'USER' | 'AGENT' | 'SYSTEM';
  content: string;
  content_type: 'TEXT' | 'STRUCTURED' | 'TRANSCRIPTION';
  metadata_json?: Record<string, unknown>;
  created_at: string;
}

export interface ProductCandidate {
  id: string;
  title: string;
  brand?: string;
  price_amount?: number;
  currency?: string;
  merchant?: string;
  product_url?: string;
  image_url?: string;
  availability?: string;
  delivery_estimate?: string;
  warranty_details?: string;
  return_details?: string;
  specifications_json?: Record<string, unknown>;
  source_type: 'REAL_PROVIDER' | 'DEVELOPMENT_CATALOGUE';
  provider: string;
  score?: number;
  rank?: number;
}

export interface PurchaseTask {
  id: string;
  family_id: string;
  conversation_id?: string;
  original_request: string;
  status: string;
  budget_amount?: number;
  currency?: string;
  selected_product_id?: string;
  approval_state: string;
  execution_state: string;
  created_at: string;
  updated_at: string;
}

export interface ChatResponse {
  conversation_id: string;
  message_id: string;
  agent_type: string;
  reply: string;
  task_id?: string;
  task_status?: string;
  structured_response?: Record<string, unknown>;
  candidates?: ProductCandidate[];
  available_actions: string[];
  correlation_id: string;
  is_development_data: boolean;
}

export interface ApprovalRequest {
  id: string;
  family_id: string;
  purchase_task_id: string;
  approval_type: string;
  status: 'PENDING' | 'APPROVED' | 'DENIED' | 'EXPIRED' | 'CANCELLED';
  request_payload_json: Record<string, unknown>;
  decision_reason?: string;
  created_at: string;
  expires_at?: string;
}

export interface MobileUseInstruction {
  id: string;
  family_id: string;
  purchase_task_id: string;
  action_type: string;
  target_type: string;
  payload_json: Record<string, unknown>;
  status: string;
  idempotency_key: string;
  created_at: string;
  updated_at: string;
}

export interface PermissionGrant {
  id: string;
  family_id: string;
  subject_membership_id: string;
  resource: string;
  action: string;
  effect: 'ALLOW' | 'DENY';
  approval_required: boolean;
  constraints_json: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface FamilyMember {
  membership_id: string;
  user_id: string;
  email: string;
  display_name: string;
  family_role: string;
  membership_status: string;
  created_at: string;
}

export interface ApiError {
  code: string;
  message: string;
  correlation_id: string;
  details?: Record<string, unknown>;
}
