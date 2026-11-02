// "Ask FamilyOS" / "Ask {Agent}" chat (AGENT.md §8.6, video 1:45 and 2:55).
import { useEffect, useRef, useState, type ComponentRef } from 'react';
import { ScrollView, StyleSheet, TextInput, View } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { ArrowUp } from 'lucide-react-native';
import type { AgentId } from '../theme/tokens';
import { colors, withAlpha } from '../theme/tokens';
import { type as T, fonts, MAX_FONT_SCALE } from '../theme/typography';
import { agentNames, copy } from '../mocks/data';
import { useFamilyOS } from '../store/useFamilyOS';
import { AppText } from '../components/AppText';
import { ChatBubble, SuggestionChips, TypingDots } from '../components/Chat';
import { ModalCard } from '../components/ModalCard';
import { ClosePill } from '../components/Pills';
import { Pressy } from '../components/Pressy';

const NO_CHIPS: string[] = [];

export function ChatSheet({ visible, onClose, thread }: { visible: boolean; onClose: () => void; thread: string }) {
  const messages = useFamilyOS((s) => s.threads[thread]);
  const typing = useFamilyOS((s) => !!s.typing[thread]);
  const chips = useFamilyOS((s) => s.suggestions[thread]) ?? NO_CHIPS;
  const send = useFamilyOS((s) => s.sendChat);
  const takePending = useFamilyOS((s) => s.takePending);
  const [text, setText] = useState('');
  const scroll = useRef<ComponentRef<typeof ScrollView>>(null);
  const input = useRef<ComponentRef<typeof TextInput>>(null);
  const isAgent = thread !== 'home';
  const accent = isAgent ? colors.agents[thread as AgentId] : '#7F8CFF';
  const title = isAgent ? copy.chatAgentTitle(agentNames[thread as AgentId]) : copy.chatTitle;

  useEffect(() => {
    if (!visible) return;
    const pending = takePending();
    if (pending) void send(thread, pending);
    else {
      const id = setTimeout(() => input.current?.focus(), 350);
      return () => clearTimeout(id);
    }
  }, [visible, thread, send, takePending]);

  useEffect(() => {
    const id = setTimeout(() => scroll.current?.scrollToEnd({ animated: true }), 60);
    return () => clearTimeout(id);
  }, [messages?.length, typing]);

  const submit = (t: string) => {
    if (!t.trim()) return;
    setText('');
    void send(thread, t);
  };

  const header = (
    <View style={styles.header}>
      <View>
        <AppText style={T.sheetTitle} accessibilityRole="header">
          {title}
        </AppText>
        <LinearGradient
          colors={[accent, withAlpha(accent, 0)]}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 0 }}
          style={styles.underline}
        />
      </View>
      <ClosePill onPress={onClose} style={styles.close} />
    </View>
  );

  return (
    <ModalCard visible={visible} onClose={onClose} header={header} closeAbove={false} fixedFrac={0.8} keyboardAware>
      <ScrollView
        ref={scroll}
        style={styles.list}
        contentContainerStyle={styles.listBody}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        {messages?.map((m) => <ChatBubble key={m.id} msg={m} />)}
        {typing ? <TypingDots /> : null}
      </ScrollView>
      <SuggestionChips chips={chips} onPick={submit} />
      <View style={styles.inputRow}>
        <TextInput
          ref={input}
          value={text}
          onChangeText={setText}
          placeholder={copy.typeMessage}
          placeholderTextColor={colors.muted}
          style={styles.input}
          returnKeyType="send"
          onSubmitEditing={() => submit(text)}
          maxFontSizeMultiplier={MAX_FONT_SCALE}
          accessibilityLabel={copy.typeMessage}
          selectionColor={accent}
        />
        <Pressy onPress={() => submit(text)} accessibilityLabel="Send" style={styles.send}>
          <ArrowUp size={18} color={colors.pillPrimaryInk} strokeWidth={2.2} />
        </Pressy>
      </View>
    </ModalCard>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', paddingHorizontal: 18, paddingTop: 18, paddingBottom: 10 },
  underline: { height: 3, width: 64, borderRadius: 2, marginTop: 6 },
  close: { alignSelf: 'flex-start' },
  list: { flex: 1 },
  listBody: { paddingHorizontal: 14, paddingTop: 6, paddingBottom: 6 },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginHorizontal: 10,
    marginBottom: 10,
    height: 52,
    borderRadius: 26,
    backgroundColor: 'rgba(255,255,255,0.06)',
    borderWidth: 1,
    borderColor: colors.glassBorder,
    paddingLeft: 18,
    paddingRight: 6,
  },
  input: { flex: 1, color: colors.ink, fontFamily: fonts.medium, fontSize: 15, paddingVertical: 0 },
  send: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.pillPrimaryBg, alignItems: 'center', justifyContent: 'center' },
});
