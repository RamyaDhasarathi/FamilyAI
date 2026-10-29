import React, { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import {
  getFamilyMembersApi,
  getMemberPermissionsApi,
  getPendingApprovalsApi,
  approveRequestApi,
  denyRequestApi,
  updatePermissionApi,
} from '../src/api/governance';
import { ErrorBanner } from '../src/components/ErrorBanner';
import { Header } from '../src/components/Header';
import { SidebarDrawer } from '../src/components/SidebarDrawer';
import { useAuthStore } from '../src/state/authStore';
import { ApprovalRequest, FamilyMember, PermissionGrant } from '../src/types';

export default function GovernanceScreen() {
  const { user } = useAuthStore();
  const [drawerOpen, setDrawerOpen] = useState(false);

  const [members, setMembers] = useState<FamilyMember[]>([]);
  const [selectedMember, setSelectedMember] = useState<FamilyMember | null>(null);
  const [permissions, setPermissions] = useState<PermissionGrant[]>([]);
  const [pendingApprovals, setPendingApprovals] = useState<ApprovalRequest[]>([]);

  const [loading, setLoading] = useState(false);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const isAdmin = user?.family_role === 'ADMIN';

  useEffect(() => {
    if (isAdmin) {
      loadInitialData();
    }
  }, [isAdmin]);

  const loadInitialData = async () => {
    setLoading(true);
    setErrorMessage(null);
    try {
      const [mems, approvals] = await Promise.all([
        getFamilyMembersApi(),
        getPendingApprovalsApi(),
      ]);
      setMembers(mems);
      setPendingApprovals(approvals);

      // Select first non-admin member or first member
      if (mems.length > 0) {
        const target = mems.find((m) => m.membership_id !== user?.membership_id) || mems[0];
        setSelectedMember(target);
        await loadMemberGrants(target.membership_id);
      }
    } catch (err: unknown) {
      const msg = err && typeof err === 'object' && 'message' in err ? String(err.message) : 'Failed to load governance data';
      setErrorMessage(msg);
    } finally {
      setLoading(false);
    }
  };

  const loadMemberGrants = async (membershipId: string) => {
    setLoading(true);
    try {
      const grants = await getMemberPermissionsApi(membershipId);
      setPermissions(grants);
    } catch (err: unknown) {
      const msg = err && typeof err === 'object' && 'message' in err ? String(err.message) : 'Failed to load member permissions';
      setErrorMessage(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectMember = async (member: FamilyMember) => {
    setSelectedMember(member);
    setSuccessMessage(null);
    await loadMemberGrants(member.membership_id);
  };

  // Toggle effect ALLOW <-> DENY
  const handleToggleEffect = async (grant: PermissionGrant) => {
    const newEffect = grant.effect === 'ALLOW' ? 'DENY' : 'ALLOW';
    setSavingId(grant.id);
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      const updated = await updatePermissionApi(grant.id, { effect: newEffect });
      setPermissions((prev) =>
        prev.map((g) => (g.id === grant.id ? { ...g, effect: updated.effect } : g))
      );
      setSuccessMessage(`Updated ${grant.resource}/${grant.action} to ${newEffect}`);
    } catch (err: unknown) {
      const msg = err && typeof err === 'object' && 'message' in err ? String(err.message) : 'Permission update rejected';
      setErrorMessage(msg);
    } finally {
      setSavingId(null);
    }
  };

  // Toggle approval_required
  const handleToggleApproval = async (grant: PermissionGrant) => {
    const newReq = !grant.approval_required;
    setSavingId(grant.id);
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      const updated = await updatePermissionApi(grant.id, { approval_required: newReq });
      setPermissions((prev) =>
        prev.map((g) => (g.id === grant.id ? { ...g, approval_required: updated.approval_required } : g))
      );
      setSuccessMessage(`Updated approval requirement for ${grant.resource}/${grant.action}`);
    } catch (err: unknown) {
      const msg = err && typeof err === 'object' && 'message' in err ? String(err.message) : 'Update rejected';
      setErrorMessage(msg);
    } finally {
      setSavingId(null);
    }
  };

  // Decide approval request
  const handleApprove = async (approvalId: string) => {
    setLoading(true);
    try {
      await approveRequestApi(approvalId, 'Approved via FGP screen');
      setPendingApprovals((prev) => prev.filter((a) => a.id !== approvalId));
      setSuccessMessage('Action approved successfully!');
    } catch (err: unknown) {
      const msg = err && typeof err === 'object' && 'message' in err ? String(err.message) : 'Approval decision failed';
      setErrorMessage(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleDeny = async (approvalId: string) => {
    setLoading(true);
    try {
      await denyRequestApi(approvalId, 'Denied via FGP screen');
      setPendingApprovals((prev) => prev.filter((a) => a.id !== approvalId));
      setSuccessMessage('Action denied.');
    } catch (err: unknown) {
      const msg = err && typeof err === 'object' && 'message' in err ? String(err.message) : 'Denial failed';
      setErrorMessage(msg);
    } finally {
      setLoading(false);
    }
  };

  if (!isAdmin) {
    return (
      <View style={styles.container}>
        <Header onToggleMenu={() => setDrawerOpen(true)} title="GOVERNANCE" />
        <View style={styles.restrictedContainer}>
          <Text style={styles.restrictedIcon}>🔒</Text>
          <Text style={styles.restrictedTitle}>Access Restricted</Text>
          <Text style={styles.restrictedText}>
            Only authorized Family Administrators can access the Family Governance Platform (FGP).
          </Text>
        </View>
        <SidebarDrawer
          visible={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          activeRoute="governance"
        />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <Header onToggleMenu={() => setDrawerOpen(true)} title="FAMILY GOVERNANCE" />

      <ScrollView contentContainerStyle={styles.scrollContent}>
        <ErrorBanner error={errorMessage} onDismiss={() => setErrorMessage(null)} />

        {successMessage ? (
          <View style={styles.successBanner}>
            <Text style={styles.successText}>✓ {successMessage}</Text>
          </View>
        ) : null}

        {/* Pending Approvals Section */}
        {pendingApprovals.length > 0 ? (
          <View style={styles.approvalsSection}>
            <Text style={styles.sectionTitle}>
              ⚠️ Pending Approvals ({pendingApprovals.length})
            </Text>
            {pendingApprovals.map((appr) => {
              const payload = appr.request_payload_json || {};
              return (
                <View key={appr.id} style={styles.approvalCard}>
                  <Text style={styles.approvalType}>{appr.approval_type}</Text>
                  <Text style={styles.approvalDetail}>
                    Item: {String(payload.title || 'Product Purchase')}
                  </Text>
                  {payload.price_amount ? (
                    <Text style={styles.approvalPrice}>
                      Amount: {String(payload.currency || 'INR')} {String(payload.price_amount)}
                    </Text>
                  ) : null}

                  <View style={styles.approvalActions}>
                    <TouchableOpacity
                      style={styles.approveBtn}
                      onPress={() => handleApprove(appr.id)}
                    >
                      <Text style={styles.approveBtnText}>Approve</Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                      style={styles.denyBtn}
                      onPress={() => handleDeny(appr.id)}
                    >
                      <Text style={styles.denyBtnText}>Deny</Text>
                    </TouchableOpacity>
                  </View>
                </View>
              );
            })}
          </View>
        ) : null}

        {/* Member Selector */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Family Members</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.memberList}>
            {members.map((mem) => {
              const isSelected = selectedMember?.membership_id === mem.membership_id;
              const isSelf = mem.membership_id === user?.membership_id;
              return (
                <TouchableOpacity
                  key={mem.membership_id}
                  style={[styles.memberPill, isSelected && styles.memberPillActive]}
                  onPress={() => handleSelectMember(mem)}
                >
                  <Text
                    style={[styles.memberName, isSelected && styles.memberNameActive]}
                  >
                    {mem.display_name} {isSelf ? '(You)' : ''}
                  </Text>
                  <Text
                    style={[styles.memberRole, isSelected && styles.memberRoleActive]}
                  >
                    {mem.family_role}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </ScrollView>
        </View>

        {/* Member Permissions View & Edit */}
        {selectedMember ? (
          <View style={styles.section}>
            <View style={styles.memberHeaderRow}>
              <View>
                <Text style={styles.selectedTitle}>{selectedMember.display_name}</Text>
                <Text style={styles.selectedSub}>
                  Role: {selectedMember.family_role} • Status: {selectedMember.membership_status}
                </Text>
              </View>
              {loading ? <ActivityIndicator size="small" color="#3b82f6" /> : null}
            </View>

            <Text style={styles.grantsTitle}>Assigned Permissions & Gating</Text>

            {permissions.length === 0 ? (
              <Text style={styles.emptyGrants}>No explicit grants found for this member.</Text>
            ) : (
              permissions.map((grant) => {
                const isAllow = grant.effect === 'ALLOW';
                const isSaving = savingId === grant.id;

                return (
                  <View key={grant.id} style={styles.grantCard}>
                    <View style={styles.grantInfo}>
                      <Text style={styles.grantResource}>{grant.resource}</Text>
                      <Text style={styles.grantAction}>action: {grant.action}</Text>
                    </View>

                    <View style={styles.grantControls}>
                      {/* Effect Toggle ALLOW / DENY */}
                      <View style={styles.controlItem}>
                        <Text style={[styles.effectLabel, isAllow ? styles.allowText : styles.denyText]}>
                          {grant.effect}
                        </Text>
                        <Switch
                          value={isAllow}
                          onValueChange={() => handleToggleEffect(grant)}
                          trackColor={{ false: '#fca5a5', true: '#86efac' }}
                          thumbColor={isAllow ? '#16a34a' : '#dc2626'}
                          disabled={isSaving}
                        />
                      </View>

                      {/* Approval Required Toggle */}
                      {isAllow ? (
                        <View style={styles.controlItem}>
                          <Text style={styles.approvalLabel}>
                            {grant.approval_required ? 'Approval Req.' : 'Pre-approved'}
                          </Text>
                          <Switch
                            value={grant.approval_required}
                            onValueChange={() => handleToggleApproval(grant)}
                            trackColor={{ false: '#e2e8f0', true: '#fcd34d' }}
                            thumbColor={grant.approval_required ? '#d97706' : '#94a3b8'}
                            disabled={isSaving}
                          />
                        </View>
                      ) : null}
                    </View>
                  </View>
                );
              })
            )}
          </View>
        ) : null}
      </ScrollView>

      <SidebarDrawer
        visible={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        activeRoute="governance"
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f8fafc',
  },
  scrollContent: {
    padding: 16,
    paddingBottom: 40,
  },
  restrictedContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 32,
  },
  restrictedIcon: {
    fontSize: 48,
    marginBottom: 16,
  },
  restrictedTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#0f172a',
    marginBottom: 8,
  },
  restrictedText: {
    fontSize: 14,
    color: '#64748b',
    textAlign: 'center',
    lineHeight: 20,
  },
  section: {
    backgroundColor: '#ffffff',
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: '#e2e8f0',
  },
  sectionTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: '#475569',
    textTransform: 'uppercase',
    letterSpacing: 1,
    marginBottom: 12,
  },
  memberList: {
    flexDirection: 'row',
  },
  memberPill: {
    backgroundColor: '#f1f5f9',
    paddingVertical: 10,
    paddingHorizontal: 14,
    borderRadius: 8,
    marginRight: 10,
    borderWidth: 1,
    borderColor: '#cbd5e1',
  },
  memberPillActive: {
    backgroundColor: '#3b82f6',
    borderColor: '#3b82f6',
  },
  memberName: {
    fontSize: 14,
    fontWeight: '600',
    color: '#1e293b',
  },
  memberNameActive: {
    color: '#ffffff',
  },
  memberRole: {
    fontSize: 11,
    color: '#64748b',
    marginTop: 2,
  },
  memberRoleActive: {
    color: '#dbeafe',
  },
  memberHeaderRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  selectedTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: '#0f172a',
  },
  selectedSub: {
    fontSize: 12,
    color: '#64748b',
    marginTop: 2,
  },
  grantsTitle: {
    fontSize: 13,
    fontWeight: '600',
    color: '#475569',
    marginBottom: 10,
    borderTopWidth: 1,
    borderTopColor: '#f1f5f9',
    paddingTop: 10,
  },
  emptyGrants: {
    fontSize: 13,
    color: '#94a3b8',
    fontStyle: 'italic',
  },
  grantCard: {
    backgroundColor: '#f8fafc',
    borderRadius: 8,
    padding: 12,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: '#e2e8f0',
  },
  grantInfo: {
    marginBottom: 8,
  },
  grantResource: {
    fontSize: 14,
    fontWeight: '700',
    color: '#0f172a',
  },
  grantAction: {
    fontSize: 12,
    color: '#64748b',
  },
  grantControls: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderTopWidth: 1,
    borderTopColor: '#f1f5f9',
    paddingTop: 8,
  },
  controlItem: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  effectLabel: {
    fontSize: 12,
    fontWeight: '700',
    marginRight: 6,
  },
  allowText: {
    color: '#16a34a',
  },
  denyText: {
    color: '#dc2626',
  },
  approvalLabel: {
    fontSize: 11,
    color: '#64748b',
    marginRight: 6,
  },
  approvalsSection: {
    backgroundColor: '#fffbeb',
    borderColor: '#f59e0b',
    borderWidth: 1,
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
  },
  approvalCard: {
    backgroundColor: '#ffffff',
    borderRadius: 8,
    padding: 12,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: '#fcd34d',
  },
  approvalType: {
    fontSize: 12,
    fontWeight: '700',
    color: '#b45309',
    textTransform: 'uppercase',
  },
  approvalDetail: {
    fontSize: 14,
    color: '#1e293b',
    marginTop: 2,
    fontWeight: '600',
  },
  approvalPrice: {
    fontSize: 13,
    color: '#0f172a',
    marginTop: 2,
  },
  approvalActions: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 10,
  },
  approveBtn: {
    backgroundColor: '#10b981',
    paddingVertical: 6,
    paddingHorizontal: 14,
    borderRadius: 6,
  },
  approveBtnText: {
    color: '#ffffff',
    fontSize: 12,
    fontWeight: '700',
  },
  denyBtn: {
    backgroundColor: '#ef4444',
    paddingVertical: 6,
    paddingHorizontal: 14,
    borderRadius: 6,
  },
  denyBtnText: {
    color: '#ffffff',
    fontSize: 12,
    fontWeight: '700',
  },
  successBanner: {
    backgroundColor: '#d1fae5',
    borderColor: '#10b981',
    borderWidth: 1,
    borderRadius: 8,
    padding: 10,
    marginBottom: 12,
  },
  successText: {
    color: '#065f46',
    fontSize: 13,
    fontWeight: '600',
  },
});
