import { createRemoteJWKSet, jwtVerify } from "jose";
import { ApiError } from "./config.js";
const keys = new Map();
export async function identity(request, env) {
  const id = env.PRIVY_APP_ID;
  if (!id) throw new ApiError(503, "Privy authentication is not configured");
  const auth = request.headers.get("Authorization") || "";
  if (!auth.startsWith("Bearer ") || auth.length > 16384)
    throw new ApiError(401, "Sign in to trade");
  try {
    let jwks = keys.get(id);
    if (!jwks) {
      jwks = createRemoteJWKSet(
        new URL(
          `https://auth.privy.io/api/v1/apps/${encodeURIComponent(id)}/jwks.json`,
        ),
        { timeoutDuration: 5000, cacheMaxAge: 3600000 },
      );
      keys.set(id, jwks);
    }
    const { payload } = await jwtVerify(auth.slice(7), jwks, {
      algorithms: ["ES256"],
      issuer: "privy.io",
      audience: id,
      requiredClaims: ["exp", "iat", "iss", "aud", "sub"],
    });
    if (
      typeof payload.sub !== "string" ||
      !payload.sub.startsWith("did:privy:") ||
      typeof payload.iat !== "number" ||
      payload.iat > Math.floor(Date.now() / 1000) + 5
    )
      throw Error("Invalid subject");
    return payload.sub;
  } catch (error) {
    if (
      error.code === "ERR_JWKS_TIMEOUT" ||
      error instanceof TypeError ||
      (error.code === "ERR_JOSE_GENERIC" && error.message.includes("200 OK"))
    )
      throw new ApiError(
        503,
        "Cannot reach Privy verification service. Please retry.",
      );
    throw new ApiError(401, "Invalid or expired session");
  }
}
