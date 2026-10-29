import React, { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import {
  executeInstructionApi,
  getPurchaseTask,
  getTaskCandidates,
  prepareExecutionApi,
} from '../../src/api/purchase';
import { DevDataBanner } from '../../src/components/DevDataBanner';
import { ErrorBanner } from '../../src/components/ErrorBanner';
import { Header } from '../../src/components/Header';
import { SidebarDrawer } from '../../src/components/SidebarDrawer';
import { ProductCandidate, PurchaseTask } from '../../src/types';

export default function TaskDetailScreen() {
  const router = useRouter();
  const { taskId } = useLocalSearchParams<{ taskId: string }>();

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [task, setTask] = useState<PurchaseTask | null>(null);
  const [candidates, setCandidates] = useState<ProductCandidate[]>([]);
  const [instructionId, setInstructionId] = useState<string | null>(null);

  const [loading, setLoading] = useState(true);
  const [executing, setExecuting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [simulationResult, setSimulationResult] = useState<any>(null);

  useEffect(() => {
    if (taskId) {
      loadTaskDetails();
    }
  }, [taskId]);

  const loadTaskDetails = async () => {
    if (!taskId) return;
    setLoading(true);
    setErrorMessage(null);
    try {
      const [taskData, cands] = await Promise.all([
        getPurchaseTask(taskId),
        getTaskCandidates(taskId),
      ]);
      setTask(taskData);
      setCandidates(cands);
    } catch (err: unknown) {
      const msg = err && typeof err === 'object' && 'message' in err ? String(err.message) : 'Failed to load task';
      setErrorMessage(msg);
    } finally {
      setLoading(false);
    }
  };

  const handlePrepare = async () => {
    if (!taskId) return;
    setExecuting(true);
    setErrorMessage(null);
    try {
      const prep = await prepareExecutionApi(taskId);
      setInstructionId(prep.instruction_id);
      await loadTaskDetails();
    } catch (err: unknown) {
      const msg = err && typeof err === 'object' && 'message' in err ? String(err.message) : 'Preparation failed';
      setErrorMessage(msg);
    } finally {
      setExecuting(false);
    }
  };

  const handleExecuteSimulation = async () => {
    if (!instructionId) {
      // Prepare first if needed
      if (!task) return;
      setExecuting(true);
      try {
        const prep = await prepareExecutionApi(task.id);
        const result = await executeInstructionApi(prep.instruction_id);
        setSimulationResult(result);
        await loadTaskDetails();
      } catch (err: unknown) {
        const msg = err && typeof err === 'object' && 'message' in err ? String(err.message) : 'Simulation failed';
        setErrorMessage(msg);
      } finally {
        setExecuting(false);
      }
      return;
    }

    setExecuting(true);
    setErrorMessage(null);
    try {
      const result = await executeInstructionApi(instructionId);
      setSimulationResult(result);
      await loadTaskDetails();
    } catch (err: unknown) {
      const msg = err && typeof err === 'object' && 'message' in err ? String(err.message) : 'Execution simulation failed';
      setErrorMessage(msg);
    } finally {
      setExecuting(false);
    }
  };

  return (
    <View style={styles.container}>
      <Header onToggleMenu={() => setDrawerOpen(true)} title="TASK LIFECYCLE" />

      <ScrollView contentContainerStyle={styles.scrollContent}>
        <TouchableOpacity
          style={styles.backRow}
          onPress={() => router.push('/purchase')}
        >
          <Text style={styles.backText}>← Back to Chat</Text>
        </TouchableOpacity>

        <ErrorBanner error={errorMessage} onDismiss={() => setErrorMessage(null)} />

        {loading ? (
          <ActivityIndicator size="large" color="#3b82f6" style={styles.loader} />
        ) : task ? (
          <>
            {/* Task Overview Card */}
            <View style={styles.card}>
              <View style={styles.rowBetween}>
                <Text style={styles.cardHeader}>Purchase Task</Text>
                <View style={styles.statusPill}>
                  <Text style={styles.statusPillText}>{task.status}</Text>
                </View>
              </View>

              <Text style={styles.requestId}>Task ID: {task.id}</Text>
              <Text style={styles.requestQuery}>"{task.original_request}"</Text>

              <View style={styles.metaGrid}>
                <View style={styles.metaItem}>
                  <Text style={styles.metaLabel}>Budget</Text>
                  <Text style={styles.metaValue}>
                    {task.budget_amount ? `${task.currency || 'INR'} ${task.budget_amount}` : 'None specified'}
                  </Text>
                </View>

                <View style={styles.metaItem}>
                  <Text style={styles.metaLabel}>Approval State</Text>
                  <Text style={[styles.metaValue, task.approval_state === 'APPROVED' ? styles.green : null]}>
                    {task.approval_state}
                  </Text>
                </View>

                <View style={styles.metaItem}>
                  <Text style={styles.metaLabel}>Execution State</Text>
                  <Text style={[styles.metaValue, task.execution_state === 'SUCCEEDED' ? styles.green : null]}>
                    {task.execution_state}
                  </Text>
                </View>
              </View>
            </View>

            {/* Simulation Completed Banner */}
            {simulationResult ? (
              <View style={styles.simulationBanner}>
                <Text style={styles.simBannerTitle}>✓ Mobile Use Execution Completed</Text>
                <Text style={styles.simBannerNotice}>
                  {simulationResult.message || 'Simulation completed — no real purchase was made.'}
                </Text>
                {simulationResult.engine ? (
                  <Text style={styles.simBannerEngine}>⚡ {simulationResult.engine}</Text>
                ) : null}
                <Text style={styles.simBannerDetail}>
                  Action: {simulationResult.action_type} • ID: {simulationResult.simulation_id || simulationResult.instruction_id}
                </Text>

                {/* Qwen Visual Grounding Trace */}
                {simulationResult.action_trace && simulationResult.action_trace.length > 0 ? (
                  <View style={styles.traceContainer}>
                    <Text style={styles.traceHeader}>🤖 Qwen Visual Grounding & Action Trace</Text>
                    {simulationResult.action_trace.map((step: any, idx: number) => (
                      <View key={idx} style={[styles.traceStep, step.safety_boundary_enforced ? styles.traceStepSafety : null]}>
                        <View style={[styles.stepNumBadge, step.safety_boundary_enforced ? styles.stepNumSafety : null]}>
                          <Text style={styles.stepNumText}>{step.step}</Text>
                        </View>
                        <View style={styles.stepContent}>
                          <Text style={styles.stepAction}>
                            {step.action}: <Text style={styles.stepElement}>{step.element}</Text>
                          </Text>
                          <Text style={styles.stepDetails}>{step.details}</Text>
                          {step.coordinates ? (
                            <Text style={styles.stepCoord}>
                              Screen Target: [{step.coordinates[0]}, {step.coordinates[1]}] px
                            </Text>
                          ) : null}
                          {step.safety_boundary_enforced ? (
                            <View style={styles.safetyTag}>
                              <Text style={styles.safetyTagText}>🛡️ Hard Payment Boundary Enforced</Text>
                            </View>
                          ) : null}
                        </View>
                      </View>
                    ))}
                  </View>
                ) : null}
              </View>
            ) : null}

            {/* Candidate Products Summary */}
            <View style={styles.card}>
              <Text style={styles.cardHeader}>Discovered Candidates ({candidates.length})</Text>
              {candidates.some((c) => c.source_type === 'DEVELOPMENT_CATALOGUE') ? (
                <DevDataBanner />
              ) : (
                <View style={styles.liveBanner}>
                  <Text style={styles.liveBannerText}>
                    ✓ Live Marketplace (Amazon India) — Gathered via Physical Device Mobile-Use Agent
                  </Text>
                </View>
              )}

              {candidates.map((cand) => (
                <View key={cand.id} style={styles.candRow}>
                  <View style={styles.candInfo}>
                    <Text style={styles.candTitle}>{cand.title}</Text>
                    <Text style={styles.candPrice}>
                      {cand.currency} {cand.price_amount} • {cand.brand || 'Generic'}
                    </Text>
                  </View>
                  <View style={styles.scorePill}>
                    <Text style={styles.scoreText}>Score: {cand.score || 'N/A'}</Text>
                  </View>
                </View>
              ))}
            </View>

            {/* Execution Simulation Action Section */}
            <View style={styles.card}>
              <Text style={styles.cardHeader}>Mobile Use Agent Autonomous Checkout</Text>
              <Text style={styles.execHelp}>
                The Purchase Agent tasks your Mobile-Use Agent to execute real actions on your phone:
                navigate Amazon India, select the candidate, tap Buy Now, confirm delivery address, and proceed directly to the payment screen.
              </Text>

              {task.status !== 'COMPLETED' ? (
                <TouchableOpacity
                  style={[styles.executeButton, executing && styles.disabledBtn]}
                  onPress={handleExecuteSimulation}
                  disabled={executing}
                >
                  {executing ? (
                    <ActivityIndicator color="#ffffff" />
                  ) : (
                    <Text style={styles.executeButtonText}>
                      Proceed to Live Checkout on Device 🛒
                    </Text>
                  )}
                </TouchableOpacity>
              ) : (
                <View style={styles.completedBadge}>
                  <Text style={styles.completedText}>✓ Live Checkout Reached: Complete Payment on Phone</Text>
                </View>
              )}
            </View>
          </>
        ) : null}
      </ScrollView>

      <SidebarDrawer
        visible={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f1f5f9',
  },
  scrollContent: {
    padding: 16,
    paddingBottom: 40,
  },
  backRow: {
    paddingVertical: 8,
    marginBottom: 8,
  },
  backText: {
    color: '#3b82f6',
    fontSize: 14,
    fontWeight: '600',
  },
  loader: {
    marginTop: 40,
  },
  card: {
    backgroundColor: '#ffffff',
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: '#e2e8f0',
  },
  rowBetween: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  cardHeader: {
    fontSize: 16,
    fontWeight: '700',
    color: '#0f172a',
  },
  statusPill: {
    backgroundColor: '#dbeafe',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 12,
  },
  statusPillText: {
    color: '#1e40af',
    fontSize: 11,
    fontWeight: '700',
  },
  requestId: {
    fontSize: 11,
    color: '#94a3b8',
    marginBottom: 6,
  },
  requestQuery: {
    fontSize: 15,
    fontStyle: 'italic',
    color: '#334155',
    marginBottom: 12,
  },
  metaGrid: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    borderTopWidth: 1,
    borderTopColor: '#f1f5f9',
    paddingTop: 10,
  },
  metaItem: {
    flex: 1,
  },
  metaLabel: {
    fontSize: 11,
    color: '#64748b',
    fontWeight: '600',
  },
  metaValue: {
    fontSize: 13,
    color: '#0f172a',
    marginTop: 2,
    fontWeight: '600',
  },
  green: {
    color: '#16a34a',
  },
  candRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#f1f5f9',
  },
  candInfo: {
    flex: 1,
    marginRight: 8,
  },
  candTitle: {
    fontSize: 13,
    fontWeight: '600',
    color: '#1e293b',
  },
  candPrice: {
    fontSize: 12,
    color: '#64748b',
    marginTop: 2,
  },
  scorePill: {
    backgroundColor: '#f1f5f9',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
  },
  scoreText: {
    fontSize: 11,
    color: '#475569',
    fontWeight: '600',
  },
  execHelp: {
    fontSize: 13,
    color: '#64748b',
    lineHeight: 18,
    marginVertical: 10,
  },
  executeButton: {
    backgroundColor: '#10b981',
    borderRadius: 8,
    paddingVertical: 14,
    alignItems: 'center',
    marginTop: 8,
  },
  disabledBtn: {
    opacity: 0.6,
  },
  executeButtonText: {
    color: '#ffffff',
    fontSize: 15,
    fontWeight: '700',
  },
  completedBadge: {
    backgroundColor: '#d1fae5',
    borderColor: '#10b981',
    borderWidth: 1,
    borderRadius: 8,
    padding: 12,
    alignItems: 'center',
    marginTop: 8,
  },
  completedText: {
    color: '#065f46',
    fontSize: 13,
    fontWeight: '700',
  },
  simulationBanner: {
    backgroundColor: '#ecfdf5',
    borderColor: '#059669',
    borderWidth: 1,
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
  },
  simBannerTitle: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#065f46',
    marginBottom: 4,
  },
  simBannerNotice: {
    fontSize: 14,
    color: '#047857',
    fontWeight: '600',
    marginBottom: 4,
  },
  simBannerDetail: {
    fontSize: 12,
    color: '#059669',
  },
  simBannerEngine: {
    fontSize: 13,
    color: '#1d4ed8',
    fontWeight: '700',
    marginBottom: 4,
  },
  traceContainer: {
    marginTop: 14,
    borderTopWidth: 1,
    borderTopColor: '#a7f3d0',
    paddingTop: 12,
  },
  traceHeader: {
    fontSize: 14,
    fontWeight: '700',
    color: '#0f172a',
    marginBottom: 8,
  },
  traceStep: {
    flexDirection: 'row',
    backgroundColor: '#ffffff',
    borderRadius: 8,
    padding: 10,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: '#e2e8f0',
  },
  traceStepSafety: {
    borderColor: '#f59e0b',
    backgroundColor: '#fffbeb',
  },
  stepNumBadge: {
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: '#3b82f6',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 10,
    marginTop: 2,
  },
  stepNumSafety: {
    backgroundColor: '#d97706',
  },
  stepNumText: {
    color: '#ffffff',
    fontSize: 12,
    fontWeight: '700',
  },
  stepContent: {
    flex: 1,
  },
  stepAction: {
    fontSize: 13,
    fontWeight: '700',
    color: '#1e293b',
  },
  stepElement: {
    fontWeight: '600',
    color: '#2563eb',
  },
  stepDetails: {
    fontSize: 12,
    color: '#475569',
    marginTop: 2,
    lineHeight: 16,
  },
  stepCoord: {
    fontSize: 11,
    color: '#64748b',
    fontFamily: 'monospace',
    marginTop: 3,
  },
  safetyTag: {
    alignSelf: 'flex-start',
    backgroundColor: '#fef3c7',
    borderColor: '#f59e0b',
    borderWidth: 1,
    borderRadius: 4,
    paddingHorizontal: 6,
    paddingVertical: 2,
    marginTop: 4,
  },
  safetyTagText: {
    fontSize: 11,
    color: '#b45309',
    fontWeight: '700',
  },
  liveBanner: {
    backgroundColor: '#ecfdf5',
    borderColor: '#10b981',
    borderWidth: 1,
    borderRadius: 8,
    padding: 10,
    marginBottom: 12,
  },
  liveBannerText: {
    color: '#065f46',
    fontSize: 12,
    fontWeight: '700',
  },
});

