import React, { useState } from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useRouter } from 'expo-router';
import { Header } from '../src/components/Header';
import { SidebarDrawer } from '../src/components/SidebarDrawer';

export default function TravelScreen() {
  const router = useRouter();
  const [drawerOpen, setDrawerOpen] = useState(false);

  return (
    <View style={styles.container}>
      <Header onToggleMenu={() => setDrawerOpen(true)} title="TRAVEL AGENT" />

      <View style={styles.content}>
        <View style={styles.card}>
          <Text style={styles.icon}>✈️</Text>
          <Text style={styles.title}>Travel Agent</Text>
          <View style={styles.badge}>
            <Text style={styles.badgeText}>PLANNED FOR FUTURE RELEASE</Text>
          </View>
          <Text style={styles.description}>
            Travel Agent is planned but is not implemented in this release.
          </Text>
          <Text style={styles.detail}>
            In future versions, the Travel Agent will coordinate family itineraries,
            compare flight and lodging options according to family safety guidelines,
            and hand execution instructions to the Mobile Use Agent with FGP oversight.
          </Text>

          <TouchableOpacity
            style={styles.backButton}
            onPress={() => router.push('/purchase')}
          >
            <Text style={styles.backButtonText}>← Switch to Purchase Agent</Text>
          </TouchableOpacity>
        </View>
      </View>

      <SidebarDrawer
        visible={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        activeRoute="travel"
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f1f5f9',
  },
  content: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 24,
  },
  card: {
    backgroundColor: '#ffffff',
    borderRadius: 16,
    padding: 28,
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 8,
    elevation: 3,
    maxWidth: 400,
  },
  icon: {
    fontSize: 52,
    marginBottom: 16,
  },
  title: {
    fontSize: 22,
    fontWeight: 'bold',
    color: '#0f172a',
    marginBottom: 8,
  },
  badge: {
    backgroundColor: '#fef3c7',
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 12,
    marginBottom: 16,
  },
  badgeText: {
    color: '#92400e',
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 1,
  },
  description: {
    fontSize: 16,
    color: '#334155',
    textAlign: 'center',
    fontWeight: '600',
    marginBottom: 12,
    lineHeight: 22,
  },
  detail: {
    fontSize: 13,
    color: '#64748b',
    textAlign: 'center',
    lineHeight: 19,
    marginBottom: 24,
  },
  backButton: {
    backgroundColor: '#3b82f6',
    paddingVertical: 12,
    paddingHorizontal: 20,
    borderRadius: 8,
  },
  backButtonText: {
    color: '#ffffff',
    fontSize: 14,
    fontWeight: '600',
  },
});
