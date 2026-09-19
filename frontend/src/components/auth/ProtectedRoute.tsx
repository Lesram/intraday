/**
 * Protected Route Component
 * Wrapper for routes that require authentication and optional role-based access
 */

import { useEffect, useRef, useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { Spin } from 'antd';
import { useAuthStore } from '@/store/authStore';
import type { UserRole } from '@/types/auth';

interface ProtectedRouteProps {
  children: React.ReactNode;
  /** Optional required role(s). If set, user must have one of these roles. */
  requiredRoles?: UserRole[];
}

/**
 * DEV ONLY: When VITE_DEV_BYPASS_AUTH=true, auto-login with admin credentials
 * so you can skip the login page during development.  The backend still gets
 * a real JWT — all API calls work normally.
 *
 * To disable: remove or set VITE_DEV_BYPASS_AUTH=false in .env.local
 *
 * V13 W98 (Lens 7) build-fence: in production-mode builds, the
 * bypass is hard-OFF regardless of env so a stray .env.production
 * with VITE_DEV_BYPASS_AUTH=true cannot enable admin auto-login.
 * Vite's import.meta.env.MODE === 'development' is the build-time
 * mode (set by --mode), distinct from NODE_ENV.  The MODE check is
 * also DEV-tree-shakeable: in production builds the second `&&`
 * operand is dropped at compile time.
 */
const DEV_BYPASS_AUTH =
  import.meta.env.MODE === 'development' &&
  import.meta.env.VITE_DEV_BYPASS_AUTH === 'true';

const ProtectedRoute = ({ children, requiredRoles }: ProtectedRouteProps) => {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const user = useAuthStore((state) => state.user);
  const setAuth = useAuthStore((state) => state.setAuth);
  const location = useLocation();

  // Start as true when bypass is active and not yet logged in,
  // so we block the redirect until the auto-login attempt completes.
  const [bypassPending, setBypassPending] = useState(
    () => DEV_BYPASS_AUTH && !useAuthStore.getState().isAuthenticated,
  );
  const attemptedRef = useRef(false);

  useEffect(() => {
    if (!DEV_BYPASS_AUTH || isAuthenticated || attemptedRef.current) {
      setBypassPending(false);
      return;
    }
    attemptedRef.current = true;

    const autoLogin = async () => {
      try {
        const { authService } = await import('@/services/authService');
        const resp = await authService.login({
          username: 'admin@example.com',
          password: 'admin123',
        });
        setAuth(resp.user, resp.access_token, resp.refresh_token, resp.expires_in);
        console.info('[DEV] Auth bypass: auto-logged in as admin');
      } catch (err) {
        console.warn('[DEV] Auth bypass failed — falling back to login page:', err);
      } finally {
        setBypassPending(false);
      }
    };
    autoLogin();
  }, [isAuthenticated, setAuth]);

  // Wait for auto-login to finish before deciding to redirect
  if (bypassPending) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <Spin tip="Auto-login..." size="large" />
      </div>
    );
  }

  // If not authenticated, redirect to login
  // Save the attempted location so we can redirect back after login
  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // Role-based access control
  if (requiredRoles && requiredRoles.length > 0 && user) {
    if (!requiredRoles.includes(user.role)) {
      return <Navigate to="/" replace />;
    }
  }

  return <>{children}</>;
};

export default ProtectedRoute;
