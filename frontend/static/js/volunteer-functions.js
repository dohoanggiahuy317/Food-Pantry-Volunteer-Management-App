// Volunteer Functions - Shift Signups and Viewing

/**
 * Get all signups for a specific shift role
 */
async function getSignupsForRole(shiftRoleId) {
    try {
        const signups = await apiGet(`/api/shift-roles/${shiftRoleId}/signups`);
        return signups;
    } catch (error) {
        console.error('Failed to get signups:', error);
        throw error;
    }
}

/**
 * Get all signups for a specific user
 */
async function getUserSignups(userId) {
    try {
        const signups = await apiGet(`/api/users/${userId}/signups`);
        return signups;
    } catch (error) {
        console.error('Failed to get user signups:', error);
        throw error;
    }
}

/**
 * Classify a shift-like object into incoming/ongoing/past buckets
 */
function classifyShiftBucket(shift, now = new Date()) {
    const start = new Date(shift.start_time);
    const end = new Date(shift.end_time);

    if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) {
        return 'past';
    }

    if (start > now) return 'incoming';
    if (start <= now && now < end) return 'ongoing';
    return 'past';
}

/**
 * Sign up for a shift role
 * If userId is not provided, uses current user from query param
 */
async function signupForShift(shiftRoleId, userId = null) {
    try {
        const payload = userId ? { user_id: userId } : {};
        const data = await apiPost(`/api/shift-roles/${shiftRoleId}/signup`, payload);
        return data;
    } catch (error) {
        console.error('Failed to signup for shift:', error);
        throw error;
    }
}

/**
 * Cancel a signup
 */
async function cancelSignup(signupId) {
    try {
        await apiDelete(`/api/signups/${signupId}`);
    } catch (error) {
        console.error('Failed to cancel signup:', error);
        throw error;
    }
}

/**
 * Reconfirm or cancel a pending signup after shift edits
 */
async function reconfirmSignup(signupId, action) {
    try {
        const normalizedAction = String(action || '').toUpperCase();
        const updated = await apiPatch(`/api/signups/${signupId}/reconfirm`, {
            action: normalizedAction
        });
        return updated;
    } catch (error) {
        console.error('Failed to reconfirm signup:', error);
        throw error;
    }
}

/**
 * Check if user is signed up for a specific role
 */
async function isUserSignedUp(shiftRoleId, userId) {
    try {
        const signups = await getSignupsForRole(shiftRoleId);
        return signups.some(signup => signup.user_id === userId);
    } catch (error) {
        console.error('Failed to check signup status:', error);
        return false;
    }
}

/**
 * Get available slots for a shift role
 */
function getAvailableSlots(shiftRole) {
    const required = shiftRole.required_count || 0;
    const signedUp = shiftRole.signups ? shiftRole.signups.length : 0;
    return Math.max(0, required - signedUp);
}

/**
 * Check if a shift role is full
 */
function isShiftRoleFull(shiftRole) {
    return getAvailableSlots(shiftRole) === 0;
}

/**
 * Calculate capacity percentage for progress bar
 */
function calculateCapacity(shiftRole) {
    const required = shiftRole.required_count || 0;
    if (required === 0) return 0;
    
    const signedUp = shiftRole.signups ? shiftRole.signups.length : 0;
    return Math.min(100, Math.round((signedUp / required) * 100));
}

/**
 * Get capacity status (full, almost-full, or available)
 */
function getCapacityStatus(shiftRole) {
    const available = getAvailableSlots(shiftRole);
    const required = shiftRole.required_count || 0;
    
    if (available === 0) return 'full';
    if (required > 0 && available <= Math.ceil(required * 0.2)) return 'almost-full';
    return 'available';
}

/**
 * Get capacity color for UI
 */
function getCapacityColor(status) {
    const colors = {
        'full': '#e53e3e',
        'almost-full': '#dd6b20',
        'available': '#38a169'
    };
    return colors[status] || colors.available;
}

/**
 * Format shift time range for display
 */
function formatShiftTime(shift) {
    const start = new Date(shift.start_time);
    const end = new Date(shift.end_time);
    
    const timeOptions = { hour: 'numeric', minute: '2-digit', hour12: true };
    const startTime = start.toLocaleTimeString('en-US', timeOptions);
    const endTime = end.toLocaleTimeString('en-US', timeOptions);
    
    return `${startTime} - ${endTime}`;
}

/**
 * Format shift date for display
 */
function formatShiftDate(shift) {
    const start = new Date(shift.start_time);
    return start.toLocaleDateString('en-US', {
        weekday: 'short',
        month: 'short',
        day: 'numeric',
        year: 'numeric'
    });
}

/**
 * Check if shift is in the past
 */
function isShiftPast(shift) {
    const end = new Date(shift.end_time);
    return end < new Date();
}

/**
 * Check whether a signup can still be canceled
 */
function canCancelSignup(signupItem, now = new Date()) {
    return classifyShiftBucket(signupItem, now) === 'incoming';
}

/**
 * Check if shift is today
 */
function isShiftToday(shift) {
    const start = new Date(shift.start_time);
    const today = new Date();
    return start.toDateString() === today.toDateString();
}

/**
 * Sort shifts by start time
 */
function sortShiftsByTime(shifts, ascending = true) {
    return [...shifts].sort((a, b) => {
        const timeA = new Date(a.start_time).getTime();
        const timeB = new Date(b.start_time).getTime();
        return ascending ? timeA - timeB : timeB - timeA;
    });
}
