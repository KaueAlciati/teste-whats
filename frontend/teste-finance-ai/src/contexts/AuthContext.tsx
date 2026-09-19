"use client";

import {
  createContext,
  useContext,
  useState,
  useCallback,
  ReactNode,
  useEffect,
} from "react";
import { api } from "@/lib/api";
import type { AuthSession, UserProfile } from "@/lib/api";

interface AuthContextType {
  session: AuthSession | null;
  user: UserProfile | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (
    name: string,
    email: string,
    whatsappPhone: string,
    password: string,
  ) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const STORAGE_KEY = "financeai_session";

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<AuthSession | null>(null);
  const [user, setUser] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const initAuth = async () => {
      try {
        const storedSession = localStorage.getItem(STORAGE_KEY);
        if (storedSession) {
          const parsedSession: AuthSession = JSON.parse(storedSession);
          if (!parsedSession.session_token) throw new Error("Sessão inválida");
          const profile = await api.getMe(parsedSession.session_token);
          const validatedSession = { ...parsedSession, user: profile };
          localStorage.setItem(STORAGE_KEY, JSON.stringify(validatedSession));
          setSession(validatedSession);
          setUser(profile);
        }
      } catch {
        localStorage.removeItem(STORAGE_KEY);
        setSession(null);
        setUser(null);
      } finally {
        setLoading(false);
      }
    };

    initAuth();
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const token = await api.login({ email, password });
    const profile = await api.getMe(token.access_token);
    const authenticatedSession: AuthSession = {
      session_token: token.access_token,
      user: profile,
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(authenticatedSession));
    setSession(authenticatedSession);
    setUser(profile);
  }, []);

  const register = useCallback(
    async (
      name: string,
      email: string,
      whatsappPhone: string,
      password: string,
    ) => {
      await api.register({
        name,
        email,
        whatsapp_phone: whatsappPhone,
        password,
      });
      const token = await api.login({ email, password });
      const profile = await api.getMe(token.access_token);
      const authenticatedSession: AuthSession = {
        session_token: token.access_token,
        user: profile,
      };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(authenticatedSession));
      setSession(authenticatedSession);
      setUser(profile);
    },
    [],
  );

  const logout = useCallback(async () => {
    localStorage.removeItem(STORAGE_KEY);
    setSession(null);
    setUser(null);
  }, []);

  const refreshUser = useCallback(async () => {
    if (session) {
      const profile = await api.getMe(session.session_token);
      setUser(profile);
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
