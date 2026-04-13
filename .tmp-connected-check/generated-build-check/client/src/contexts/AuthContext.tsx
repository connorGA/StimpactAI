import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { User } from '@shared/schema';
import { authService } from '@/lib/authService';
import { accountStatusService } from '@/lib/accountStatusService';
import { getAuthToken } from '@/lib/xanoClient';
import { queryClient } from '@/lib/queryClient';

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (name: string, email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const isAuthenticated = !!user;

  // Fetch current user on mount if token exists
  useEffect(() => {
    const initAuth = async () => {
      const token = getAuthToken();
      if (token) {
        try {
          const currentUser = await authService.getCurrentUser();
          setUser(currentUser);
          // Invalidate queries to ensure fresh data on app init
          queryClient.invalidateQueries({ queryKey: ['/account_status', currentUser.id] });
        } catch (error) {
          console.error('Failed to fetch current user:', error);
          authService.logout();
        }
      }
      setIsLoading(false);
    };

    initAuth();
  }, []);

  // Listen for auth events
  useEffect(() => {
    const handleUnauthorized = () => {
      setUser(null);
    };

    const handleLogout = () => {
      setUser(null);
    };

    window.addEventListener('auth:unauthorized', handleUnauthorized);
    window.addEventListener('auth:logout', handleLogout);

    return () => {
      window.removeEventListener('auth:unauthorized', handleUnauthorized);
      window.removeEventListener('auth:logout', handleLogout);
    };
  }, []);

  const login = async (email: string, password: string) => {
    setIsLoading(true);
    try {
      const response = await authService.login({ email, password });
      setUser(response.user);
      // Invalidate queries to ensure fresh data after login
      queryClient.invalidateQueries({ queryKey: ['/account_status', response.user.id] });
    } finally {
      setIsLoading(false);
    }
  };

  const signup = async (name: string, email: string, password: string) => {
    setIsLoading(true);
    try {
      const response = await authService.signup({ name, email, password });
      setUser(response.user);

      // Create account status with free tier for new user
      try {
        await accountStatusService.create({
          user_id: response.user.id,
          plan_tier: 'free',
        });
        // Invalidate queries to ensure fresh data
        queryClient.invalidateQueries({ queryKey: ['/account_status', response.user.id] });
      } catch (error) {
        console.error('Failed to create account status:', error);
        // Don't fail signup if account status creation fails
        // The user can still use the app with default free tier
      }
    } finally {
      setIsLoading(false);
    }
  };

  const logout = () => {
    authService.logout();
    setUser(null);
  };

  const refreshUser = async () => {
    try {
      const currentUser = await authService.getCurrentUser();
      setUser(currentUser);
    } catch (error) {
      console.error('Failed to refresh user:', error);
      logout();
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated,
        login,
        signup,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}
