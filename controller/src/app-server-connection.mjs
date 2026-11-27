import { createHash, randomBytes } from 'node:crypto';
import { lstat, realpath } from 'node:fs/promises';
import { request } from 'node:http';
import { dirname } from 'node:path';
import { TextDecoder } from 'node:util';

const WEBSOCKET_GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11';
const MAX_MESSAGE_BYTES = 16 * 1024 * 1024;
const REQUEST_TIMEOUT_MS = 20_000;
const decoder = new TextDecoder('utf-8', { fatal: true });

function connectionError(code = 'APP_SERVER_CONNECTION_LOST') {
  return Object.assign(new Error(code), { code, reconnectable: true });
}

async function upgrade(socketPath) {
  const [socketInfo, parentInfo] = await Promise.all([lstat(socketPath), lstat(dirname(socketPath))]);
  if (!socketInfo.isSocket() || socketInfo.mode & 0o007 ||
      !parentInfo.isDirectory() || parentInfo.mode & 0o022 ||
      (parentInfo.uid !== 0 && parentInfo.uid !== socketInfo.uid) ||
      await realpath(socketPath) !== socketPath) {
    throw Object.assign(new Error('APP_SERVER_SOCKET_INVALID'), { code: 'APP_SERVER_SOCKET_INVALID' });
  }
  const key = randomBytes(16).toString('base64');
  const accept = createHash('sha1').update(key + WEBSOCKET_GUID).digest('base64');
  return new Promise((resolve, reject) => {
    const req = request({
      socketPath, path: '/rpc', agent: false, maxHeaderSize: 8192,
      headers: {
        Host: 'localhost', Connection: 'Upgrade', Upgrade: 'websocket',
        'Sec-WebSocket-Version': '13', 'Sec-WebSocket-Key': key
      }
    });
    const deadline = setTimeout(() => req.destroy(connectionError('APP_SERVER_CONNECT_TIMEOUT')), REQUEST_TIMEOUT_MS);
    req.on('upgrade', (response, socket, head) => {
      clearTimeout(deadline);
      if (response.statusCode === 101 && response.headers.upgrade?.toLowerCase() === 'websocket' &&
          response.headers.connection?.toLowerCase().split(/\s*,\s*/).includes('upgrade') &&
          response.headers['sec-websocket-accept'] === accept &&
          !response.headers['sec-websocket-extensions'] && !response.headers['sec-websocket-protocol']) {
        resolve({ socket, head });
      } else {
        socket.destroy();
        reject(connectionError('APP_SERVER_UPGRADE_INVALID'));
      }
    });
    req.on('response', response => {
      clearTimeout(deadline);
      response.destroy();
      reject(connectionError('APP_SERVER_UPGRADE_INVALID'));
    });
    req.on('error', () => {
      clearTimeout(deadline);
      reject(connectionError('APP_SERVER_CONNECT_FAILED'));
    });
    req.end();
  });
}

function clientFrame(opcode, content) {
  const payload = Buffer.isBuffer(content) ? content : Buffer.from(content, 'utf8');
  if (payload.length > MAX_MESSAGE_BYTES) throw connectionError('APP_SERVER_MESSAGE_TOO_LARGE');
  const sizeBytes = payload.length < 126 ? 0 : payload.length <= 0xffff ? 2 : 8;
  const maskOffset = 2 + sizeBytes;
  const offset = maskOffset + 4;
  const frame = Buffer.allocUnsafe(offset + payload.length);
  frame[0] = 0x80 | opcode;
  frame[1] = 0x80 | (sizeBytes === 0 ? payload.length : sizeBytes === 2 ? 126 : 127);
  if (sizeBytes === 2) frame.writeUInt16BE(payload.length, 2);
  if (sizeBytes === 8) frame.writeBigUInt64BE(BigInt(payload.length), 2);
  const mask = randomBytes(4);
  mask.copy(frame, maskOffset);
  for (let index = 0; index < payload.length; index++) frame[offset + index] = payload[index] ^ mask[index % 4];
  return frame;
}

