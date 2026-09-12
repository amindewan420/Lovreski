// Firebase Web SDK client — initialized only when env vars are present.
// This lets us ship the FCM feature dark until the user pastes credentials.
import { initializeApp, getApps } from "firebase/app";
import { getMessaging, isSupported } from "firebase/messaging";

const firebaseConfig = {
  apiKey: process.env.REACT_APP_FIREBASE_API_KEY,
  authDomain: process.env.REACT_APP_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.REACT_APP_FIREBASE_PROJECT_ID,
  storageBucket: process.env.REACT_APP_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: process.env.REACT_APP_FIREBASE_MESSAGING_SENDER_ID,
  appId: process.env.REACT_APP_FIREBASE_APP_ID,
};

export const FCM_CONFIGURED = Boolean(
  firebaseConfig.apiKey && firebaseConfig.projectId && firebaseConfig.appId &&
  process.env.REACT_APP_FIREBASE_VAPID_KEY
);

export const VAPID_KEY = process.env.REACT_APP_FIREBASE_VAPID_KEY || "";

let _app = null;
export function getFirebaseApp() {
  if (!FCM_CONFIGURED) return null;
  if (_app) return _app;
  _app = getApps().length ? getApps()[0] : initializeApp(firebaseConfig);
  return _app;
}

export async function getBrowserMessaging() {
  const app = getFirebaseApp();
  if (!app) return null;
  try {
    if (!(await isSupported())) return null;
    return getMessaging(app);
  } catch (e) {
    // Safari on iOS < 16.4 / private mode / etc.
    console.warn("[fcm] getMessaging unsupported:", e);
    return null;
  }
}
