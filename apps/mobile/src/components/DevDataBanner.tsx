import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

interface DevDataBannerProps {
  message?: string;
}

export const DevDataBanner: React.FC<DevDataBannerProps> = ({
  message = 'Development Catalogue Data — Not live marketplace information. Real purchases cannot be made.',
}) => {
  return (
    <View style={styles.container}>
      <Text style={styles.icon}>⚠️</Text>
      <Text style={styles.text}>{message}</Text>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    backgroundColor: '#fef3c7',
    borderColor: '#f59e0b',
    borderWidth: 1,
    borderRadius: 8,
    padding: 10,
    marginHorizontal: 12,
    marginVertical: 6,
    flexDirection: 'row',
    alignItems: 'center',
  },
  icon: {
    fontSize: 16,
    marginRight: 8,
  },
  text: {
    flex: 1,
    fontSize: 12,
    color: '#92400e',
    fontWeight: '500',
    lineHeight: 16,
  },
});
