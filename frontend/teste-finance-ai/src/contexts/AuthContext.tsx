"use client";

import {
  createContext,
  useContext,
  useState,
  useCallback,
  ReactNode,
  useEffect,
} from "react";
import { storage } from "@/lib/storage";
import type { AuthSession, UserProfile } from "@/lib/api";

interface AuthContextType {
  session: AuthSession | null;
  user: UserProfile | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const STORAGE_KEY = "financeai_session";

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<AuthSession | null>(null);
  const [user, setUser] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);

  // Initialize auth from localStorage
  useEffect(() => {
    const initAuth = async () => {
      try {
        const storedSession = localStorage.getItem(STORAGE_KEY);
        if (storedSession) {
          const parsedSession: AuthSession = JSON.parse(storedSession);
          // Check if session is expired
          const isExpired = new Date(parsedSession.expires_at) < new Date();
          if (!isExpired) {
            setSession(parsedSession);
            setUser(parsedSession.user);
          } else {
            localStorage.removeItem(STORAGE_KEY);
          }
        }
      } catch (error) {
        console.error("Error initializing auth:", error);
        localStorage.removeItem(STORAGE_KEY);
      } finally {
        setLoading(false);
      }
    };

    initAuth();
  }, []);

  // Update fetchWithTimeout to include auth token
  const login = useCallback(async (email: string, password: string) => {
    const response = await storage.login({ email, password });
    localStorage.setItem(STORAGE_KEY, JSON.stringify(response));
    setSession(response);
    setUser(response.user);
  }, []);

  const register = useCallback(async (name: string, email: string, password: string) => {
    const response = await storage.register({ name, email, password });
    localStorage.setItem(STORAGE_KEY, JSON.stringify(response));
    setSession(response);
    setUser(response.user);
  }, []);

  const logout = useCallback(async () => {
    if (session) {
      try {
        await storage.logout(session.session_token);
      } catch (error) {
        console.error("Error during logout:", error);
      }
    }
    localStorage.removeItem(STORAGE_KEY);
    setSession(null);
    setUser(null);
  }, [session]);

  const refreshUser = useCallback(async () => {
    if (session) {
      const profile = await storage.getProfile();
      setUser(profile);
      // Update session with new user data
      const updatedSession = { ...session, user: profile };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(updatedSession));
      setSession(updatedSession);
    }
  }, [session]);

  return (
    <AuthContext.Provider
      value={{
        session,
        user,
        loading,
        login,
        register,
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
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
