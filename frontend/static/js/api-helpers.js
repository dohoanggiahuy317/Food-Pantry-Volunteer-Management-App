// API Helper Functions

/**
 * Core API call function
 */
async function apiCall(path, options = {}) {
    const response = await fetch(path, {
        credentials: 'same-origin',
        ...options
    });

    if (!response.ok) {
        let errorBody = null;
        try {
            errorBody = await response.json();
        } catch (_error) {
            errorBody = await response.text();
        }

        const error = new Error(
            typeof errorBody === 'string'
                ? `API Error: ${response.status} - ${errorBody}`
                : `API Error: ${response.status} - ${errorBody?.error || 'Unknown error'}`
        );
        error.status = response.status;
        error.body = errorBody;
        throw error;
    }

    if (response.status === 204) {
        return null;
    }

    return response.json();
}

/**
 * GET request
 */
async function apiGet(path) {
    return apiCall(path, { method: 'GET' });
}

/**
 * POST request
 */
async function apiPost(path, data) {
    return apiCall(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
}

/**
 * PATCH request
 */
async function apiPatch(path, data) {
    return apiCall(path, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
}

/**
 * DELETE request
 */
async function apiDelete(path) {
    return apiCall(path, { method: 'DELETE' });
}
