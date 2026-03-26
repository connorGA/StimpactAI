import { SignJWT, jwtVerify } from "jose";

export const SESSION_COOKIE_NAME = "stimpact_session";
const SESSION_ALGORITHM = "HS256";

export type SessionClaims = {
  sub: string;
  org_id: string;
  role: "owner" | "admin" | "member";
  type: "session";
  iat: number;
  exp: number;
};

function getSessionSecret(): Uint8Array {
  const value =
    process.env.AGENT_PLATFORM_AUTH_SESSION_SECRET ?? "stimpact-dev-session-secret";
  return new TextEncoder().encode(value);
}

export async function verifySessionToken(
  token: string,
): Promise<SessionClaims | null> {
  try {
    const { payload } = await jwtVerify(token, getSessionSecret(), {
      algorithms: [SESSION_ALGORITHM],
    });
    if (
      typeof payload.sub !== "string" ||
      typeof payload.org_id !== "string" ||
      typeof payload.role !== "string" ||
      payload.type !== "session"
    ) {
      return null;
    }
    return payload as unknown as SessionClaims;
  } catch {
    return null;
  }
}

export async function signSessionToken(payload: SessionClaims): Promise<string> {
  return new SignJWT({
    org_id: payload.org_id,
    role: payload.role,
    type: payload.type,
  })
    .setProtectedHeader({ alg: SESSION_ALGORITHM })
    .setSubject(payload.sub)
    .setIssuedAt(payload.iat)
    .setExpirationTime(payload.exp)
    .sign(getSessionSecret());
}

export const sessionCookieOptions = {
  httpOnly: true,
  sameSite: "lax" as const,
  secure: process.env.NODE_ENV === "production",
  path: "/",
};
