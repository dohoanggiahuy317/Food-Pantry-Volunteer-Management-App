// Pantry Lead Functions - Shift Management

/**
 * Get all shifts for a pantry
 * Returns shifts with nested shift_roles
 */
async function getShifts(pantryId) {
    try {
        const shifts = await apiGet(`/api/pantries/${pantryId}/shifts`);
        return shifts;
    } catch (error) {
        console.error('Failed to get shifts:', error);
        throw error;
    }
}

/**
 * Get non-expired, non-cancelled shifts for a pantry.
 * Returns shifts with nested shift_roles
 */
async function getActiveShifts(pantryId) {
    try {
        const shifts = await apiGet(`/api/pantries/${pantryId}/active-shifts`);
        return shifts;
    } catch (error) {
        console.error('Failed to get shifts:', error);
        throw error;
    }
}

/**
 * Get specific shift by ID
 */
async function getShift(shiftId) {
    try {
        const shift = await apiGet(`/api/shifts/${shiftId}`);
        return shift;
    } catch (error) {
        console.error('Failed to get shift:', error);
        throw error;
    }
}

/**
 * Get role registrations for a shift (lead/admin only)
 */
async function getShiftRegistrations(shiftId) {
    try {
        const registrations = await apiGet(`/api/shifts/${shiftId}/registrations`);
        return registrations;
    } catch (error) {
        console.error('Failed to get shift registrations:', error);
        throw error;
    }
}

/**
 * Create a new shift (pantry lead or admin)
 */
async function createShift(pantryId, shiftData) {
    try {
        const shift = await apiPost(`/api/pantries/${pantryId}/shifts`, shiftData);
        return shift;
    } catch (error) {
        console.error('Failed to create shift:', error);
        throw error;
    }
}

/**
 * Create a shift and its roles atomically, optionally as a recurring series.
 */
async function createFullShift(pantryId, shiftData) {
    try {
        const response = await apiPost(`/api/pantries/${pantryId}/shifts/full-create`, shiftData);
        return response;
    } catch (error) {
        console.error('Failed to fully create shift:', error);
        throw error;
    }
}

/**
 * Update shift information
 */
async function updateShift(shiftId, shiftData) {
    try {
        const shift = await apiPatch(`/api/shifts/${shiftId}`, shiftData);
        return shift;
    } catch (error) {
        console.error('Failed to update shift:', error);
        throw error;
    }
}

/**
 * Update shift and roles in one request
 */
async function updateFullShift(shiftId, shiftData) {
    try {
        const shift = await apiPut(`/api/shifts/${shiftId}/full-update`, shiftData);
        return shift;
    } catch (error) {
        console.error('Failed to fully update shift:', error);
        throw error;
    }
}

/**
 * Cancel a shift (soft-cancel with volunteer reconfirmation flow)
 */
async function deleteShift(shiftId) {
    try {
        const data = await apiDelete(`/api/shifts/${shiftId}`);
        return data;
    } catch (error) {
        console.error('Failed to delete shift:', error);
        throw error;
    }
}

/**
 * Cancel a shift with scope support for recurring series.
 */
async function cancelShiftWithScope(shiftId, applyScope = 'single') {
    try {
        const data = await apiPost(`/api/shifts/${shiftId}/cancel`, { apply_scope: applyScope });
        return data;
    } catch (error) {
        console.error('Failed to cancel shift:', error);
        throw error;
    }
}

/**
 * Mark attendance for a signup (PANTRY_LEAD or ADMIN)
 */
async function markAttendance(signupId, attendanceStatus) {
    try {
        const updated = await apiPatch(`/api/signups/${signupId}/attendance`, {
            attendance_status: attendanceStatus
        });
        return updated;
    } catch (error) {
        console.error('Failed to mark attendance:', error);
        throw error;
    }
}

/**
 * Get roles for a specific shift
 */
async function getShiftRoles(shiftId) {
    try {
        const roles = await apiGet(`/api/shifts/${shiftId}/roles`);
        return roles;
    } catch (error) {
        console.error('Failed to get shift roles:', error);
        throw error;
    }
}

/**
 * Create a role for a shift (e.g., "Food Sorter" with required_count: 5)
 */
async function createShiftRole(shiftId, roleData) {
    try {
        const role = await apiPost(`/api/shifts/${shiftId}/roles`, roleData);
        return role;
    } catch (error) {
        console.error('Failed to create shift role:', error);
        throw error;
    }
}

/**
 * Update shift role information
 */
async function updateShiftRole(roleId, roleData) {
    try {
        const role = await apiPatch(`/api/shift-roles/${roleId}`, roleData);
        return role;
    } catch (error) {
        console.error('Failed to update shift role:', error);
        throw error;
    }
}

/**
 * Delete a shift role
 */
async function deleteShiftRole(roleId) {
    try {
        await apiDelete(`/api/shift-roles/${roleId}`);
    } catch (error) {
        console.error('Failed to delete shift role:', error);
        throw error;
    }
}

/**
 * Format datetime for input field (YYYY-MM-DDTHH:MM)
 */
function formatDateTimeForInput(dateString) {
    return formatDateTimeForLocalInput(dateString);
}

/**
 * Format datetime for display
 */
function formatDateTimeForDisplay(dateString) {
    return formatLocalDateTime(dateString);
}

/**
 * Calculate shift duration in hours
 */
function calculateShiftDuration(startTime, endTime) {
    const start = new Date(startTime);
    const end = new Date(endTime);
    const hours = (end - start) / (1000 * 60 * 60);
    return hours.toFixed(1);
}
