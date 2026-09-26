import { useEffect, type ReactNode } from 'react';
import { Spin } from 'antd';
import { useAuthStore } from '@/store/authStore';

/** No protected route, portfolio query or socket mounts before restoration. */
export default function AuthBootstrap({ children }: { children: ReactNode }) {
  const ready = useAuthStore((state) => state.sessionReady);
  const restore = useAuthStore((state) => state.restoreSession);
  useEffect(() => { void restore(); }, [restore]);
  if (!ready) return <div role="status"><Spin /> Restoring session...</div>;
  return <>{children}</>;
}
