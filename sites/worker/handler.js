import catalog from "./catalog.json" with { type: "json" };
import { acquire } from "./admission.js";
import { parseRequest } from "./envelope.js";

const version = "1.0.3";
const protocol = "2026-07-28";
const maxBody = 128 * 1024;
const maxDiagnosticBody = 32 * 1024;
const maxText = 4096;
const maxItems = 128;
const maxNumber = 1_000_000;
const requestIdSchema = { type: "string", format: "uuid" };

function objectSchema(properties) {
  return { type: "object", properties, required: Object.keys(properties), additionalProperties: false };
}

const toolSchemas = [
  {
    name: "lab_health",
    description: "Check the version and status of Execution Guard Lab.",
    inputSchema: objectSchema({}),
    outputSchema: objectSchema({
      version: { type: "string" }, status: { type: "string", const: "ok" }, request_id: requestIdSchema
    })
  },
  {
    name: "lab_sha256",
    description: "Compute SHA-256 of UTF-8 test text, up to 4096 Unicode code points.",
    inputSchema: objectSchema({ text: { type: "string", maxLength: maxText } }),
    outputSchema: objectSchema({
      sha256: { type: "string", pattern: "^[a-f0-9]{64}$" }, request_id: requestIdSchema
    })
  },
  {
    name: "lab_numeric_verify",
    description: "Return an exact sum, sum of squares and count for up to 128 integers from -1000000 to 1000000.",
    inputSchema: objectSchema({
      values: {
        type: "array", minItems: 1, maxItems,
        items: { type: "integer", minimum: -maxNumber, maximum: maxNumber }
      }
    }),
    outputSchema: objectSchema({
      count: { type: "integer" }, sum: { type: "integer" },
      sum_of_squares: { type: "integer" }, request_id: requestIdSchema
    })
  }
].map((schema) => ({
  ...schema, annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false }
}));

const names = new Set(catalog.map(spec => spec.name));
for (const spec of catalog) {
  spec.outputSchema.properties.request_id = requestIdSchema;
  spec.outputSchema.required.push("request_id");
  if (spec.name === "math_calculate") {
    spec.outputSchema.properties.exact_integer = { type: "string", pattern: "^-?[0-9]+$" };
  }
  toolSchemas.push(spec);
}
const knownTools = new Set(toolSchemas.map(spec => spec.name));
if (knownTools.size !== 26 || toolSchemas.length !== knownTools.size) throw new Error("unexpected_catalog");

const jsonHeaders = { "cache-control": "no-store", "x-content-type-options": "nosniff" };

function rpc(id, result) {
  return Response.json({ jsonrpc: "2.0", id, result }, { headers: jsonHeaders });
}

function rpcError(id, code, message, status = 200) {
  return Response.json({ jsonrpc: "2.0", id, error: { code, message } }, { status, headers: jsonHeaders });
}

function toolError(id, message, requestId) {
  return rpc(id, { isError: true, content: [{ type: "text", text: message + " Request ID " + requestId }] });
}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function onlyKey(args, key) {
  return Object.hasOwn(args, key) && Object.keys(args).length === 1;
}

async function readBody(request) {
  if (Number(request.headers.get("content-length")) > maxBody) return null;
  const reader = request.body?.getReader();
  if (!reader) return { text:"", size:0 };
  const decoder = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true });
  let body = "";
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) return { text: body + decoder.decode(), size };
      size += value.byteLength;
      if (size > maxBody) {
        await reader.cancel().catch(() => {});
        return null;
      }
      body += decoder.decode(value, { stream: true });
    }
  } finally {
    reader.releaseLock();
  }
}

async function diagnostic(id, params, request_id) {
  const args = params?.arguments === undefined ? {} : params.arguments;
  const invalid = () => toolError(id, "Invalid tool arguments.", request_id);
  if (!isObject(args)) return invalid();

  let output;
  switch (params?.name) {
    case "lab_health":
      if (Object.keys(args).length !== 0) return invalid();
      output = { version, status: "ok", request_id };
      break;
    case "lab_sha256": {
      if (!onlyKey(args, "text") || typeof args.text !== "string" || [...args.text].length > maxText) return invalid();
      const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(args.text));
      output = { sha256: Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join(""), request_id };
      break;
    }
    case "lab_numeric_verify": {
      const values = args.values;
      if (!onlyKey(args, "values") || !Array.isArray(values) || values.length < 1 || values.length > maxItems) return invalid();
      let sum = 0;
      let sum_of_squares = 0;
      for (const value of values) {
        if (!Number.isInteger(value) || Math.abs(value) > maxNumber) return invalid();
        sum += value;
        sum_of_squares += value * value;
      }
      output = { count: values.length, sum, sum_of_squares, request_id };
      break;
    }
    default:
      return rpcError(id, -32602, "Unknown tool");
  }
  return rpc(id, { content: [{ type: "text", text: JSON.stringify(output) }], structuredContent: output });
}

