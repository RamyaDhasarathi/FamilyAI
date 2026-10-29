import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { Message } from '../types';

interface MessageBubbleProps {
  message: Message;
}

export const MessageBubble: React.FC<MessageBubbleProps> = ({ message }) => {
  const isUser = message.sender_type === 'USER';

  return (
    <View
      style={[
        styles.bubbleContainer,
        isUser ? styles.userContainer : styles.agentContainer,
      ]}
    >
      <View style={[styles.bubble, isUser ? styles.userBubble : styles.agentBubble]}>
        <Text style={[styles.senderLabel, isUser ? styles.userLabel : styles.agentLabel]}>
          {isUser ? 'You' : 'Purchase Agent'}
        </Text>
        <Text style={[styles.messageText, isUser ? styles.userText : styles.agentText]}>
          {message.content}
        </Text>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  bubbleContainer: {
    marginVertical: 6,
    paddingHorizontal: 12,
    flexDirection: 'row',
  },
  userContainer: {
    justifyContent: 'flex-end',
  },
  agentContainer: {
    justifyContent: 'flex-start',
  },
  bubble: {
    maxWidth: '82%',
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.08,
    shadowRadius: 2,
    elevation: 1,
  },
  userBubble: {
    backgroundColor: '#3b82f6',
    borderBottomRightRadius: 4,
  },
  agentBubble: {
    backgroundColor: '#ffffff',
    borderBottomLeftRadius: 4,
    borderWidth: 1,
    borderColor: '#e2e8f0',
  },
  senderLabel: {
    fontSize: 10,
    fontWeight: '700',
    marginBottom: 4,
    textTransform: 'uppercase',
  },
  userLabel: {
    color: '#dbeafe',
  },
  agentLabel: {
    color: '#64748b',
  },
  messageText: {
    fontSize: 15,
    lineHeight: 21,
  },
  userText: {
    color: '#ffffff',
  },
  agentText: {
    color: '#1e293b',
  },
});
