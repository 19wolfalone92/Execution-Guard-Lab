import compiled from "./kernel.wasm";
import image from "./stdlib.zip";
import { kernel } from "./kernel.js";
import { createWorker } from "./handler.js";

export default createWorker(kernel(compiled, image));
