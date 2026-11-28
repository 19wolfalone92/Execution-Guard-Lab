import { File, OpenFile, PreopenDirectory, WASI } from "@bjorn3/browser_wasi_shim";

const encoder = new TextEncoder();
const decoder = new TextDecoder("utf-8", { fatal: true });

export function kernel(compiled, image) {
  let runtime;
  const closed = () => new OpenFile(new File([], { readonly: true }));

  function initialize() {
    const files = new Map([["lib.zip", new File(image, { readonly: true })]]);
    const wasi = new WASI(["lab"], [], [closed(), closed(), closed(), new PreopenDirectory("/lab", files)], { debug: false });
    const instance = new WebAssembly.Instance(compiled, { wasi_snapshot_preview1: wasi.wasiImport });
    wasi.initialize(instance);
    const status = instance.exports.lab_init();
    if (status !== 0) {
      throw new Error("kernel_init_" + status);
    }
    return instance.exports;
  }

  return {
    call(raw) {
      try {
        runtime ??= initialize();
        const bytes = encoder.encode(raw);
        const input = runtime.malloc(bytes.length);
        if (!input) throw new Error("kernel_memory_limit");
        try {
          new Uint8Array(runtime.memory.buffer, input, bytes.length).set(bytes);
          const ptr = runtime.lab_call(input, bytes.length);
          const len = runtime.lab_length();
          if (!ptr || len < 1 || len > 131073) throw new Error("invalid_kernel_response");
          return decoder.decode(new Uint8Array(runtime.memory.buffer, ptr, len));
        } finally {
          runtime.lab_release();
          runtime.free(input);
        }
      } catch (error) {
        runtime = undefined;
        throw error;
      }
    },
    memoryBytes() {
      return runtime?.memory.buffer.byteLength ?? 0;
    },
  };
}
