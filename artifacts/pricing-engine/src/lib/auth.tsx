import React, { createContext, useContext, useEffect, useState } from "react";
import { useLocation } from "wouter";
import { useGetCurrentUser, setAuthTokenGetter } from "@workspace/api-client-react";

// Initialize auth token getter
setAuthTokenGetter(() => localStorage.getItem("auth_token"));

export const getAuthToken = (): string => localStorage.getItem("auth_token") || "";

export const setAuthToken = (token: string | null) => {
  if (token) {
    localStorage.setItem("auth_token", token);
  } else {
    localStorage.removeItem("auth_token");
  }
};

const AuthContext = createContext<{
  user: any;
  isLoading: boolean;
  logout: () => void;
}>({
  user: null,
  isLoading: true,
  logout: () => {},
});

export const AuthProvider = ({ children }: { children: React.ReactNode }) => {
  const [, setLocation] = useLocation();
  const { data: user, isLoading, isError, error } = useGetCurrentUser({
    query: {
      retry: false,
    }
  });

  useEffect(() => {
    if (!isLoading && isError && (error as any)?.status === 401) {
      setLocation("/login");
    }
  }, [isLoading, isError, error, setLocation]);

  const logout = () => {
    setAuthToken(null);
    setLocation("/login");
  };

  return (
    <AuthContext.Provider value={{ user, isLoading, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
