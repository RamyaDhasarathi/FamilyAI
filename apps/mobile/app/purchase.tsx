import React, { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  Keyboard,
  KeyboardAvoidingView,
  Modal,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { useRouter } from 'expo-router';
import {
  executeInstructionApi,
  getPurchaseTasks,
  getTaskCandidates,
  prepareExecutionApi,
  selectCandidateApi,
  sendChatMessage,
} from '../src/api/purchase';
import apiClient from '../src/api/client';
import { DevDataBanner } from '../src/components/DevDataBanner';
import { ErrorBanner } from '../src/components/ErrorBanner';
import { Header } from '../src/components/Header';
import { MessageBubble } from '../src/components/MessageBubble';
import { ProductCard } from '../src/components/ProductCard';
import { SessionsModal } from '../src/components/SessionsModal';
import { SidebarDrawer } from '../src/components/SidebarDrawer';
import { useVoice } from '../src/hooks/useVoice';
import { Message, ProductCandidate, PurchaseTask } from '../src/types';

export default function PurchaseScreen() {
  const router = useRouter();
  const [drawerOpen, setDrawerOpen] = useState(false);

  // Conversation & Task state
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      sender_type: 'AGENT',
      content:
        "Hello! I'm your Family OS Purchase Agent. Tell me what you're looking to purchase or research (e.g. 'Find a wireless mouse under ₹1,500').",
      content_type: 'TEXT',
      created_at: new Date().toISOString(),
    },
  ]);

  const [inputQuery, setInputQuery] = useState('');
  const [conversationId, setConversationId] = useState<string | undefined>(undefined);
  const [taskId, setTaskId] = useState<string | undefined>(undefined);
  const [taskStatus, setTaskStatus] = useState<string | undefined>(undefined);
  const [candidates, setCandidates] = useState<ProductCandidate[]>([]);
  const [selectedProductId, setSelectedProductId] = useState<string | null>(null);
  const [isDevData, setIsDevData] = useState(true);

  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [actionSuccessMessage, setActionSuccessMessage] = useState<string | null>(null);

  // Chat Sessions history modal state
  const [sessionsModalVisible, setSessionsModalVisible] = useState(false);
  const [recentTasks, setRecentTasks] = useState<PurchaseTask[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(false);

  // Credit Card Payment Modal State
  const [paymentModalVisible, setPaymentModalVisible] = useState(false);
  const [pendingProduct, setPendingProduct] = useState<ProductCandidate | null>(null);
  const [selectedCardId, setSelectedCardId] = useState<string>('card_hdfc');
  const [customLast4, setCustomLast4] = useState<string>('');
  const [cvv, setCvv] = useState<string>('');

  const savedCreditCards = [
    { id: 'card_hdfc', name: 'HDFC Bank Regalia Credit Card', last4: '4242', brand: 'Visa' },
    { id: 'card_icici', name: 'ICICI Bank Sapphiro Credit Card', last4: '8891', brand: 'Mastercard' },
    { id: 'card_sbi', name: 'SBI Card Elite', last4: '1024', brand: 'Visa' },
    { id: 'card_custom', name: 'Use Another Credit Card', last4: '', brand: 'Custom' },
  ];

  // Voice recording hook
  const {
    isRecording,
    isTranscribing,
    transcriptionText,
    errorMessage: voiceError,
    startRecording,
    stopRecording,
    clearTranscription,
  } = useVoice();

  const flatListRef = useRef<FlatList>(null);

  useEffect(() => {
    loadActiveState();
  }, []);

  const loadActiveState = async () => {
    try {
      const tasks = await getPurchaseTasks();
      if (tasks && tasks.length > 0) {
        setRecentTasks(tasks);
        const latest = tasks[0];
        // Only auto-restore active in-progress tasks (not already COMPLETED or CANCELLED)
        if (latest.status !== 'COMPLETED' && latest.status !== 'CANCELLED') {
          setTaskId(latest.id);
          setTaskStatus(latest.status);
          if (latest.selected_product_id) {
            setSelectedProductId(latest.selected_product_id);
          }
          if (latest.conversation_id) {
            setConversationId(latest.conversation_id);
            try {
              const msgsRes = await apiClient.get<Message[]>(
                `/api/v1/conversations/${latest.conversation_id}/messages`
              );
              if (msgsRes.data && msgsRes.data.length > 0) {
                setMessages(msgsRes.data);
              }
            } catch {}
          }
          if (
            latest.status === 'RECOMMENDATION_READY' ||
            latest.status === 'OPTION_SELECTED'
          ) {
            const cands = await getTaskCandidates(latest.id);
            if (cands && cands.length > 0) {
              setCandidates(cands);
              setIsDevData(cands[0].source_type === 'DEVELOPMENT_CATALOGUE');
            }
          }
        }
      }
    } catch (err) {
      console.warn('Failed to load active task state:', err);
    }
  };

  // Start a fresh, clean chat session
  const handleNewChat = () => {
    Keyboard.dismiss();
    setConversationId(undefined);
    setTaskId(undefined);
    setTaskStatus(undefined);
    setCandidates([]);
    setSelectedProductId(null);
    setInputQuery('');
    setErrorMessage(null);
    setActionSuccessMessage(null);
    setPendingProduct(null);
    setMessages([
      {
        id: 'welcome',
        sender_type: 'AGENT',
        content:
          "Hello! I'm your Family OS Purchase Agent. Tell me what you're looking to purchase or research (e.g. 'Find a wireless mouse under ₹1,500').",
        content_type: 'TEXT',
        created_at: new Date().toISOString(),
      },
    ]);
    setSessionsModalVisible(false);
  };

  // Switch to a previous chat session
  const handleSwitchSession = async (task: PurchaseTask) => {
    Keyboard.dismiss();
    setLoading(true);
    setErrorMessage(null);
    setActionSuccessMessage(null);
    setPendingProduct(null);
    try {
      setTaskId(task.id);
      setTaskStatus(task.status);
      setSelectedProductId(task.selected_product_id || null);
      setConversationId(task.conversation_id);

      if (task.conversation_id) {
        try {
          const msgsRes = await apiClient.get<Message[]>(
            `/api/v1/conversations/${task.conversation_id}/messages`
          );
          if (msgsRes.data && msgsRes.data.length > 0) {
            setMessages(msgsRes.data);
          } else {
            setMessages([
              {
                id: 'init_task',
                sender_type: 'USER',
                content: task.original_request,
                content_type: 'TEXT',
                created_at: task.created_at,
              },
            ]);
          }
        } catch {
          setMessages([
            {
              id: 'init_task',
              sender_type: 'USER',
              content: task.original_request,
              content_type: 'TEXT',
              created_at: task.created_at,
            },
          ]);
        }
      } else {
        setMessages([
          {
            id: 'init_task',
            sender_type: 'USER',
            content: task.original_request,
            content_type: 'TEXT',
            created_at: task.created_at,
          },
        ]);
      }

      const cands = await getTaskCandidates(task.id);
      setCandidates(cands || []);
      if (cands && cands.length > 0) {
        setIsDevData(cands[0].source_type === 'DEVELOPMENT_CATALOGUE');
      }
    } catch (err: unknown) {
      const msg =
        err && typeof err === 'object' && 'message' in err
          ? String(err.message)
          : 'Failed to switch session';
      setErrorMessage(msg);
    } finally {
      setLoading(false);
    }
  };

  // Open Sessions Modal and refresh task list
  const handleOpenSessions = async () => {
    setSessionsModalVisible(true);
    setLoadingSessions(true);
    try {
      const tasks = await getPurchaseTasks();
      if (tasks) {
        setRecentTasks(tasks);
      }
    } catch (err) {
      console.warn('Failed to refresh sessions:', err);
    } finally {
      setLoadingSessions(false);
    }
  };

  // Send typed or voice message
  const handleSendMessage = async (textToSend?: string) => {
    const query = (textToSend || inputQuery).trim();
    if (!query) return;

    setInputQuery('');
    clearTranscription();
    setErrorMessage(null);
    setActionSuccessMessage(null);

    // Append user message immediately to UI
    const userMsg: Message = {
      id: `usr_${Date.now()}`,
      sender_type: 'USER',
      content: query,
      content_type: 'TEXT',
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    try {
      const resp = await sendChatMessage('PURCHASE', {
        conversation_id: conversationId,
        message: query,
        task_id: taskId,
      });

      setConversationId(resp.conversation_id);
      if (resp.task_id) setTaskId(resp.task_id);
      if (resp.task_status) setTaskStatus(resp.task_status);
      if (resp.candidates && resp.candidates.length > 0) {
        setCandidates(resp.candidates);
      }
      setIsDevData(resp.is_development_data);

      // Append agent message
      const agentMsg: Message = {
        id: resp.message_id || `agt_${Date.now()}`,
        sender_type: 'AGENT',
        content: resp.reply,
        content_type: resp.candidates && resp.candidates.length > 0 ? 'STRUCTURED' : 'TEXT',
        metadata_json: resp.structured_response,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, agentMsg]);
      getPurchaseTasks().then((t) => t && setRecentTasks(t)).catch(() => {});
    } catch (err: unknown) {
      const msg =
        err && typeof err === 'object' && 'message' in err
          ? String(err.message)
          : 'Failed to contact Purchase Agent.';
      setErrorMessage(msg);
    } finally {
      setLoading(false);
    }
  };

  // Voice record button toggle
  const handleMicPress = async () => {
    if (isRecording) {
      const transcribed = await stopRecording();
      if (transcribed) {
        setInputQuery(transcribed);
      }
    } else {
      await startRecording();
    }
  };

  // Select a product candidate
  const handleSelectProduct = async (product: ProductCandidate) => {
    Keyboard.dismiss();
    let currentTaskId = taskId;
    if (!currentTaskId) {
      try {
        const tasks = await getPurchaseTasks();
        if (tasks && tasks.length > 0) {
          currentTaskId = tasks[0].id;
          setTaskId(currentTaskId);
        }
      } catch (e) {}
    }
    if (!currentTaskId) return;

    setLoading(true);
    setErrorMessage(null);
    try {
      await selectCandidateApi(currentTaskId, product.id);
      setSelectedProductId(product.id);
      setActionSuccessMessage(`Selected '${product.title}'. Tap 'Proceed to Checkout'.`);
    } catch (err: unknown) {
      const msg = err && typeof err === 'object' && 'message' in err ? String(err.message) : 'Selection failed';
      setErrorMessage(msg);
    } finally {
      setLoading(false);
    }
  };

  // Proceed directly to live checkout via Mobile-Use Agent
  const [isCheckingOut, setIsCheckingOut] = useState(false);

  const handlePrepareExecution = (product?: ProductCandidate) => {
    Keyboard.dismiss();
    if (product) {
      setPendingProduct(product);
    }
    setPaymentModalVisible(true);
  };

  const handleExecuteWithPayment = async () => {
    setPaymentModalVisible(false);
    Keyboard.dismiss();
    let currentTaskId = taskId;
    if (!currentTaskId) {
      try {
        const tasks = await getPurchaseTasks();
        if (tasks && tasks.length > 0) {
          currentTaskId = tasks[0].id;
          setTaskId(currentTaskId);
        }
      } catch (e) {}
    }
    if (!currentTaskId) {
      setErrorMessage('No active purchase task found.');
      return;
    }

    const selectedCard = savedCreditCards.find((c) => c.id === selectedCardId);
    const activeLast4 = selectedCardId === 'card_custom' ? customLast4.trim() : (selectedCard?.last4 || '');
    const activeNickname = selectedCard?.name || 'Credit Card';

    setIsCheckingOut(true);
    setLoading(true);
    setErrorMessage(null);
    setActionSuccessMessage(
      `🚀 Agent starting autonomous payment with ${activeNickname} (ending in ${activeLast4 || 'card'})...`
    );

    try {
      const prodToSelect = pendingProduct;
      if (prodToSelect && prodToSelect.id !== selectedProductId) {
        await selectCandidateApi(currentTaskId, prodToSelect.id);
        setSelectedProductId(prodToSelect.id);
      }

      // Prepare execution with Credit Card details
      const prep = await prepareExecutionApi(currentTaskId, {
        payment_mode: 'CREDIT_CARD',
        card_last4: activeLast4,
        card_nickname: activeNickname,
        cvv: cvv.trim(),
      });

      if (prep.approval_required) {
        setActionSuccessMessage('Administrator approval is required before checkout.');
        router.push(`/task/${currentTaskId}`);
        return;
      }

      // Execute live on device immediately!
      setActionSuccessMessage('💳 Navigating Amazon checkout, entering CVV & awaiting bank OTP...');
      const execResult = await executeInstructionApi(prep.instruction_id);
      setTaskStatus('COMPLETED');
      setActionSuccessMessage(
        execResult.message || '✓ Autonomous Credit Card payment completed! OTP verified and order placed.'
      );
    } catch (err: unknown) {
      const msg = err && typeof err === 'object' && 'message' in err ? String(err.message) : 'Checkout initiation failed';
      setErrorMessage(msg);
    } finally {
      setIsCheckingOut(false);
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <Header
        onToggleMenu={() => setDrawerOpen(true)}
        title="PURCHASE AGENT"
        showChatActions={true}
        onNewChat={handleNewChat}
        onOpenSessions={handleOpenSessions}
      />

      {/* Task Status Pill & Navigation Link */}
      {taskId ? (
        <View style={styles.taskBar}>
          <View style={styles.taskStatusContainer}>
            <Text style={styles.taskStatusLabel}>Task:</Text>
            <View style={styles.statusPill}>
              <Text style={styles.statusPillText}>{taskStatus || 'ACTIVE'}</Text>
            </View>
          </View>
          <View style={styles.taskBarActions}>
            <TouchableOpacity
              style={styles.taskDetailLink}
              onPress={() => router.push(`/task/${taskId}`)}
            >
              <Text style={styles.taskDetailLinkText}>Details ➔</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.taskNewBtn}
              onPress={handleNewChat}
            >
              <Text style={styles.taskNewBtnText}>＋ New Chat</Text>
            </TouchableOpacity>
          </View>
        </View>
      ) : null}

      {/* Banners */}
      {candidates.length > 0 && isDevData ? <DevDataBanner /> : null}
      <ErrorBanner error={errorMessage || voiceError} onDismiss={() => setErrorMessage(null)} />

      {actionSuccessMessage ? (
        <View style={styles.actionSuccessBanner}>
          <Text style={styles.actionSuccessText}>✓ {actionSuccessMessage}</Text>
        </View>
      ) : null}

      {/* Main Conversation Area */}
      <FlatList
        ref={flatListRef}
        data={messages}
        keyExtractor={(item) => item.id}
        renderItem={({ item }) => <MessageBubble message={item} />}
        contentContainerStyle={styles.listContent}
        onContentSizeChange={() => flatListRef.current?.scrollToEnd({ animated: true })}
        ListFooterComponent={
          <>
            {/* Show Candidate Product Cards */}
            {candidates.length > 0 ? (
              <View style={styles.candidatesSection}>
                <Text style={styles.candidatesSectionTitle}>
                  Candidate Products ({candidates.length})
                </Text>
                {candidates.map((cand) => (
                  <ProductCard
                    key={cand.id}
                    product={cand}
                    isSelected={selectedProductId === cand.id}
                    isCheckingOut={isCheckingOut}
                    onSelect={handleSelectProduct}
                    onPrepareExecution={handlePrepareExecution}
                  />
                ))}
              </View>
            ) : null}

            {loading ? (
              <View style={styles.loadingBubble}>
                <ActivityIndicator size="small" color="#3b82f6" />
                <Text style={styles.loadingText}>Purchase Agent is thinking...</Text>
              </View>
            ) : null}
          </>
        }
      />

      {/* Voice Transcription Preview / Confirm */}
      {transcriptionText ? (
        <View style={styles.voicePreview}>
          <Text style={styles.voicePreviewTitle}>Voice Transcript Review:</Text>
          <Text style={styles.voicePreviewText}>"{transcriptionText}"</Text>
          <View style={styles.voicePreviewActions}>
            <TouchableOpacity
              style={styles.voiceConfirmBtn}
              onPress={() => handleSendMessage(transcriptionText)}
            >
              <Text style={styles.voiceConfirmBtnText}>Send Transcript</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.voiceCancelBtn} onPress={clearTranscription}>
              <Text style={styles.voiceCancelBtnText}>Discard</Text>
            </TouchableOpacity>
          </View>
        </View>
      ) : null}

      {/* Recording Status Bar */}
      {isRecording ? (
        <View style={styles.recordingBar}>
          <View style={styles.recordingDot} />
          <Text style={styles.recordingText}>Listening... Tap mic again to stop</Text>
        </View>
      ) : null}

      {isTranscribing ? (
        <View style={styles.recordingBar}>
          <ActivityIndicator size="small" color="#ef4444" />
          <Text style={styles.recordingText}>Transcribing audio via backend...</Text>
        </View>
      ) : null}

      {/* Bottom Composer */}
      <View style={styles.composerContainer}>
        <TextInput
          style={styles.composerInput}
          value={inputQuery}
          onChangeText={setInputQuery}
          placeholder="Ask Purchase Agent (e.g. wireless mouse under ₹1,500)..."
          placeholderTextColor="#94a3b8"
          multiline
        />

        {/* Microphone Button */}
        <TouchableOpacity
          style={[styles.iconButton, isRecording && styles.micActiveButton]}
          onPress={handleMicPress}
          disabled={loading || isTranscribing}
        >
          <Text style={styles.micIcon}>{isRecording ? '⏹️' : '🎙️'}</Text>
        </TouchableOpacity>

        {/* Send Button */}
        <TouchableOpacity
          style={[styles.sendButton, (!inputQuery.trim() || loading) && styles.sendDisabled]}
          onPress={() => handleSendMessage()}
          disabled={!inputQuery.trim() || loading}
        >
          <Text style={styles.sendButtonText}>➔</Text>
        </TouchableOpacity>
      </View>

      {/* Credit Card Payment Modal */}
      <Modal
        visible={paymentModalVisible}
        transparent
        animationType="fade"
        onRequestClose={() => setPaymentModalVisible(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>💳 Credit Card Payment</Text>
              <TouchableOpacity onPress={() => setPaymentModalVisible(false)} style={styles.modalCloseBtn}>
                <Text style={styles.modalCloseBtnText}>✕</Text>
              </TouchableOpacity>
            </View>

            <Text style={styles.modalSubtitle}>
              Select your credit card. The autonomous agent will select the card on Amazon, enter CVV, intercept the bank OTP from your phone SMS/notifications, and finish the transaction.
            </Text>

            {pendingProduct ? (
              <View style={styles.modalProductSummary}>
                <Text style={styles.modalProductTitle} numberOfLines={1}>{pendingProduct.title}</Text>
                <Text style={styles.modalProductPrice}>
                  Total: {pendingProduct.currency || 'INR'} {pendingProduct.price_amount?.toLocaleString() || 'N/A'}
                </Text>
              </View>
            ) : null}

            <Text style={styles.modalSectionLabel}>Select Credit Card:</Text>
            <View style={styles.cardsContainer}>
              {savedCreditCards.map((card) => {
                const isSelected = selectedCardId === card.id;
                return (
                  <TouchableOpacity
                    key={card.id}
                    style={[styles.cardOption, isSelected && styles.cardOptionSelected]}
                    onPress={() => setSelectedCardId(card.id)}
                  >
                    <View style={styles.radioOuter}>
                      {isSelected ? <View style={styles.radioInner} /> : null}
                    </View>
                    <View style={styles.cardInfo}>
                      <Text style={[styles.cardName, isSelected && styles.cardNameSelected]}>
                        {card.name}
                      </Text>
                      {card.last4 ? (
                        <Text style={styles.cardLast4}>
                          {card.brand} •••• {card.last4}
                        </Text>
                      ) : null}
                    </View>
                  </TouchableOpacity>
                );
              })}
            </View>

            {selectedCardId === 'card_custom' ? (
              <View style={styles.customCardInputRow}>
                <Text style={styles.inputFieldLabel}>Card Last 4 Digits:</Text>
                <TextInput
                  style={styles.customCardInput}
                  value={customLast4}
                  onChangeText={setCustomLast4}
                  placeholder="e.g. 1234"
                  keyboardType="numeric"
                  maxLength={4}
                  placeholderTextColor="#94a3b8"
                />
              </View>
            ) : null}

            <View style={styles.cvvInputRow}>
              <View style={styles.cvvLabelContainer}>
                <Text style={styles.inputFieldLabel}>Security Code (CVV):</Text>
                <Text style={styles.cvvHint}>3 digits on back of card</Text>
              </View>
              <TextInput
                style={styles.cvvInput}
                value={cvv}
                onChangeText={setCvv}
                placeholder="123"
                keyboardType="numeric"
                secureTextEntry
                maxLength={4}
                placeholderTextColor="#94a3b8"
              />
            </View>

            <View style={styles.governanceNotice}>
              <Text style={styles.governanceNoticeText}>
                🔒 Full Autonomous Flow: The agent reads the bank OTP via local ADB and approves the 3DS gateway automatically.
              </Text>
            </View>

            <TouchableOpacity
              style={styles.payConfirmButton}
              onPress={handleExecuteWithPayment}
            >
              <Text style={styles.payConfirmButtonText}>🚀 Pay with Card & Complete Checkout</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.modalCancelButton}
              onPress={() => setPaymentModalVisible(false)}
            >
              <Text style={styles.modalCancelButtonText}>Cancel</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>

      {/* Left Sidebar Drawer */}
      <SidebarDrawer
        visible={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        activeRoute="purchase"
        onNewPurchaseSession={handleNewChat}
      />

      {/* Chat Sessions History Modal */}
      <SessionsModal
        visible={sessionsModalVisible}
        onClose={() => setSessionsModalVisible(false)}
        tasks={recentTasks}
        activeTaskId={taskId}
        onSelectTask={handleSwitchSession}
        onNewChat={handleNewChat}
        loading={loadingSessions}
      />
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f1f5f9',
  },
  taskBar: {
    backgroundColor: '#ffffff',
    paddingHorizontal: 16,
    paddingVertical: 8,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderBottomWidth: 1,
    borderBottomColor: '#e2e8f0',
  },
  taskStatusContainer: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  taskStatusLabel: {
    fontSize: 12,
    color: '#64748b',
    marginRight: 6,
  },
  statusPill: {
    backgroundColor: '#dbeafe',
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 12,
  },
  statusPillText: {
    fontSize: 11,
    color: '#1e40af',
    fontWeight: '700',
  },
  taskDetailLink: {
    paddingVertical: 4,
    paddingHorizontal: 8,
  },
  taskDetailLinkText: {
    fontSize: 12,
    color: '#3b82f6',
    fontWeight: '600',
  },
  taskBarActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  taskNewBtn: {
    backgroundColor: '#eff6ff',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: '#bfdbfe',
  },
  taskNewBtnText: {
    fontSize: 11,
    color: '#1d4ed8',
    fontWeight: '700',
  },
  actionSuccessBanner: {
    backgroundColor: '#d1fae5',
    borderColor: '#10b981',
    borderWidth: 1,
    borderRadius: 8,
    padding: 10,
    marginHorizontal: 12,
    marginVertical: 4,
  },
  actionSuccessText: {
    color: '#065f46',
    fontSize: 13,
    fontWeight: '600',
  },
  listContent: {
    paddingVertical: 12,
  },
  candidatesSection: {
    paddingHorizontal: 12,
    marginTop: 8,
  },
  candidatesSectionTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: '#334155',
    marginBottom: 6,
    textTransform: 'uppercase',
    letterSpacing: 1,
  },
  loadingBubble: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#ffffff',
    alignSelf: 'flex-start',
    marginLeft: 12,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 16,
    marginVertical: 6,
  },
  loadingText: {
    marginLeft: 8,
    fontSize: 13,
    color: '#64748b',
  },
  voicePreview: {
    backgroundColor: '#eff6ff',
    borderTopWidth: 1,
    borderColor: '#bfdbfe',
    padding: 12,
  },
  voicePreviewTitle: {
    fontSize: 11,
    color: '#3b82f6',
    fontWeight: '700',
    textTransform: 'uppercase',
  },
  voicePreviewText: {
    fontSize: 14,
    color: '#1e3a8a',
    marginVertical: 4,
    fontStyle: 'italic',
  },
  voicePreviewActions: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 6,
  },
  voiceConfirmBtn: {
    backgroundColor: '#3b82f6',
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: 6,
  },
  voiceConfirmBtnText: {
    color: '#ffffff',
    fontSize: 12,
    fontWeight: '600',
  },
  voiceCancelBtn: {
    paddingVertical: 6,
    paddingHorizontal: 10,
  },
  voiceCancelBtnText: {
    color: '#64748b',
    fontSize: 12,
  },
  recordingBar: {
    backgroundColor: '#fee2e2',
    paddingVertical: 8,
    paddingHorizontal: 16,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
  },
  recordingDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: '#ef4444',
    marginRight: 8,
  },
  recordingText: {
    color: '#991b1b',
    fontSize: 13,
    fontWeight: '600',
  },
  composerContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#ffffff',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderTopWidth: 1,
    borderTopColor: '#e2e8f0',
  },
  composerInput: {
    flex: 1,
    backgroundColor: '#f8fafc',
    borderWidth: 1,
    borderColor: '#cbd5e1',
    borderRadius: 20,
    paddingHorizontal: 14,
    paddingVertical: 8,
    fontSize: 14,
    maxHeight: 100,
    color: '#0f172a',
  },
  iconButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#f1f5f9',
    alignItems: 'center',
    justifyContent: 'center',
    marginLeft: 8,
  },
  micActiveButton: {
    backgroundColor: '#fee2e2',
  },
  micIcon: {
    fontSize: 18,
  },
  sendButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#3b82f6',
    alignItems: 'center',
    justifyContent: 'center',
    marginLeft: 8,
  },
  sendDisabled: {
    backgroundColor: '#94a3b8',
    opacity: 0.5,
  },
  sendButtonText: {
    color: '#ffffff',
    fontSize: 18,
    fontWeight: 'bold',
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  modalContent: {
    backgroundColor: '#ffffff',
    borderRadius: 16,
    padding: 20,
    width: '100%',
    maxWidth: 440,
    elevation: 8,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.15,
    shadowRadius: 10,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: '#0f172a',
  },
  modalCloseBtn: {
    padding: 4,
  },
  modalCloseBtnText: {
    fontSize: 18,
    color: '#64748b',
    fontWeight: 'bold',
  },
  modalSubtitle: {
    fontSize: 12,
    color: '#475569',
    lineHeight: 17,
    marginBottom: 10,
  },
  modalProductSummary: {
    backgroundColor: '#f1f5f9',
    borderRadius: 8,
    padding: 10,
    marginBottom: 10,
  },
  modalProductTitle: {
    fontSize: 13,
    fontWeight: '600',
    color: '#1e293b',
    marginBottom: 2,
  },
  modalProductPrice: {
    fontSize: 13,
    fontWeight: '700',
    color: '#059669',
  },
  modalSectionLabel: {
    fontSize: 11,
    fontWeight: '700',
    color: '#334155',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 6,
  },
  cardsContainer: {
    marginBottom: 10,
  },
  cardOption: {
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#e2e8f0',
    borderRadius: 8,
    padding: 8,
    marginBottom: 6,
    backgroundColor: '#ffffff',
  },
  cardOptionSelected: {
    borderColor: '#3b82f6',
    backgroundColor: '#eff6ff',
  },
  radioOuter: {
    width: 18,
    height: 18,
    borderRadius: 9,
    borderWidth: 2,
    borderColor: '#94a3b8',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 10,
  },
  radioInner: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: '#3b82f6',
  },
  cardInfo: {
    flex: 1,
  },
  cardName: {
    fontSize: 13,
    fontWeight: '600',
    color: '#334155',
  },
  cardNameSelected: {
    color: '#1d4ed8',
  },
  cardLast4: {
    fontSize: 11,
    color: '#64748b',
    marginTop: 1,
  },
  customCardInputRow: {
    marginBottom: 10,
  },
  inputFieldLabel: {
    fontSize: 12,
    fontWeight: '600',
    color: '#334155',
    marginBottom: 4,
  },
  customCardInput: {
    borderWidth: 1,
    borderColor: '#cbd5e1',
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 6,
    fontSize: 13,
    backgroundColor: '#f8fafc',
    color: '#0f172a',
  },
  cvvInputRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: '#f8fafc',
    borderRadius: 8,
    padding: 10,
    borderWidth: 1,
    borderColor: '#e2e8f0',
    marginBottom: 10,
  },
  cvvLabelContainer: {
    flex: 1,
  },
  cvvHint: {
    fontSize: 11,
    color: '#94a3b8',
  },
  cvvInput: {
    borderWidth: 1,
    borderColor: '#cbd5e1',
    borderRadius: 8,
    width: 70,
    paddingHorizontal: 10,
    paddingVertical: 6,
    fontSize: 14,
    textAlign: 'center',
    backgroundColor: '#ffffff',
    color: '#0f172a',
    fontWeight: 'bold',
  },
  governanceNotice: {
    backgroundColor: '#f0fdf4',
    borderRadius: 6,
    padding: 8,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: '#bbf7d0',
  },
  governanceNoticeText: {
    fontSize: 11,
    color: '#166534',
    lineHeight: 15,
  },
  payConfirmButton: {
    backgroundColor: '#2563eb',
    borderRadius: 10,
    paddingVertical: 12,
    alignItems: 'center',
    marginBottom: 8,
  },
  payConfirmButtonText: {
    color: '#ffffff',
    fontSize: 14,
    fontWeight: '700',
  },
  modalCancelButton: {
    paddingVertical: 4,
    alignItems: 'center',
  },
  modalCancelButtonText: {
    color: '#64748b',
    fontSize: 13,
    fontWeight: '600',
  },
});
