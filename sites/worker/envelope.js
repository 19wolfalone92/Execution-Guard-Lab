// The JSON tokenizer enforces key uniqueness and bounds before host parsing.
function readString(source, start) {
  for (let i = start + 1; i < source.length; i++) {
    if (source[i] === "\\") i++;
    else if (source[i] === '"') return i + 1;
  }
  throw new Error("unterminated_string");
}

export function parseRequest(source) {
  const stack = [];
  let index = 0;
  while (index < source.length) {
    const ch = source[index++];
    if (ch === "{" || ch === "[") {
      if (stack.length >= 21) throw new Error("depth_limit");
      stack.push(ch === "{" ? new Set() : null);
    } else if (ch === "}" || ch === "]") {
      stack.pop();
    } else if (ch === '"') {
      const start = index - 1;
      index = readString(source, start);
      const val = JSON.parse(source.slice(start, index));
      if (/[\uD800-\uDFFF]/u.test(val)) throw new Error("invalid_unicode");
      let next = index;
      while (next < source.length && /[ \r\t\n]/.test(source[next])) next++;
      if (source[next] === ":") {
        const keys = stack.at(-1);
        if (!keys || keys.has(val)) throw new Error("duplicate_key");
        keys.add(val);
      }
    }
  }
  return JSON.parse(source, (_, value) => {
    if (typeof value === "number" && !Number.isFinite(value)) throw new Error("nonfinite_number");
    return value;
  });
}
