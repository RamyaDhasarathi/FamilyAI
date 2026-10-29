import React from 'react';
import {
  ActivityIndicator,
  FlatList,
  Modal,
  StyleSheet,
  Text,
  TouchableOpacity,
  TouchableWithoutFeedback,
  View,
} from 'react-native';
import { PurchaseTask } from '../types';

interface SessionsModalProps {
  visible: boolean;
  onClose: () => void;
  tasks: PurchaseTask[];
  activeTaskId?: string;
  onSelectTask: (task: PurchaseTask) => void;
  onNewChat: () => void;
  loading?: boolean;
}

export const SessionsModal: React.FC<SessionsModalProps> = ({
  visible,
  onClose,
  tasks,
  activeTaskId,
  onSelectTask,
  onNewChat,
  loading = false,
}) => {
  const getStatusBadgeStyle = (status: string) => {
    switch (status) {
      case 'COMPLETED':
        return { bg: '#dcfce7', text: '#15803d', label: 'Completed' };
      case 'RECOMMENDATION_READY':
        return { bg: '#dbeafe', text: '#1d4ed8', label: 'Recommendations' };
      case 'OPTION_SELECTED':
        return { bg: '#f3e8ff', text: '#7e22ce', label: 'Option Selected' };
      case 'CANCELLED':
        return { bg: '#fee2e2', text: '#b91c1c', label: 'Cancelled' };
      default:
        return { bg: '#f1f5f9', text: '#475569', label: status };
    }
  };

  const formatDate = (isoString?: string) => {
    if (!isoString) return '';
    try {
      const d = new Date(isoString);
      return d.toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return isoString;
    }
  };

  return (
    <Modal
      visible={visible}
      transparent
      animationType="fade"
      onRequestClose={onClose}
    >
      <View style={styles.overlay}>
        <TouchableWithoutFeedback onPress={onClose}>
          <View style={styles.backdrop} />
        </TouchableWithoutFeedback>

        <View style={styles.content}>
          {/* Header */}
          <View style={styles.header}>
            <View>
              <Text style={styles.title}>💬 Chat Sessions</Text>
              <Text style={styles.subtitle}>
                Start a fresh request or resume previous chats
              </Text>
            </View>
            <TouchableOpacity onPress={onClose} style={styles.closeBtn}>
              <Text style={styles.closeBtnText}>✕</Text>
            </TouchableOpacity>
          </View>

          {/* New Chat Action Button */}
          <TouchableOpacity
            style={styles.newChatCard}
            onPress={() => {
              onClose();
              onNewChat();
            }}
          >
            <View style={styles.newChatIconBox}>
              <Text style={styles.newChatIcon}>＋</Text>
            </View>
            <View style={styles.newChatTextBox}>
              <Text style={styles.newChatTitle}>Start New Chat Session</Text>
              <Text style={styles.newChatSubtitle}>
                Ask for a new product, price comparison, or brand
              </Text>
            </View>
          </TouchableOpacity>

          <View style={styles.sectionDivider}>
            <Text style={styles.sectionHeader}>PREVIOUS SESSIONS</Text>
          </View>

          {loading ? (
            <View style={styles.loadingContainer}>
              <ActivityIndicator size="small" color="#2563eb" />
              <Text style={styles.loadingText}>Loading sessions...</Text>
            </View>
          ) : tasks.length === 0 ? (
            <View style={styles.emptyContainer}>
              <Text style={styles.emptyIcon}>🛍️</Text>
              <Text style={styles.emptyTitle}>No past sessions found</Text>
              <Text style={styles.emptySubtitle}>
                Tap 'Start New Chat Session' above to begin.
              </Text>
            </View>
          ) : (
            <FlatList
              data={tasks}
              keyExtractor={(item) => item.id}
              contentContainerStyle={styles.listContent}
              renderItem={({ item }) => {
                const isActive = item.id === activeTaskId;
                const badge = getStatusBadgeStyle(item.status);
                return (
                  <TouchableOpacity
                    style={[styles.taskItem, isActive && styles.taskItemActive]}
                    onPress={() => {
                      onClose();
                      onSelectTask(item);
                    }}
                  >
                    <View style={styles.taskItemHeader}>
                      <Text
                        style={[styles.taskRequest, isActive && styles.taskRequestActive]}
                        numberOfLines={2}
                      >
                        {item.original_request || 'Untitled Purchase Request'}
                      </Text>
                      {isActive ? (
                        <View style={styles.activeIndicator}>
                          <Text style={styles.activeIndicatorText}>Current</Text>
                        </View>
                      ) : null}
                    </View>

                    <View style={styles.taskItemFooter}>
                      <View
                        style={[styles.statusBadge, { backgroundColor: badge.bg }]}
                      >
                        <Text style={[styles.statusBadgeText, { color: badge.text }]}>
                          {badge.label}
                        </Text>
                      </View>
                      <Text style={styles.taskDate}>{formatDate(item.created_at)}</Text>
                    </View>
                  </TouchableOpacity>
                );
              }}
            />
          )}
        </View>
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.65)',
    justifyContent: 'flex-end',
  },
  backdrop: {
    ...StyleSheet.absoluteFillObject,
  },
  content: {
    backgroundColor: '#ffffff',
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    maxHeight: '85%',
    paddingHorizontal: 20,
    paddingTop: 18,
    paddingBottom: 28,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 16,
  },
  title: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#0f172a',
  },
  subtitle: {
    fontSize: 12,
    color: '#64748b',
    marginTop: 2,
  },
  closeBtn: {
    padding: 6,
    borderRadius: 16,
    backgroundColor: '#f1f5f9',
  },
  closeBtnText: {
    fontSize: 16,
    color: '#475569',
    fontWeight: 'bold',
  },
  newChatCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#eff6ff',
    borderWidth: 1.5,
    borderColor: '#93c5fd',
    borderRadius: 12,
    padding: 14,
    marginBottom: 16,
  },
  newChatIconBox: {
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: '#2563eb',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  newChatIcon: {
    color: '#ffffff',
    fontSize: 20,
    fontWeight: 'bold',
    lineHeight: 22,
  },
  newChatTextBox: {
    flex: 1,
  },
  newChatTitle: {
    fontSize: 15,
    fontWeight: '700',
    color: '#1e40af',
  },
  newChatSubtitle: {
    fontSize: 12,
    color: '#3b82f6',
    marginTop: 2,
  },
  sectionDivider: {
    borderBottomWidth: 1,
    borderBottomColor: '#e2e8f0',
    paddingBottom: 6,
    marginBottom: 10,
  },
  sectionHeader: {
    fontSize: 11,
    fontWeight: '700',
    color: '#94a3b8',
    letterSpacing: 0.8,
  },
  loadingContainer: {
    paddingVertical: 32,
    alignItems: 'center',
  },
  loadingText: {
    fontSize: 13,
    color: '#64748b',
    marginTop: 8,
  },
  emptyContainer: {
    paddingVertical: 36,
    alignItems: 'center',
  },
  emptyIcon: {
    fontSize: 32,
    marginBottom: 8,
  },
  emptyTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: '#334155',
  },
  emptySubtitle: {
    fontSize: 12,
    color: '#94a3b8',
    marginTop: 4,
  },
  listContent: {
    paddingBottom: 16,
  },
  taskItem: {
    backgroundColor: '#f8fafc',
    borderWidth: 1,
    borderColor: '#e2e8f0',
    borderRadius: 10,
    padding: 12,
    marginBottom: 10,
  },
  taskItemActive: {
    backgroundColor: '#f0fdf4',
    borderColor: '#86efac',
    borderWidth: 1.5,
  },
  taskItemHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 8,
  },
  taskRequest: {
    fontSize: 14,
    fontWeight: '600',
    color: '#1e293b',
    flex: 1,
    marginRight: 8,
  },
  taskRequestActive: {
    color: '#166534',
  },
  activeIndicator: {
    backgroundColor: '#22c55e',
    paddingHorizontal: 7,
    paddingVertical: 2,
    borderRadius: 8,
  },
  activeIndicatorText: {
    color: '#ffffff',
    fontSize: 10,
    fontWeight: '700',
  },
  taskItemFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  statusBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 6,
  },
  statusBadgeText: {
    fontSize: 11,
    fontWeight: '600',
  },
  taskDate: {
    fontSize: 11,
    color: '#94a3b8',
  },
});
