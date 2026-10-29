import { useState } from 'react';
import { Alert } from 'react-native';
import { Audio } from 'expo-av';
import { transcribeAudioApi } from '../api/purchase';

export interface UseVoiceResult {
  isRecording: boolean;
  isTranscribing: boolean;
  transcriptionText: string;
  errorMessage: string | null;
  startRecording: () => Promise<void>;
  stopRecording: () => Promise<string | null>;
  clearTranscription: () => void;
}

export function useVoice(): UseVoiceResult {
  const [recording, setRecording] = useState<Audio.Recording | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [transcriptionText, setTranscriptionText] = useState('');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const startRecording = async () => {
    setErrorMessage(null);
    try {
      const perm = await Audio.requestPermissionsAsync();
      if (!perm.granted) {
        Alert.alert(
          'Microphone Permission Required',
          'Please allow microphone access to use voice input.'
        );
        return;
      }

      await Audio.setAudioModeAsync({
        allowsRecordingIOS: true,
        playsInSilentModeIOS: true,
      });

      const { recording: newRecording } = await Audio.Recording.createAsync(
        Audio.RecordingOptionsPresets.HIGH_QUALITY
      );

      setRecording(newRecording);
      setIsRecording(true);
    } catch (err: unknown) {
      console.warn('Failed to start recording:', err);
      setErrorMessage('Could not initialize microphone recording.');
      setIsRecording(false);
    }
  };

  const stopRecording = async (): Promise<string | null> => {
    if (!recording) return null;

    try {
      setIsRecording(false);
      setIsTranscribing(true);
      await recording.stopAndUnloadAsync();
      const uri = recording.getURI();
      setRecording(null);

      if (!uri) {
        setIsTranscribing(false);
        return null;
      }

      // Transcribe via backend
      const result = await transcribeAudioApi(uri, 'audio/m4a');
      setIsTranscribing(false);

      if (result.is_available && result.text) {
        setTranscriptionText(result.text);
        return result.text;
      } else {
        setErrorMessage(
          result.message || 'Speech-to-text is not configured on the backend. Please type your message.'
        );
        return null;
      }
    } catch (err: unknown) {
      setIsTranscribing(false);
      setRecording(null);
      const msg = err && typeof err === 'object' && 'message' in err
        ? String(err.message)
        : 'Transcription failed. Please type your message.';
      setErrorMessage(msg);
      return null;
    }
  };

  const clearTranscription = () => {
    setTranscriptionText('');
    setErrorMessage(null);
  };

  return {
    isRecording,
    isTranscribing,
    transcriptionText,
    errorMessage,
    startRecording,
    stopRecording,
    clearTranscription,
  };
}
