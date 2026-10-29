import { Redirect } from 'expo-router';
import { useAuthStore } from '../src/state/authStore';

export default function Index() {
  const { isAuthenticated, isLoading } = useAuthStore();

  if (isLoading) {
    return null;
  }

  return <Redirect href={isAuthenticated ? '/purchase' : '/login'} />;
}
