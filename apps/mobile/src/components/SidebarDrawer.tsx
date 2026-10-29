import React from 'react';
import {
  Modal,
  StyleSheet,
  Text,
  TouchableOpacity,
  TouchableWithoutFeedback,
  View,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useAuthStore } from '../state/authStore';

interface SidebarDrawerProps {
  visible: boolean;
  onClose: () => void;
  activeRoute?: string;
  onNewPurchaseSession?: () => void;
}

export const SidebarDrawer: React.FC<SidebarDrawerProps> = ({
  visible,
  onClose,
  activeRoute = 'purchase',
  onNewPurchaseSession,
}) => {
  const router = useRouter();
  const { user, logout } = useAuthStore();

  const handleNavigate = (route: string) => {
    onClose();
    if (route === 'purchase') {
      router.push('/purchase');
    } else if (route === 'travel') {
      router.push('/travel');
    } else if (route === 'governance') {
      router.push('/governance');
    }
  };

  const handleLogout = async () => {
    onClose();
    await logout();
    router.replace('/login');
  };

  const isAdmin = user?.family_role === 'ADMIN';

  return (
    <Modal
      animationType="fade"
      transparent
      visible={visible}
      onRequestClose={onClose}
    >
      <View style={styles.overlay}>
        <TouchableWithoutFeedback onPress={onClose}>
          <View style={styles.backdrop} />
        </TouchableWithoutFeedback>

        <View style={styles.drawer}>
          {/* Header */}
          <View style={styles.drawerHeader}>
            <Text style={styles.appTitle}>FAMILY OS</Text>
            <Text style={styles.familyName}>{user?.family_name || 'Family Hub'}</Text>
          </View>

          <View style={styles.divider} />

          {/* Section: Agents */}
          <Text style={styles.sectionHeader}>AGENTS</Text>
          <TouchableOpacity
            style={[styles.navItem, activeRoute === 'purchase' && styles.navItemActive]}
            onPress={() => handleNavigate('purchase')}
          >
            <Text style={styles.navIcon}>🛒</Text>
            <Text
              style={[
                styles.navText,
                activeRoute === 'purchase' && styles.navTextActive,
              ]}
            >
              Purchase Agent
            </Text>
          </TouchableOpacity>

          {onNewPurchaseSession ? (
            <TouchableOpacity
              style={styles.subNavItem}
              onPress={() => {
                onClose();
                onNewPurchaseSession();
              }}
            >
              <Text style={styles.subNavIcon}>＋</Text>
              <Text style={styles.subNavText}>New Purchase Session</Text>
            </TouchableOpacity>
          ) : null}

          <TouchableOpacity
            style={[styles.navItem, activeRoute === 'travel' && styles.navItemActive]}
            onPress={() => handleNavigate('travel')}
          >
            <Text style={styles.navIcon}>✈️</Text>
            <Text
              style={[styles.navText, activeRoute === 'travel' && styles.navTextActive]}
            >
              Travel Agent
            </Text>
            <Text style={styles.badge}>Planned</Text>
          </TouchableOpacity>

          {/* Section: Administration (ADMIN only) */}
          {isAdmin ? (
            <>
              <View style={styles.divider} />
              <Text style={styles.sectionHeader}>ADMINISTRATION</Text>
              <TouchableOpacity
                style={[
                  styles.navItem,
                  activeRoute === 'governance' && styles.navItemActive,
                ]}
                onPress={() => handleNavigate('governance')}
              >
                <Text style={styles.navIcon}>🛡️</Text>
                <Text
                  style={[
                    styles.navText,
                    activeRoute === 'governance' && styles.navTextActive,
                  ]}
                >
                  Family Governance
                </Text>
              </TouchableOpacity>
            </>
          ) : null}

          {/* Spacer */}
          <View style={styles.spacer} />

          <View style={styles.divider} />

          {/* Current User & Logout */}
          <View style={styles.userFooter}>
            <Text style={styles.userDisplay}>{user?.display_name}</Text>
            <Text style={styles.userRole}>{user?.email}</Text>
            <Text style={styles.roleTag}>Role: {user?.family_role}</Text>

            <TouchableOpacity style={styles.logoutButton} onPress={handleLogout}>
              <Text style={styles.logoutText}>Log Out</Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    flexDirection: 'row',
  },
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
  },
  drawer: {
    width: 280,
    backgroundColor: '#1a1a2e',
    paddingTop: 48,
    paddingBottom: 24,
    paddingHorizontal: 16,
    shadowColor: '#000',
    shadowOffset: { width: 4, height: 0 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 16,
  },
  drawerHeader: {
    marginBottom: 16,
  },
  appTitle: {
    color: '#ffffff',
    fontSize: 20,
    fontWeight: 'bold',
    letterSpacing: 2,
  },
  familyName: {
    color: '#4a90d9',
    fontSize: 14,
    marginTop: 4,
  },
  divider: {
    height: 1,
    backgroundColor: '#2d2d44',
    marginVertical: 14,
  },
  sectionHeader: {
    color: '#7a7a99',
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 1.5,
    marginBottom: 8,
    marginTop: 4,
  },
  navItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 12,
    paddingHorizontal: 10,
    borderRadius: 8,
    marginBottom: 4,
  },
  navItemActive: {
    backgroundColor: '#272740',
  },
  subNavItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 8,
    paddingLeft: 40,
    paddingRight: 10,
    borderRadius: 6,
    marginBottom: 6,
    backgroundColor: 'rgba(37, 99, 235, 0.12)',
  },
  subNavIcon: {
    fontSize: 14,
    color: '#60a5fa',
    fontWeight: 'bold',
    marginRight: 8,
  },
  subNavText: {
    color: '#93c5fd',
    fontSize: 13,
    fontWeight: '600',
  },
  navIcon: {
    fontSize: 18,
    marginRight: 12,
  },
  navText: {
    color: '#d0d0e0',
    fontSize: 15,
    flex: 1,
  },
  navTextActive: {
    color: '#ffffff',
    fontWeight: '600',
  },
  badge: {
    color: '#f39c12',
    fontSize: 11,
    backgroundColor: 'rgba(243, 156, 18, 0.15)',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  spacer: {
    flex: 1,
  },
  userFooter: {
    paddingTop: 8,
  },
  userDisplay: {
    color: '#ffffff',
    fontSize: 15,
    fontWeight: '600',
  },
  userRole: {
    color: '#8e8ea0',
    fontSize: 12,
    marginTop: 2,
  },
  roleTag: {
    color: '#4a90d9',
    fontSize: 11,
    marginTop: 4,
  },
  logoutButton: {
    marginTop: 16,
    backgroundColor: '#2d2d44',
    paddingVertical: 10,
    borderRadius: 6,
    alignItems: 'center',
  },
  logoutText: {
    color: '#e74c3c',
    fontSize: 14,
    fontWeight: '600',
  },
});
