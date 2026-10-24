import test from "node:test";
import assert from "node:assert/strict";
import { generateKeyPair, exportJWK, SignJWT } from "jose";
import { identity } from "../src/auth.js";

test("Privy verifies ES256, issuer, app, expiry and subject; no local bypass", async (t) => {
  const { privateKey, publicKey } = await generateKeyPair("ES256");
  const jwk = { ...(await exportJWK(publicKey)), kid: "test", alg: "ES256" };
  t.mock.method(globalThis, "fetch", async () =>
    Response.json({ keys: [jwk] }),
  );
  const env = { PRIVY_APP_ID: "test-auth-app" };
  const token = async (overrides = {}) =>
    new SignJWT({
      iss: "privy.io",
      aud: env.PRIVY_APP_ID,
      sub: "did:privy:email-player",
      iat: Math.floor(Date.now() / 1000),
      exp: Math.floor(Date.now() / 1000) + 60,
      ...overrides,
    })
      .setProtectedHeader({ alg: "ES256", kid: "test" })
      .sign(privateKey);
  const request = (token) =>
    new Request("https://norx.test/api/me", {
      headers: { Authorization: "Bearer " + token },
    });
  assert.equal(
    await identity(request(await token()), env),
    "did:privy:email-player",
  );
  for (const overrides of [
    { aud: "other-app" },
    { iss: "attacker" },
    { sub: "agent-whale-03" },
    { exp: 1 },
    { iat: undefined },
    { iat: Math.floor(Date.now() / 1000) + 3600 },
  ]) {
    await assert.rejects(
      identity(request(await token(overrides)), env),
      (e) => e.status === 401,
    );
  }
  await assert.rejects(
    identity(request("local-demo"), env),
    (e) => e.status === 401,
  );
  await assert.rejects(identity(request(""), {}), (e) => e.status === 503);
});
