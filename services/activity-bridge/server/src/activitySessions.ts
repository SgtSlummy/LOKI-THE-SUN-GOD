import crypto from "node:crypto";

const SESSION_TTL_MS = 60 * 60 * 1000;

type ActivitySession = {
  token: string;
  userId: string;
  expiresAt: number;
};

const sessions = new Map<string, ActivitySession>();

function pruneExpiredSessions(now = Date.now()) {
  for (const [token, session] of sessions) {
    if (session.expiresAt <= now) sessions.delete(token);
  }
}

export function createActivitySession(userId: string): ActivitySession {
  pruneExpiredSessions();
  const session = {
    token: crypto.randomUUID(),
    userId,
    expiresAt: Date.now() + SESSION_TTL_MS
  };
  sessions.set(session.token, session);
  return session;
}

export function getActivitySession(token?: string | null): ActivitySession | null {
  if (!token) return null;
  const session = sessions.get(token);
  if (!session) return null;
  if (session.expiresAt <= Date.now()) {
    sessions.delete(token);
    return null;
  }
  return session;
}
