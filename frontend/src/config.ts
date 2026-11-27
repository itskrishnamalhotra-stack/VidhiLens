import type { RuntimeConfig } from "./types";
import { getApps, initializeApp } from "firebase/app";
import { doc, getDoc, getFirestore } from "firebase/firestore/lite";

const trimUrl = (value: string) => value.trim().replace(/\/$/, "");

export async function loadApiBaseUrl(): Promise<string> {
  if (firebaseConfigured) {
    try {
      const app = getApps()[0] || initializeApp(firebaseConfig);
      const snapshot = await getDoc(doc(getFirestore(app), "runtime", "active"));
      const url = snapshot.data()?.api_base_url;
      if (typeof url === "string" && /^https:\/\/[a-z0-9-]+\.trycloudflare\.com\/?$/.test(url)) {
        const clean = trimUrl(url);
        const response = await fetch(`${clean}/health`, { cache: "no-store", signal: AbortSignal.timeout(7000) });
        if (response.ok) {
          const health = await response.json();
          if (health.api === "ready" && health.auth_mode === "firebase" &&
              health.build_id === "nyayasetu_draft_intake_2026_09_29") return clean;
        }
      }
    } catch {
      // The app will retry while Colab starts or its tunnel changes.
    }
    return "";
  }
  const locallySelected = localStorage.getItem("legalai.apiBaseUrl");
  if (locallySelected) return trimUrl(locallySelected);
  try {
    const response = await fetch("/runtime-config.json", { cache: "no-store" });
    if (response.ok) {
      const config = (await response.json()) as RuntimeConfig;
      if (config.apiBaseUrl) return trimUrl(config.apiBaseUrl);
    }
  } catch {
    // The environment fallback below also supports local development.
  }
  return trimUrl(import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8080");
}

export const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY || "",
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN || "",
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID || "",
  appId: import.meta.env.VITE_FIREBASE_APP_ID || "",
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET || "",
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID || "",
};

export const firebaseConfigured = Boolean(
  import.meta.env.VITE_AUTH_MODE !== "demo" &&
  firebaseConfig.apiKey && firebaseConfig.authDomain &&
  firebaseConfig.projectId && firebaseConfig.appId
);
