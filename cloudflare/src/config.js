export const UNIT = 1_000_000;
export const SUPPLY = 1_000_000_000;
export const SCENARIOS = {
  balanced: {
    label: "Balanced",
    description: "Mixed sentiment, patient investors and speculative traders.",
    drift: 0,
    activity: 1,
    appetite: 1,
  },
  bull: {
    label: "Bull run",
    description: "Stronger buying interest, with profit taking and pullbacks.",
    drift: 0.0005,
    activity: 1.25,
    appetite: 1.25,
  },
  bear: {
    label: "Bear market",
    description: "Lower risk appetite, defensive exits and bargain hunters.",
    drift: -0.0005,
    activity: 1.1,
    appetite: 0.55,
  },
  mania: {
    label: "Meme mania",
    description: "Fast turnover, impulsive entries and frequent reversals.",
    drift: 0,
    activity: 1.7,
    appetite: 1.15,
  },
};
// Same policy limits as personalities.py. Money stays in PostgreSQL integers.
export const POLICIES = {
  patient_value: [
    "Patient value investor",
    "value",
    0.12,
    0.005,
    0.025,
    200,
    0.1,
    5,
    15,
    true,
  ],
  careful_trend: [
    "Disciplined trend trader",
    "momentum",
    0.15,
    0.01,
    0.04,
    400,
    0.18,
    4,
    10,
    true,
  ],
  contrarian: [
    "Cautious contrarian",
    "value",
    0.18,
    0.01,
    0.04,
    350,
    0.12,
    5,
    14,
    true,
  ],
  fomo: [
    "FOMO chaser",
    "momentum",
    0.45,
    0.05,
    0.18,
    10000,
    0.24,
    4,
    12,
    false,
  ],
  gambler: [
    "Impulsive gambler",
    "noise",
    0.55,
    0.06,
    0.25,
    18000,
    0.18,
    5,
    18,
    false,
  ],
  reckless_whale: [
    "Reckless whale",
    "noise",
    0.65,
    0.08,
    0.3,
    25000,
    0.08,
    15,
    40,
    false,
  ],
  retail_noise: [
    "Casual small trader",
    "noise",
    0.2,
    0.01,
    0.06,
    1500,
    0.22,
    2,
    7,
    false,
  ],
};
export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}
export function worldSchema(env, world) {
  const prefix = env.NORX_PG_SCHEMA_PREFIX || "norx_";
  if (!/^[a-z][a-z0-9_]{0,35}$/.test(prefix))
    throw new Error("Invalid schema prefix");
  if (!Object.hasOwn(SCENARIOS, world))
    throw new ApiError(400, "Unknown economy");
  return prefix + world;
}
