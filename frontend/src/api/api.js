// Thin wrapper around the KYC relay server REST API.
// Base URL can be overridden with VITE_API_BASE_URL at build time.
const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080';

async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    throw new Error(data?.error || `Request failed: ${res.status}`);
  }
  return data;
}

export const api = {
  login: (username, password) =>
    request('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  getClients: () => request('/api/clients'),
  getClient: (id) => request(`/api/clients/${id}`),
  getCases: (status, assignedOfficerId, limit, offset) => {
    const params = new URLSearchParams();
    if (status) {
      // status may be a single string or an array of statuses (OR'd together)
      const statusValue = Array.isArray(status) ? status.join(',') : status;
      if (statusValue) params.set('status', statusValue);
    }
    if (assignedOfficerId != null) params.set('assigned_officer_id', assignedOfficerId);
    if (limit != null) params.set('limit', limit);
    if (offset != null) params.set('offset', offset);
    const qs = params.toString();
    const url = `/api/onboarding/cases${qs ? `?${qs}` : ''}`;
    console.log('Fetching:', url);
    return request(url).then((response) => {
      console.log('Raw response:', response);
      // If pagination parameters were provided, return the full paginated response
      if (limit != null && offset != null) {
        // Should be in format: {total, offset, limit, cases: [...]}
        if (response && response.cases) {
          return response;
        }
        // If response is an array (old format), wrap it
        if (Array.isArray(response)) {
          return {
            total: response.length,
            offset: offset,
            limit: limit,
            cases: response
          };
        }
        // If we get here, response is unexpected
        console.warn('Unexpected pagination response format:', response);
        return {
          total: 0,
          offset: offset,
          limit: limit,
          cases: []
        };
      }
      // For backward compatibility: if no pagination params, return just the cases array
      // (or the cases array from the paginated response if it's in the new format)
      if (response && response.cases && Array.isArray(response.cases)) {
        return response.cases;
      }
      return response;
    });
  },
  getCase: (id) => request(`/api/onboarding/cases/${id}`),
  updateCaseStatus: (id, case_status) =>
    request(`/api/onboarding/cases/${id}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ case_status }),
    }),
  verifyDocument: (caseId, docId) =>
    request(`/api/onboarding/cases/${caseId}/documents/${docId}/verify`, { method: 'PATCH' }),
  getOfficers: () => request('/api/officers'),
  assignOfficer: (caseId, officerId) =>
    request(`/api/onboarding/cases/${caseId}/officer`, {
      method: 'PATCH',
      body: JSON.stringify({ officer_id: officerId }),
    }),
  updateRiskClassification: (caseId, riskLevel, rationale, officerId) =>
    request(`/api/onboarding/cases/${caseId}/risk-classification`, {
      method: 'PATCH',
      body: JSON.stringify({ risk_level: riskLevel, rationale, officer_id: officerId }),
    }),
      getDocumentTypes: () => request('/api/document-types'),
  submitDocument: (caseId, docTypeId) =>
    request(`/api/onboarding/cases/${caseId}/documents`, {
      method: 'POST',
      body: JSON.stringify({ doc_type_id: docTypeId }),
    }),
  openCase: (payload) =>
    request('/api/onboarding/cases/open', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
};
