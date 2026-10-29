import React from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { ApiError } from '../types';

interface ErrorBannerProps {
  error: ApiError | string | null;
  onDismiss?: () => void;
  onRetry?: () => void;
}

export const ErrorBanner: React.FC<ErrorBannerProps> = ({
  error,
  onDismiss,
  onRetry,
}) => {
  if (!error) return null;

  const message = typeof error === 'string' ? error : error.message;
  const code = typeof error === 'string' ? '' : error.code;

  return (
    <View style={styles.container}>
      <View style={styles.textContainer}>
        {code ? <Text style={styles.codeText}>{code}</Text> : null}
        <Text style={styles.messageText}>{message}</Text>
      </View>
      <View style={styles.actions}>
        {onRetry ? (
          <TouchableOpacity style={styles.retryBtn} onPress={onRetry}>
            <Text style={styles.retryText}>Retry</Text>
          </TouchableOpacity>
        ) : null}
        {onDismiss ? (
          <TouchableOpacity style={styles.dismissBtn} onPress={onDismiss}>
            <Text style={styles.dismissText}>✕</Text>
          </TouchableOpacity>
        ) : null}
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    backgroundColor: '#fee2e2',
    borderColor: '#ef4444',
    borderWidth: 1,
    borderRadius: 8,
    padding: 12,
    marginHorizontal: 12,
    marginVertical: 6,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  textContainer: {
    flex: 1,
    marginRight: 8,
  },
  codeText: {
    fontSize: 10,
    fontWeight: '700',
    color: '#991b1b',
    marginBottom: 2,
    textTransform: 'uppercase',
  },
  messageText: {
    fontSize: 13,
    color: '#b91c1c',
  },
  actions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  retryBtn: {
    backgroundColor: '#ef4444',
    paddingVertical: 5,
    paddingHorizontal: 10,
    borderRadius: 4,
  },
  retryText: {
    color: '#ffffff',
    fontSize: 12,
    fontWeight: '600',
  },
  dismissBtn: {
    padding: 4,
  },
  dismissText: {
    color: '#991b1b',
    fontSize: 16,
    fontWeight: 'bold',
  },
});