const encoder = new TextEncoder();
const home = '<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Execution Guard Lab</title><main><h1>Execution Guard Lab</h1><p>Версия 1.0.3 · 23 вычислительных и 3 диагностических инструмента MCP</p></main></html>';

function compute(kernel, raw, id, requestId) {
  const reply = kernel.call(raw, requestId);
  if (reply.startsWith("-")) return toolError(id, reply.slice(1), requestId);
  if (!reply.startsWith("+{") || !reply.endsWith("}")) throw new Error("invalid_kernel_output");
  // Preserve the exact numeric lexemes in both wire results and the text block.
  const payload = reply.slice(1, -1) + ',"request_id":' + JSON.stringify(requestId) + '}';
  const content = JSON.stringify([{ type: "text", text: payload }]);
  const serialized = '{"jsonrpc":"2.0","id":' + JSON.stringify(id)
    + ',"result":{"isError":false,"content":' + content + ',"structuredContent":' + payload + '}}';
  if (encoder.encode(serialized).length > 384 * 1024) return toolError(id, "result_too_large", requestId);
  return new Response(serialized, { headers: { ...jsonHeaders, "content-type": "application/json; charset=utf-8" } });
}

function admissionError(id, status, requestId) {
  return Response.json({
    jsonrpc: "2.0", id, error: { code: -32002, message: "Admission unavailable", data: { request_id: requestId } },
  }, { status, headers: { ...jsonHeaders, "retry-after": "60" } });
}

export function createWorker(kernel) {
  let pending = 0;

  async function call(request, env, ctx, payload, id, params) {
    const requestId = crypto.randomUUID();
    const failed = () => rpcError(id, -32603, "Computation failed. Request ID " + requestId);
    const subject = request.headers.get("oai-authenticated-user-id")?.trim();
    if (!subject || subject.length > 512) return rpcError(id, -32001, "Site authentication required", 401);
    if (!isObject(params) || typeof params.name !== "string" || !knownTools.has(params.name)) {
      return rpcError(id, -32602, "Unknown tool");
    }
    if (pending >= 4) return admissionError(id, 429, requestId);
    pending++;
    try {
      const slot = await acquire(env.DB, requestId, request.signal);
      if (slot.status !== 200) return admissionError(id, slot.status, requestId);
      let result;
      try {
        if (names.has(params.name)) {
          result = compute(kernel, payload.text, id, requestId);
        } else if (payload.size > maxDiagnosticBody) {
          result = rpcError(id, -32600, "Diagnostic request too large", 413);
        } else {
          result = await diagnostic(id, params, requestId);
        }
      } catch {
        result = failed();
      }
      try {
        const completing = slot.release();
        ctx?.waitUntil?.(completing);
        if (await completing) return result;
      } catch {
        // A lost D1 completion keeps its slot closed.
      }
      return admissionError(id, 503, requestId);
    } finally {
      pending--;
    }
  }

  return {
    async fetch(request, env = {}, ctx) {
      const { pathname } = new URL(request.url);
      if (request.method === "GET" && pathname === "/") {
        return new Response(home, { headers: { ...jsonHeaders, "content-type": "text/html; charset=utf-8",
          "content-security-policy": "default-src 'none'; frame-ancestors 'self' https://chatgpt.com; base-uri 'none'" } });
      }
      if (request.method === "GET" && pathname === "/favicon.ico") {
        return new Response(null, { status: 204, headers: jsonHeaders });
      }
      if (pathname !== "/mcp") return new Response("Not found", { status: 404, headers: jsonHeaders });
      if (request.method !== "POST") {
        return new Response("Method not allowed", { status: 405, headers: { ...jsonHeaders, allow: "POST" } });
      }
      if (request.headers.get("content-type")?.split(";")[0].trim().toLowerCase() !== "application/json") {
        return rpcError(null, -32600, "Expected application/json", 415);
      }
      let payload, message;
      try {
        payload = await readBody(request);
        if (payload === null) return rpcError(null, -32600, "Request exceeds 131072 bytes", 413);
        message = parseRequest(payload.text);
      } catch {
        return rpcError(null, -32700, "Parse error", 400);
      }
      if (!isObject(message) || message.jsonrpc !== "2.0" || typeof message.method !== "string") {
        return rpcError(null, -32600, "Invalid request", 400);
      }
      const { id, method, params } = message;
      if (id === undefined && method.startsWith("notifications/")) {
        return new Response(null, { status: 202, headers: jsonHeaders });
      }
      if (!(typeof id === "string" && id.length <= 256) && !Number.isSafeInteger(id)) {
        return rpcError(null, -32600, "Invalid request ID", 400);
      }
      switch (method) {
        case "server/discover":
          return rpc(id, { supportedVersions: [protocol], capabilities: { tools: {} },
            serverInfo: { name: "Execution Guard Lab", version } });
        case "tools/list":
          return rpc(id, { tools: toolSchemas });
        case "tools/call":
          return call(request, env, ctx, payload, id, params);
        default:
          return rpcError(id, -32601, "Method not found");
      }
    }
  };
}
