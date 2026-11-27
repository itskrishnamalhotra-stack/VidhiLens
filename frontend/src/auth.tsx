import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { initializeApp, getApps } from "firebase/app";
import {
  GoogleAuthProvider,
  RecaptchaVerifier,
  getAuth,
  linkWithPhoneNumber,
  onAuthStateChanged,
  signInWithPopup,
  signOut,
  type User as FirebaseUser,
  type ConfirmationResult,
} from "firebase/auth";
import { firebaseConfig, firebaseConfigured } from "./config";

export interface AppUser {
  uid: string;
  displayName: string;
  email?: string | null;
  photoURL?: string | null;
  mode: "firebase" | "demo";
  phoneNumber?: string | null;
}

interface AuthContextValue {
  user: AppUser | null;
  loading: boolean;
  firebaseEnabled: boolean;
  signInGoogle: () => Promise<void>;
  signInDemo: (token: string, userId: string) => void;
  logout: () => Promise<void>;
  authHeaders: () => Promise<Record<string, string>>;
  startPhoneVerification: (phone: string, containerId: string) => Promise<void>;
  completePhoneVerification: (code: string) => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);
const DEMO_TOKEN_KEY = "legalai.demoToken";
const DEMO_USER_KEY = "legalai.demoUser";

const firebaseAuth = firebaseConfigured
  ? getAuth(getApps()[0] || initializeApp(firebaseConfig))
  : null;

function mapFirebaseUser(user: FirebaseUser): AppUser {
  return {
    uid: user.uid,
    displayName: user.displayName || (user.isAnonymous ? "Guest user" : "Signed-in user"),
    email: user.email,
    photoURL: user.photoURL,
    mode: "firebase",
    phoneNumber: user.phoneNumber,
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [phoneConfirmation, setPhoneConfirmation] = useState<ConfirmationResult | null>(null);
  const [user, setUser] = useState<AppUser | null>(() => {
    if (firebaseConfigured) return null;
    const token = sessionStorage.getItem(DEMO_TOKEN_KEY);
    const uid = sessionStorage.getItem(DEMO_USER_KEY);
    return token && uid ? { uid, displayName: uid, mode: "demo" } : null;
  });
  const [loading, setLoading] = useState(firebaseConfigured);

  useEffect(() => {
    if (!firebaseAuth) return;
    return onAuthStateChanged(firebaseAuth, (next) => {
      setUser(next ? mapFirebaseUser(next) : null);
      setLoading(false);
    });
  }, []);

  const signInGoogle = useCallback(async () => {
    if (!firebaseAuth) throw new Error("Firebase is not configured");
    await signInWithPopup(firebaseAuth, new GoogleAuthProvider());
  }, []);

  const signInDemo = useCallback((token: string, userId: string) => {
    const cleanToken = token.trim();
    const cleanUser = userId.trim();
    if (!cleanToken || !/^[A-Za-z0-9_.-]{1,128}$/.test(cleanUser)) {
      throw new Error("Enter a valid temporary token and user ID");
    }
    sessionStorage.setItem(DEMO_TOKEN_KEY, cleanToken);
    sessionStorage.setItem(DEMO_USER_KEY, cleanUser);
    setUser({ uid: cleanUser, displayName: cleanUser, mode: "demo" });
  }, []);

  const logout = useCallback(async () => {
    sessionStorage.removeItem(DEMO_TOKEN_KEY);
    sessionStorage.removeItem(DEMO_USER_KEY);
    if (firebaseAuth) await signOut(firebaseAuth);
    setUser(null);
  }, []);

  const startPhoneVerification = useCallback(async (phone: string, containerId: string) => {
    if (!firebaseAuth?.currentUser) throw new Error("Sign in before verifying your phone");
    if (!/^\+[1-9]\d{7,14}$/.test(phone)) throw new Error("Enter your phone with country code, for example +91…");
    const verifier = new RecaptchaVerifier(firebaseAuth, containerId, { size: "normal" });
    try {
      const confirmation = await linkWithPhoneNumber(firebaseAuth.currentUser, phone, verifier);
      setPhoneConfirmation(confirmation);
    } catch (error) {
      verifier.clear();
      throw error;
    }
  }, []);

  const completePhoneVerification = useCallback(async (code: string) => {
    if (!phoneConfirmation || !firebaseAuth?.currentUser) throw new Error("Request a verification code first");
    await phoneConfirmation.confirm(code.trim());
    await firebaseAuth.currentUser.reload();
    await firebaseAuth.currentUser.getIdToken(true);
    setUser(mapFirebaseUser(firebaseAuth.currentUser));
    setPhoneConfirmation(null);
  }, [phoneConfirmation]);

  const authHeaders = useCallback(async (): Promise<Record<string, string>> => {
    if (firebaseAuth?.currentUser) {
      return { Authorization: `Bearer ${await firebaseAuth.currentUser.getIdToken()}` };
    }
    if (firebaseConfigured) throw new Error("Sign in with Google before making a request");
    const token = sessionStorage.getItem(DEMO_TOKEN_KEY);
    const uid = sessionStorage.getItem(DEMO_USER_KEY);
    if (!token || !uid) throw new Error("Sign in before making a request");
    return {
      Authorization: `Bearer ${token}`,
      "X-LegalAI-Demo-User": uid,
    };
  }, []);

  const value = useMemo<AuthContextValue>(() => ({
    user,
    loading,
    firebaseEnabled: firebaseConfigured,
    signInGoogle,
    signInDemo,
    logout,
    authHeaders, startPhoneVerification, completePhoneVerification,
  }), [user, loading, signInGoogle, signInDemo, logout, authHeaders,
    startPhoneVerification, completePhoneVerification]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used within AuthProvider");
  return value;
}
