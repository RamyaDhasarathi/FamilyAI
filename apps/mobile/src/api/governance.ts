import apiClient from './client';
import { ApprovalRequest, FamilyMember, PermissionGrant } from '../types';

export const getFamilyMembersApi = async (): Promise<FamilyMember[]> => {
  const resp = await apiClient.get<FamilyMember[]>('/api/v1/families/current/members');
  return resp.data;
};

export const getMemberPermissionsApi = async (membershipId: string): Promise<PermissionGrant[]> => {
  const resp = await apiClient.get<PermissionGrant[]>(
    `/api/v1/governance/members/${membershipId}/permissions`
  );
  return resp.data;
};

export const createPermissionApi = async (data: {
  subject_membership_id: string;
  resource: string;
  action: string;
  effect: 'ALLOW' | 'DENY';
  approval_required?: boolean;
  constraints_json?: Record<string, unknown>;
}): Promise<PermissionGrant> => {
  const resp = await apiClient.post<PermissionGrant>('/api/v1/governance/permissions', data);
  return resp.data;
};

export const updatePermissionApi = async (
  permissionId: string,
  data: {
    effect?: 'ALLOW' | 'DENY';
    approval_required?: boolean;
    is_active?: boolean;
    constraints_json?: Record<string, unknown>;
  }
): Promise<PermissionGrant> => {
  const resp = await apiClient.patch<PermissionGrant>(
    `/api/v1/governance/permissions/${permissionId}`,
    data
  );
  return resp.data;
};

export const deletePermissionApi = async (permissionId: string): Promise<void> => {
  await apiClient.delete(`/api/v1/governance/permissions/${permissionId}`);
};

export const getPendingApprovalsApi = async (): Promise<ApprovalRequest[]> => {
  const resp = await apiClient.get<ApprovalRequest[]>('/api/v1/approvals/pending');
  return resp.data;
};

export const approveRequestApi = async (approvalId: string, reason?: string) => {
  const resp = await apiClient.post(`/api/v1/approvals/${approvalId}/approve`, { reason });
  return resp.data;
};

export const denyRequestApi = async (approvalId: string, reason?: string) => {
  const resp = await apiClient.post(`/api/v1/approvals/${approvalId}/deny`, { reason });
  return resp.data;
};
