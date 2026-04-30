// API Helper Functions

function isLockableButton(element) {
    return element instanceof HTMLButtonElement;
}

function getButtonLockState(button) {
    return button?.dataset?.buttonLockInFlight === 'true';
}

function getSubmitButtonFromEvent(event) {
    if (isLockableButton(event?.submitter)) {
        return event.submitter;
    }
    return event?.target?.querySelector('button[type="submit"], button:not([type])') || null;
}

async function withButtonLock(button, callback) {
    if (typeof callback !== 'function') {
        return undefined;
    }
    if (!isLockableButton(button)) {
        return callback();
    }
    if (button.disabled || getButtonLockState(button)) {
        return undefined;
    }

    const wasDisabled = button.disabled;
    button.dataset.buttonLockInFlight = 'true';
    button.disabled = true;

    try {
        return await callback();
    } finally {
        if (button.isConnected) {
            button.disabled = wasDisabled;
            delete button.dataset.buttonLockInFlight;
        }
    }
}

/**
 * Core API call function
 */
async function apiCall(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (typeof getBrowserTimeZone === 'function') {
        const browserTimeZone = getBrowserTimeZone();
        if (browserTimeZone && !headers.has('X-Client-Timezone')) {
            headers.set('X-Client-Timezone', browserTimeZone);
        }
    }

    const requestOptions = { ...options };
    delete requestOptions.headers;

    const response = await fetch(path, {
        credentials: 'same-origin',
        ...requestOptions,
        headers
    });

    if (!response.ok) {
        let errorBody = null;
        try {
            errorBody = await response.json();
        } catch (_error) {
            errorBody = await response.text();
        }

        const errorMessage = typeof errorBody === 'string'
            ? errorBody
            : errorBody?.error || errorBody?.message || 'Unknown error';
        const error = new Error(errorMessage);
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
 * PUT request
 */
async function apiPut(path, data) {
    return apiCall(path, {
        method: 'PUT',
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