// Unix control sockets speak uncompressed WebSocket JSON-RPC. Use the system
// HTTP client for the upgrade and retain only one bounded message and request.
function jsonRpc(socket, head, onNotification, ownsRequest) {
  let buffer = Buffer.alloc(4096);
  let bytes = 0;
  let messageBytes = 0;
  let fragments = [];
  let requestId = 0;
  let pending;
  let closed = false;

  const fail = error => {
    if (closed) return;
    closed = true;
    if (pending) pending.finish(error);
    socket.destroy();
  };
  const write = (opcode, payload) => {
    if (closed || socket.destroyed) throw connectionError();
    socket.write(clientFrame(opcode, payload));
  };
  const send = value => write(1, JSON.stringify(value));
  const receive = message => {
    const value = JSON.parse(decoder.decode(message));
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw connectionError('APP_SERVER_PROTOCOL_INVALID');
    if (typeof value.method === 'string') {
      if (Object.hasOwn(value, 'id')) {
        if (ownsRequest(value.params)) send({ id: value.id, error: { code: -32601, message: 'Relay does not provide interactive tools or approvals.' } });
      } else {
        onNotification(value.method, value.params);
      }
    } else if (pending && pending.id === value.id) {
      if (value.error && typeof value.error === 'object') {
        // A native error can include provider and workspace data. Emit only the
        // method, which is selected by Relay, and the numeric protocol code.
        const code = Number.isSafeInteger(value.error.code) ? value.error.code : undefined;
        pending.finish(Object.assign(new Error(`App Server refused ${pending.method}`), { code: 'APP_SERVER_REQUEST_REJECTED', protocolCode: code }));
      } else if (Object.hasOwn(value, 'result')) {
        pending.finish(null, value.result);
      } else {
        throw connectionError('APP_SERVER_PROTOCOL_INVALID');
      }
    }
  };
  const handleFrame = (header, payload) => {
    const opcode = header & 0x0f;
    const final = (header & 0x80) !== 0;
    if (opcode === 8) {
      fail(connectionError());
    } else if (opcode === 9) {
      write(10, payload);
    } else if (opcode !== 10) {
      if (opcode === 1 && !fragments.length && final) {
        receive(payload);
        return;
      }
      if ((opcode !== 1 && opcode !== 0) || (opcode === 0) !== (fragments.length !== 0)) {
        throw connectionError('APP_SERVER_PROTOCOL_INVALID');
      }
      // Store bytes as they arrive without allowing arbitrarily many empty
      // continuation frames to grow per-message state.
      messageBytes += payload.length;
      if (messageBytes > MAX_MESSAGE_BYTES || fragments.length >= 1024) throw connectionError('APP_SERVER_MESSAGE_TOO_LARGE');
      fragments.push(Buffer.from(payload));
      if (final) {
        receive(Buffer.concat(fragments, messageBytes));
        fragments = [];
        messageBytes = 0;
      }
    }
  };
  const consume = chunk => {
    if (closed) return;
    try {
      const total = bytes + chunk.length;
      if (total > MAX_MESSAGE_BYTES + 128 * 1024) throw connectionError('APP_SERVER_MESSAGE_TOO_LARGE');
      if (total > buffer.length) {
        const next = Buffer.allocUnsafe(Math.max(total, Math.min(MAX_MESSAGE_BYTES + 128 * 1024, buffer.length * 2)));
        buffer.copy(next, 0, 0, bytes);
        buffer = next;
      }
      chunk.copy(buffer, bytes);
      bytes = total;
      let position = 0;
      while (!closed && bytes - position >= 2) {
        const header = buffer[position];
        const size = buffer[position + 1];
        const opcode = header & 0x0f;
        if (header & 0x70 || size & 0x80 || (opcode >= 8 && (!(header & 0x80) || size > 125))) throw connectionError('APP_SERVER_PROTOCOL_INVALID');
        const sizeBytes = size < 126 ? 0 : size === 126 ? 2 : 8;
        const offset = position + 2 + sizeBytes;
        if (bytes < offset) break;
        const length = sizeBytes === 0 ? size : sizeBytes === 2 ? buffer.readUInt16BE(position + 2) : Number(buffer.readBigUInt64BE(position + 2));
        if (length > MAX_MESSAGE_BYTES) throw connectionError('APP_SERVER_MESSAGE_TOO_LARGE');
        if (bytes - offset < length) break;
        handleFrame(header, buffer.subarray(offset, offset + length));
        position = offset + length;
      }
      bytes -= position;
      if (bytes) buffer.copy(buffer, 0, position, position + bytes);
    } catch (error) {
      fail(error.reconnectable ? error : connectionError('APP_SERVER_PROTOCOL_INVALID'));
    }
  };
  socket.on('error', () => fail(connectionError()));
  socket.on('end', () => fail(connectionError()));
  socket.on('close', () => fail(connectionError()));
  socket.on('data', consume);
  if (head.length) consume(head);
  return {
    async request(method, params) {
      if (closed) throw connectionError();
      if (pending) throw new Error('APP_SERVER_CONCURRENT_REQUEST_INVALID');
      return new Promise((resolve, reject) => {
        const id = ++requestId;
        const timer = setTimeout(() => fail(connectionError('APP_SERVER_REQUEST_TIMEOUT')), REQUEST_TIMEOUT_MS);
        pending = {
          id, method,
          finish(error, value) {
            clearTimeout(timer);
            pending = undefined;
            if (error) reject(error);
            else resolve(value);
          }
        };
        try { send({ id, method, params }); }
        catch (error) { fail(error); }
      });
    },
    notify(method) { send({ method }); },
    close() { fail(connectionError()); }
  };
}

export async function connectAppServer(socketPath, { onNotification, ownsRequest }) {
  let upgraded;
  try { upgraded = await upgrade(socketPath); }
  catch (error) {
    if (error.code?.startsWith('APP_SERVER_')) throw error;
    throw connectionError('APP_SERVER_CONNECT_FAILED');
  }
  const connection = jsonRpc(upgraded.socket, upgraded.head, onNotification, ownsRequest);
  try {
    const initialized = await connection.request('initialize', {
      clientInfo: { name: 'codex_relay', title: 'Codex Relay', version: '1.0.0' },
      capabilities: { experimentalApi: true, requestAttestation: false }
    });
    if (initialized?.platformOs !== 'linux' || typeof initialized.codexHome !== 'string' || !initialized.codexHome.startsWith('/')) {
      throw Object.assign(new Error('APP_SERVER_PLATFORM_UNSUPPORTED'), { code: 'APP_SERVER_PLATFORM_UNSUPPORTED' });
    }
    connection.notify('initialized');
    return { ...connection, codexHome: initialized.codexHome };
  } catch (error) {
    connection.close();
    throw error;
  }
}
