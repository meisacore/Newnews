// Inspect driver errors, but emit only fixed categories and hints. Raw messages,
// stacks, SQL, connection strings and query parameters never leave this module.
export function databaseFailure(error) {
  const chain = [];
  let current = error;
  for (let i = 0; current && i < 4; i++, current = current.cause)
    chain.push(current);
  if (Array.isArray(error?.errors)) chain.push(...error.errors.slice(0, 4));
  const message = chain
    .map((e) => (typeof e?.message === "string" ? e.message : ""))
    .join(" ")
    .toLowerCase();
  const codes = chain.map((e) => String(e?.code || ""));
  let category = "unknown",
    hint = "The market service is unavailable. Please retry shortly.";
  if (
    codes.some((c) => ["28P01", "28000"].includes(c)) ||
    /authentication failed|password|tenant or user not found|sasl|scram/.test(
      message,
    )
  ) {
    category = "database_authentication";
    hint =
      "Database authentication failed. Check the Worker's DATABASE_URL secret and Supabase session-pooler credentials.";
  } else if (codes.some((c) => ["42P01", "3F000", "42883"].includes(c))) {
    category = "database_setup";
    hint =
      "Cloudflare database tables or functions are missing. Check the schema prefix and run cloudflare/prepare.py --activate against the same database.";
  } else if (codes.includes("42501")) {
    category = "database_permissions";
    hint = "The database connection lacks permission for the NORX schemas.";
  } else if (
    codes.includes("53300") ||
    /maxclients|too many (?:clients|connections)|connection limit/.test(message)
  ) {
    category = "database_connection_limit";
    hint =
      "The database pooler has reached its connection limit. Stop duplicate backends and retry.";
  } else if (codes.includes("55P03")) {
    category = "database_lock_timeout";
    hint = "The market is finishing another update. Please retry shortly.";
  } else if (codes.includes("57014")) {
    category = "database_statement_timeout";
    hint = "The database update exceeded its time limit. Please retry shortly.";
  } else if (/timeout|timed out/.test(message) || codes.includes("ETIMEDOUT")) {
    category = "database_connection_timeout";
    hint =
      "The Worker timed out connecting to Supabase. Check the pooler connection and that the project is active.";
  } else if (
    /certificate|self.signed|ssl|tls/.test(message) ||
    codes.some((c) => /TLS|CERT|SSL/.test(c))
  ) {
    category = "database_tls";
    hint =
      "The encrypted database connection failed. Check the Supabase pooler URL and TLS settings.";
  } else if (
    codes.some((c) => ["ENOTFOUND", "EAI_AGAIN"].includes(c)) ||
    /getaddrinfo|resolve.*host/.test(message)
  ) {
    category = "database_dns";
    hint =
      "The database hostname could not be resolved. Check the Supabase session-pooler hostname.";
  } else if (codes.includes("ECONNREFUSED")) {
    category = "database_connection_refused";
    hint =
      "Supabase refused the connection. Check the pooler host, port and project status.";
  } else if (
    codes.some((c) =>
      ["ECONNRESET", "EPIPE", "57P01", "ERR_SOCKET_CLOSED"].includes(c),
    ) ||
    /connection (?:terminated|ended|closed)|socket.*closed|closed.*connection/.test(
      message,
    )
  ) {
    category = "database_connection_closed";
    hint =
      "The database connection closed unexpectedly. Check the session pooler and retry.";
  } else if (
    /not (?:yet )?implemented|not supported|unsupported|cannot connect to/.test(
      message,
    )
  ) {
    category = "database_runtime";
    hint =
      "The Worker could not open the database socket. Check the runtime configuration and database connection path.";
  } else if (/schema prefix/.test(message)) {
    category = "database_configuration";
    hint = "The Worker's NORX_PG_SCHEMA_PREFIX is invalid.";
  }
  const code = codes.find((c) => /^[A-Z0-9_]{1,40}$/.test(c)) || "none";
  const stage = /^[a-z_]{1,40}$/.test(error?.norxStage || "")
    ? error.norxStage
    : "unknown";
  return { category, stage, code, hint };
}
export function logFailure(label, error, world) {
  const { category, stage, code, hint } = databaseFailure(error);
  console.error(
    label,
    JSON.stringify({
      ...(world ? { world } : {}),
      category,
      stage,
      code,
      hint,
    }),
  );
}
