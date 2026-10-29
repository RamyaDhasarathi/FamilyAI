import React from 'react';
import { Platform, StatusBar, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useAuthStore } from '../state/authStore';

interface HeaderProps {
  onToggleMenu: () => void;
  title?: string;
  onNewChat?: () => void;
  onOpenSessions?: () => void;
  showChatActions?: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  onToggleMenu,
  title = 'FAMILY OS',
  onNewChat,
  onOpenSessions,
  showChatActions = false,
}) => {
  const { user } = useAuthStore();
  const insets = useSafeAreaInsets();

  const topInset = Math.max(
    insets.top,
    Platform.OS === 'android' ? (StatusBar.currentHeight || 24) : 0
  );

  return (
    <View style={[styles.container, { paddingTop: topInset + 6 }]}>
      <TouchableOpacity
        style={styles.menuButton}
        onPress={onToggleMenu}
        accessibilityRole="button"
        accessibilityLabel="Open Navigation Menu"
      >
        <Text style={styles.menuIcon}>☰</Text>
      </TouchableOpacity>

      <View style={styles.titleContainer}>
        <Text style={styles.title} numberOfLines={1}>
          {title}
        </Text>
        {user ? (
          <Text style={styles.subtitle} numberOfLines={1}>
            {user.display_name} ({user.family_role})
          </Text>
        ) : null}
      </View>

      {showChatActions ? (
        <View style={styles.actionContainer}>
          {onOpenSessions ? (
            <TouchableOpacity
              style={styles.historyButton}
              onPress={onOpenSessions}
              accessibilityRole="button"
              accessibilityLabel="View Chat Sessions"
            >
              <Text style={styles.historyIcon}>📋</Text>
            </TouchableOpacity>
          ) : null}
          {onNewChat ? (
            <TouchableOpacity
              style={styles.newChatButton}
              onPress={onNewChat}
              accessibilityRole="button"
              accessibilityLabel="New Chat Session"
            >
              <Text style={styles.newChatIcon}>＋</Text>
              <Text style={styles.newChatText}>New</Text>
            </TouchableOpacity>
          ) : null}
        </View>
      ) : null}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    backgroundColor: '#1a1a2e',
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingBottom: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#2d2d44',
  },
  menuButton: {
    padding: 8,
    marginRight: 8,
  },
  menuIcon: {
    color: '#ffffff',
    fontSize: 22,
    fontWeight: 'bold',
  },
  titleContainer: {
    flex: 1,
    justifyContent: 'center',
  },
  title: {
    color: '#ffffff',
    fontSize: 16,
    fontWeight: 'bold',
    letterSpacing: 0.5,
  },
  subtitle: {
    color: '#a0a0b8',
    fontSize: 11,
    marginTop: 2,
  },
  actionContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    marginLeft: 8,
  },
  historyButton: {
    paddingHorizontal: 10,
    paddingVertical: 7,
    backgroundColor: '#262640',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#3a3a5c',
    marginRight: 8,
  },
  historyIcon: {
    fontSize: 15,
  },
  newChatButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#2563eb',
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderRadius: 8,
    shadowColor: '#2563eb',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.3,
    shadowRadius: 3,
    elevation: 3,
  },
  newChatIcon: {
    color: '#ffffff',
    fontSize: 14,
    fontWeight: 'bold',
    marginRight: 4,
  },
  newChatText: {
    color: '#ffffff',
    fontSize: 13,
    fontWeight: '700',
  },
});
