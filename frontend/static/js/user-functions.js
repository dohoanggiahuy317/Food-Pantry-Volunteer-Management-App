// User Authentication and Profile Functions

/**
 * Get current user information
 * Returns: { user_id, full_name, email, roles: [...] }
 */
async function getCurrentUser() {
    try {
        const user = await apiGet('/api/me');
        return user;
    } catch (error) {
        console.error('Failed to get current user:', error);
        throw error;
    }
}

/**
 * Check if user has a specific role
 */
function userHasRole(user, roleName) {
    if (!user || !user.roles) return false;
    // API returns roles as array of strings: ["ADMIN", "PANTRY_LEAD"]
    return user.roles.includes(roleName);
}

/**
 * Display current user information in the UI
 */
function displayCurrentUser(user, emailElementId = 'user-email', roleElementId = 'user-role') {
    const emailEl = document.getElementById(emailElementId);
    const roleEl = document.getElementById(roleElementId);
    
    if (emailEl) emailEl.textContent = user.email;
    
    if (roleEl) {
        // roles is array of strings: ["ADMIN", "PANTRY_LEAD"]
        const roleNames = user.roles.join(', ');
        roleEl.textContent = roleNames || 'No Role';
    }
}

/**
 * Get all users (admin only)
 */
async function getAllUsers(roleFilter = null, searchQuery = '') {
    try {
        const params = new URLSearchParams();
        if (roleFilter) {
            params.set('role', roleFilter);
        }
        if (searchQuery) {
            params.set('q', searchQuery);
        }
        const path = params.toString() ? `/api/users?${params.toString()}` : '/api/users';
        const users = await apiGet(path);
        return users;
    } catch (error) {
        console.error('Failed to get users:', error);
        throw error;
    }
}

/**
 * Create a new user
 */
async function createUser(userData) {
    try {
        const user = await apiPost('/api/users', userData);
        return user;
    } catch (error) {
        console.error('Failed to create user:', error);
        throw error;
    }
}

async function getUserProfile(userId) {
    try {
        return await apiGet(`/api/users/${userId}`);
    } catch (error) {
        console.error('Failed to get user profile:', error);
        throw error;
    }
}

async function updateCurrentUserProfile(profileData) {
    try {
        return await apiPatch('/api/me', profileData);
    } catch (error) {
        console.error('Failed to update current user profile:', error);
        throw error;
    }
}

async function getGoogleCalendarStatus() {
    try {
        return await apiGet('/api/google-calendar/status');
    } catch (error) {
        console.error('Failed to get Google Calendar status:', error);
        throw error;
    }
}

async function startGoogleCalendarConnect() {
    try {
        return await apiPost('/api/google-calendar/connect/start', {});
    } catch (error) {
        console.error('Failed to start Google Calendar connect:', error);
        throw error;
    }
}

async function disconnectGoogleCalendar() {
    try {
        return await apiPost('/api/google-calendar/disconnect', {});
    } catch (error) {
        console.error('Failed to disconnect Google Calendar:', error);
        throw error;
    }
}

async function prepareCurrentUserEmailChange(newEmail) {
    try {
        return await apiPost('/api/me/email-change/prepare', { new_email: newEmail });
    } catch (error) {
        console.error('Failed to prepare email change:', error);
        throw error;
    }
}

async function deleteCurrentUserAccount(payload = {}) {
    try {
        return await apiCall('/api/me', {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
    } catch (error) {
        console.error('Failed to delete current user account:', error);
        throw error;
    }
}

/**
 * Assign role to user
 */
async function updateUserRoles(userId, roleIds) {
    try {
        return await apiPatch(`/api/users/${userId}/roles`, { role_ids: roleIds });
    } catch (error) {
        console.error('Failed to update user roles:', error);
        throw error;
    }
}

/**
 * Ensure user has required role (throws error if not)
 */
function ensureUserRole(user, roleName) {
    if (!userHasRole(user, roleName)) {
        throw new Error(`User does not have required role: ${roleName}`);
    }
}

/**
 * Get user's display name (full_name or email)
 */
function getUserDisplayName(user) {
    return user.full_name || user.email || 'Unknown User';
}
