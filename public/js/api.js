// Thin wrapper around fetch for the PFB JSON API.

export class ApiError extends Error {
  constructor(status, message, fields = {}) {
    super(message);
    this.status = status;
    this.fields = fields;
  }
}

const NOT_PFB_SERVER = 'This page is not running on the PFB server, so log in and saving do not work. '
  + 'Open a terminal in the CSE412 folder, run "python server.py", then open http://127.0.0.1:8765';

async function send(method, path, { json, body, contentType } = {}) {
  const headers = {};
  if (method !== 'GET') headers['X-PFB-Request'] = '1';
  if (json !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(json);
  } else if (contentType) {
    headers['Content-Type'] = contentType;
  }
  let response;
  try {
    response = await fetch(path, { method, headers, body, credentials: 'same-origin' });
  } catch {
    throw new ApiError(0, 'Could not reach the server. Make sure "python server.py" is running.');
  }
  // A static file server (for example VS Code Live Server) answers /api/... with
  // HTML or 404/405 instead of JSON. Say how to start the real server.
  if (!(response.headers.get('Content-Type') || '').includes('application/json')) {
    throw new ApiError(response.status, NOT_PFB_SERVER);
  }
  let data = {};
  try {
    data = await response.json();
  } catch {
    // A broken JSON body falls through to the generic message below.
  }
  if (!response.ok) {
    throw new ApiError(response.status, data.error || `Request failed (${response.status}).`, data.fields || {});
  }
  return data;
}

export const api = {
  get: path => send('GET', path),
  post: (path, json = {}) => send('POST', path, { json }),
  put: (path, json = {}) => send('PUT', path, { json }),
  del: path => send('DELETE', path),
  upload: (requestId, documentType, file) => send(
    'POST',
    `/api/verification-requests/${requestId}/documents?type=${encodeURIComponent(documentType)}&name=${encodeURIComponent(file.name)}`,
    { body: file, contentType: file.type || 'application/octet-stream' },
  ),
};
