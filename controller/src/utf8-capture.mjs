import { StringDecoder } from "node:string_decoder";

export function createBoundedUtf8Capture(limit) {
  if (!Number.isInteger(limit) || limit < 0) throw new Error("A non-negative byte limit is required");
  const decoder = new StringDecoder("utf8");
  const textParts = [];
  let totalBytes = 0;
  let capturedBytes = 0;
  let finished = false;
  return {
    push(chunk) {
      if (finished) return;
      const bytes = Buffer.isBuffer(chunk) || chunk instanceof Uint8Array ? Buffer.from(chunk) : Buffer.from(String(chunk), "utf8");
      totalBytes += bytes.length;
      const remaining = Math.max(0, limit - capturedBytes);
      if (remaining === 0) return;
      const captured = bytes.subarray(0, remaining);
      capturedBytes += captured.length;
      textParts.push(decoder.write(captured));
    },
    finish() {
      if (!finished) {
        finished = true;
        // Do not flush an incomplete trailing code point after overflow: the
        // bounded stream must not gain a replacement character at its edge.
        if (totalBytes <= limit) textParts.push(decoder.end());
      }
      return { value: textParts.join(""), total: totalBytes, captured: capturedBytes, truncated: totalBytes > limit };
    }
  };
}
