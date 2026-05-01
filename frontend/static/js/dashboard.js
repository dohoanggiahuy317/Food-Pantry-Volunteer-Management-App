// Global state
let currentUser = null;
let currentPantryId = null;
let allPantries = [];
let allPublicPantries = [];
let expandedShiftContext = null;
let registrationsCache = {};
let editingShiftSnapshot = null;
let activeManageShiftsSubtab = 'create';
let activeAdminSubtab = 'pantries';
let managedShifts = [];
let manageShiftsSearchQuery = '';
let manageShiftsStatusFilter = 'incoming';
let managedShiftPanelMode = 'create';
let managedShiftMobileView = 'queue';
let selectedManagedShiftId = null;
let helpBroadcastShift = null;
let helpBroadcastSelected = [];
let helpBroadcastCandidateMap = new Map();
let helpBroadcastCandidateCache = [];
let helpBroadcastCandidateQuery = '';
let helpBroadcastSearchTimer = null;
let helpBroadcastRequestToken = 0;
let attendanceModalShiftId = null;
let attendanceModalRegistrations = null;
let attendanceModalSearchQuery = '';
let selectedAssignPantryId = null;
let pantryLeadUsers = [];
let selectedPantryLeadId = null;
let adminPantrySearchQuery = '';
let selectedAdminPantryId = null;
let adminPantryLeadSearchQuery = '';
let adminPantryLeadActionInFlight = false;
let adminRoles = [];
let adminUsers = [];
let selectedAdminUserId = null;
let selectedAdminUserProfile = null;
let selectedAdminUserProfileError = '';
let lastAdminUsersPhoneViewport = null;
let dashboardBootPromise = null;
let dashboardEventListenersBound = false;
let recurringScopeResolver = null;
let volunteerPantryDirectory = [];
let volunteerPantrySearchQuery = '';
let volunteerPantrySort = 'name-asc';
let volunteerPantrySubscriptionFilter = 'all';
let selectedVolunteerPantryId = null;
let lastVolunteerPantriesCompactViewport = null;
let myRegisteredSignups = [];
let myShiftsViewMode = 'calendar';
let currentGoogleCalendarStatus = null;
let myShiftsListFilters = {
    search: '',
    pantryId: 'all',
    timeBucket: 'all',
    status: 'all',
    sort: 'date-asc'
};

const RECURRING_WEEKDAY_ORDER = ['MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU'];
const RECURRING_WEEKDAY_LABELS = {
    MO: 'Mon',
    TU: 'Tue',
    WE: 'Wed',
    TH: 'Thu',
    FR: 'Fri',
    SA: 'Sat',
    SU: 'Sun'
};
const HELP_BROADCAST_MAX_RECIPIENTS = 25;
const MANAGE_SHIFTS_PHONE_QUERY = '(max-width: 767px)';

function currentUserHasRole(roleName) {
    return Boolean(currentUser && Array.isArray(currentUser.roles) && currentUser.roles.includes(roleName));
}

function currentUserIsAdminCapable() {
    return currentUserHasRole('ADMIN') || currentUserHasRole('SUPER_ADMIN');
}

function currentUserCanAccessAppTour() {
    return currentUserHasRole('VOLUNTEER')
        && !currentUserIsAdminCapable()
        && !currentUserHasRole('PANTRY_LEAD');
}

function getWeekdayCodeFromDateInput(value) {
    if (!value) {
        return null;
    }

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return null;
    }

    const weekdayOrder = ['SU', 'MO', 'TU', 'WE', 'TH', 'FR', 'SA'];
    return weekdayOrder[date.getDay()] || null;
}

function setWeekdayChipSelection(containerId, weekdays = []) {
    const normalized = new Set(Array.isArray(weekdays) ? weekdays : []);
    document.querySelectorAll(`#${containerId} [data-weekday]`).forEach((button) => {
        button.classList.toggle('active', normalized.has(button.dataset.weekday));
    });
}

function getSelectedWeekdays(containerId) {
    return Array.from(document.querySelectorAll(`#${containerId} [data-weekday].active`))
        .map((button) => button.dataset.weekday)
        .filter(Boolean);
}

function setRecurrenceEndMode(prefix, mode = 'COUNT') {
    const normalized = mode === 'UNTIL' ? 'UNTIL' : 'COUNT';
    document.querySelectorAll(`input[name="${prefix}-repeat-end-mode"]`).forEach((input) => {
        input.checked = input.value === normalized;
    });

    const countInput = document.getElementById(`${prefix}-repeat-count`);
    const untilInput = document.getElementById(`${prefix}-repeat-until`);
    if (countInput) {
        countInput.disabled = normalized !== 'COUNT';
    }
    if (untilInput) {
        untilInput.disabled = normalized !== 'UNTIL';
    }
}

function describeRecurrenceRule(recurrence, shift = null) {
    if (!recurrence) {
        return 'One-time shift';
    }

    const weekdays = Array.isArray(recurrence.weekdays)
        ? recurrence.weekdays.map((code) => RECURRING_WEEKDAY_LABELS[code] || code).join(', ')
        : '';
    const everyText = Number(recurrence.interval_weeks || 1) === 1
        ? 'every week'
        : `every ${Number(recurrence.interval_weeks || 1)} weeks`;
    const endText = recurrence.end_mode === 'UNTIL'
        ? `until ${recurrence.until_date || 'a set date'}`
        : `for ${Number(recurrence.occurrence_count || 1)} occurrence(s)`;
    const summaryParts = [`${everyText} on ${weekdays}; ${endText}.`];

    if (shift) {
        const startValue = shift.start_time || shift.startDate || null;
        const endValue = shift.end_time || shift.endDate || null;
        const startDateKey = getLocalDateKeyForTimeZone(startValue);
        const endDateKey = getLocalDateKeyForTimeZone(endValue);
        if (startDateKey && endDateKey && startDateKey !== endDateKey) {
            summaryParts.push(`Time window: ${formatLocalTimeRange(startValue, endValue, { includeDate: false })}.`);
        }
    }

    return summaryParts.join(' ');
}

function resetCreateRecurrenceForm() {
    const toggle = document.getElementById('shift-repeat-toggle');
    const fields = document.getElementById('shift-recurrence-fields');
    if (toggle) {
        toggle.checked = false;
    }
    if (fields) {
        fields.classList.add('app-hidden');
    }
    const intervalInput = document.getElementById('shift-repeat-interval');
    const countInput = document.getElementById('shift-repeat-count');
    const untilInput = document.getElementById('shift-repeat-until');
    if (intervalInput) intervalInput.value = '1';
    if (countInput) countInput.value = '4';
    if (untilInput) untilInput.value = '';
    setRecurrenceEndMode('shift', 'COUNT');
    setWeekdayChipSelection('shift-repeat-weekdays', []);
}

function resetEditRecurrenceForm() {
    const card = document.getElementById('edit-shift-recurrence-card');
    const summary = document.getElementById('edit-shift-recurrence-summary');
    if (card) {
        card.classList.add('app-hidden');
    }
    if (summary) {
        summary.textContent = '';
    }
    const intervalInput = document.getElementById('edit-shift-repeat-interval');
    const countInput = document.getElementById('edit-shift-repeat-count');
    const untilInput = document.getElementById('edit-shift-repeat-until');
    if (intervalInput) intervalInput.value = '1';
    if (countInput) countInput.value = '1';
    if (untilInput) untilInput.value = '';
    setRecurrenceEndMode('edit-shift', 'COUNT');
    setWeekdayChipSelection('edit-shift-repeat-weekdays', []);
}

function toggleCreateRecurrenceFields() {
    const toggle = document.getElementById('shift-repeat-toggle');
    const fields = document.getElementById('shift-recurrence-fields');
    if (!toggle || !fields) {
        return;
    }
    fields.classList.toggle('app-hidden', !toggle.checked);

    if (toggle.checked) {
        const currentWeekday = getWeekdayCodeFromDateInput(document.getElementById('shift-start')?.value);
        if (currentWeekday) {
            const selected = new Set(getSelectedWeekdays('shift-repeat-weekdays'));
            selected.add(currentWeekday);
            setWeekdayChipSelection('shift-repeat-weekdays', Array.from(selected));
        }
    }
}

function populateEditRecurrenceForm(shift) {
    const recurrence = shift && shift.recurrence ? shift.recurrence : null;
    const card = document.getElementById('edit-shift-recurrence-card');
    const summary = document.getElementById('edit-shift-recurrence-summary');
    if (!card || !summary) {
        return;
    }

    if (!shift || !shift.is_recurring || !recurrence) {
        resetEditRecurrenceForm();
        return;
    }

    card.classList.remove('app-hidden');
    summary.textContent = describeRecurrenceRule(recurrence, shift);
    document.getElementById('edit-shift-repeat-interval').value = String(Number(recurrence.interval_weeks || 1));
    document.getElementById('edit-shift-repeat-count').value = String(Number(recurrence.occurrence_count || 1));
    document.getElementById('edit-shift-repeat-until').value = recurrence.until_date || '';
    setWeekdayChipSelection('edit-shift-repeat-weekdays', recurrence.weekdays || []);
    setRecurrenceEndMode('edit-shift', recurrence.end_mode || 'COUNT');
}

function buildRecurrencePayloadFromForm(prefix, startInputId) {
    if (prefix === 'shift') {
        const enabled = document.getElementById('shift-repeat-toggle')?.checked;
        if (!enabled) {
            return null;
        }
    } else if (!editingShiftSnapshot?.is_recurring) {
        return null;
    }

    const startValue = document.getElementById(startInputId)?.value;
    const startWeekday = getWeekdayCodeFromDateInput(startValue);
    const weekdays = getSelectedWeekdays(`${prefix}-repeat-weekdays`);
    if (startWeekday && !weekdays.includes(startWeekday)) {
        weekdays.push(startWeekday);
    }
    weekdays.sort((a, b) => RECURRING_WEEKDAY_ORDER.indexOf(a) - RECURRING_WEEKDAY_ORDER.indexOf(b));

    const interval = parseInt(document.getElementById(`${prefix}-repeat-interval`)?.value || '1', 10);
    const endMode = document.querySelector(`input[name="${prefix}-repeat-end-mode"]:checked`)?.value || 'COUNT';
    const payload = {
        timezone: getBrowserTimeZone(),
        frequency: 'WEEKLY',
        interval_weeks: interval,
        weekdays,
        end_mode: endMode
    };

    if (endMode === 'UNTIL') {
        payload.until_date = document.getElementById(`${prefix}-repeat-until`)?.value || '';
    } else {
        payload.occurrence_count = parseInt(document.getElementById(`${prefix}-repeat-count`)?.value || '0', 10);
    }
    return payload;
}

function promptRecurringScope(mode = 'edit') {
    const modal = document.getElementById('recurring-scope-modal');
    const title = document.getElementById('recurring-scope-modal-title');
    const copy = document.getElementById('recurring-scope-modal-copy');
    if (!modal || !title || !copy) {
        return Promise.resolve('single');
    }

    title.textContent = mode === 'cancel' ? 'Cancel recurring shift' : 'Save recurring shift changes';
    copy.textContent = mode === 'cancel'
        ? 'Cancel only this event, or cancel this and all following events in the series.'
        : 'Apply these changes to only this event, or to this and all following events in the recurring series.';
    modal.classList.remove('app-hidden');

    return new Promise((resolve) => {
        recurringScopeResolver = resolve;
    });
}

function closeRecurringScopeModal(choice = null) {
    const modal = document.getElementById('recurring-scope-modal');
    if (modal) {
        modal.classList.add('app-hidden');
    }
    if (recurringScopeResolver) {
        const resolver = recurringScopeResolver;
        recurringScopeResolver = null;
        resolver(choice);
    }
}

async function syncCurrentUserTimezoneIfNeeded() {
    if (!currentUser || typeof updateCurrentUserProfile !== 'function') {
        return;
    }

    const browserTimeZone = getBrowserTimeZone();
    if (!browserTimeZone || currentUser.timezone === browserTimeZone) {
        return;
    }

    try {
        currentUser = await updateCurrentUserProfile({ timezone: browserTimeZone });
    } catch (error) {
        console.error('Failed to sync browser timezone:', error);
    }
}

async function initializeDashboardApp() {
    if (dashboardBootPromise) {
        return dashboardBootPromise;
    }

    dashboardBootPromise = (async () => {
        try {
            if (typeof getCurrentUser === 'undefined') {
                throw new Error('Required functions not loaded. Please refresh the page.');
            }

            currentUser = await getCurrentUser();
            await syncCurrentUserTimezoneIfNeeded();
            document.getElementById('user-email').textContent = currentUser.email;
            document.getElementById('user-role').textContent = currentUser.roles.join(', ');

            const defaultTab = setupRoleBasedUI();
            await loadPantries();

            if (!dashboardEventListenersBound) {
                setupEventListeners();
                dashboardEventListenersBound = true;
            }

            await activateTab(defaultTab);
        } catch (error) {
            dashboardBootPromise = null;
            console.error('Failed to initialize dashboard:', error);
            showMessage('calendar', `Failed to load: ${error.message}`, 'error');
            const shiftsContainer = document.getElementById('shifts-container');
            if (shiftsContainer) {
                shiftsContainer.innerHTML = `
                    <div class="error-state-card">
                        <h3>Failed to Load</h3>
                        <p><strong>${escapeHtml(error.message || 'Unknown error')}</strong></p>
                    </div>
                `;
            }
            throw error;
        }
    })();

    await dashboardBootPromise;
    await maybeStartAppTour();
    return dashboardBootPromise;
}

const APP_TOUR_STORAGE_KEY_PREFIX = 'volunteerAppTourCompleted';
const APP_TOUR_PENDING_COOKIE = 'volunteerAppTourPendingSignup';
const APP_TOUR_NUDGE_DISMISSED_KEY_PREFIX = 'volunteerAppTourNudgeDismissed';
const APP_TOUR_FILTERS_SELECTOR = '[data-app-tour-target="available-calendar-filters"]';
let appTourSteps = null;
let appTourCurrentIndex = 0;
let appTourManagedSidebarControllerKey = null;
let appTourResizeTimeoutId = null;
let appTourIsRequired = false;
let appTourScrollLockEnabled = false;
let appTourStepTransitionInFlight = false;

const APP_TOUR_SCROLL_KEYS = new Set([
    'ArrowDown',
    'ArrowLeft',
    'ArrowRight',
    'ArrowUp',
    'End',
    'Home',
    'PageDown',
    'PageUp',
    ' '
]);

function isElementVisible(element) {
    if (!(element instanceof HTMLElement)) {
        return false;
    }
    const style = window.getComputedStyle(element);
    return style.visibility !== 'hidden' && style.display !== 'none' && element.offsetWidth > 0 && element.offsetHeight > 0;
}

function getAppTourSteps() {
    const steps = [
        {
            title: 'Welcome',
            body: 'This tour will walk you through the main sections of the volunteer dashboard.',
            selector: '.header-left h1',
            tab: null
        },
        {
            title: 'Navigation',
            body: 'Use these tabs to jump between the calendar, your shifts, pantries, admin features, and your account.',
            selector: '.nav-tabs-container',
            tab: null
        },
        {
            title: 'Calendar',
            body: 'Browse all available volunteer shifts and use the calendar filters to find a time that works for you.',
            selector: '.calendar-shell-card',
            tab: 'calendar'
        },
        {
            title: 'Calendar Views',
            body: 'You can view the calendar in month, week, and day modes here.',
            selector: '#content-calendar .calendar-view-switch',
            tab: 'calendar'
        },
        {
            title: 'Filters',
            body: 'Use these filters to search by pantry, date range, or time bucket.',
            selector: APP_TOUR_FILTERS_SELECTOR,
            tab: 'calendar',
            requiresAvailableCalendarSidebar: true
        },
        {
            title: 'My Shifts',
            body: 'Review the shifts you already signed up for and switch between calendar and list views.',
            selector: '#tab-my-shifts',
            tab: 'my-shifts',
            optional: true
        },
        {
            title: 'Pantry Directory',
            body: 'Use the Pantry tab to browse pantry details, preview upcoming shifts, and manage your subscriptions.',
            selector: '#tab-pantries',
            tab: 'pantries',
            optional: true
        },
        {
            title: 'Search Pantries',
            body: 'Search by pantry name or address to quickly narrow the directory.',
            selector: '#volunteer-pantry-search',
            tab: 'pantries',
            optional: true
        },
        {
            title: 'Sort Pantries',
            body: 'Sort the pantry list alphabetically to scan the directory the way you prefer.',
            selector: '#volunteer-pantry-sort',
            tab: 'pantries',
            optional: true
        },
        {
            title: 'Subscription Filters',
            body: 'Use these filters to show all pantries, only the ones you subscribed to, or only unsubscribed ones.',
            selector: '.volunteer-pantries-filter-row',
            tab: 'pantries',
            optional: true
        },
        {
            title: 'Pantry List',
            body: 'Select a pantry here to review its address, upcoming shifts, and subscription status.',
            selector: '#volunteer-pantries-list',
            tab: 'pantries',
            optional: true
        },
        {
            title: 'Pantry Details',
            body: 'This panel shows the selected pantry details, pantry leads, the next incoming shift, and the subscribe or unsubscribe action.',
            selector: '#volunteer-pantry-detail .volunteer-pantry-detail-head',
            tab: 'pantries',
            optional: true
        },
        {
            title: 'My Account',
            body: 'Use My Account to review your saved account details and manage profile settings.',
            selector: '#tab-my-account',
            tab: 'my-account'
        },
        {
            title: 'Account Summary',
            body: 'This section shows your current account details, including your email, phone number, roles, and saved timezone.',
            selector: '#my-account-summary',
            tab: 'my-account'
        },
        {
            title: 'Timezone Note',
            body: 'This note explains which browser timezone the app is using to display times on the web.',
            selector: '#my-account-timezone-note',
            tab: 'my-account'
        },
        {
            title: 'Basic Information',
            body: 'Update your full name and phone number here, then save your changes.',
            selector: '#my-account-profile-form',
            tab: 'my-account'
        },
        {
            title: 'Email Address',
            body: 'Review your current email and start an email change request from this section when needed.',
            selector: '#my-account-email-form',
            tab: 'my-account'
        },
        {
            title: 'Delete Account',
            body: 'Warning: use this action only if you want to permanently remove your account. Deleting your account will sign you out and cannot be undone.',
            selector: '#delete-account-btn',
            tab: 'my-account'
        }
    ];

    return steps.filter((step) => {
        if (step.optional) {
            return Boolean(document.querySelector(step.selector));
        }
        return true;
    });
}

function getAppTourStorageKey() {
    if (!currentUser || !currentUser.user_id) {
        return null;
    }
    return `${APP_TOUR_STORAGE_KEY_PREFIX}:${currentUser.user_id}`;
}

function getAppTourNudgeDismissedKey() {
    if (!currentUser || !currentUser.user_id) {
        return null;
    }
    return `${APP_TOUR_NUDGE_DISMISSED_KEY_PREFIX}:${currentUser.user_id}`;
}

function getPendingAppTourCookie() {
    return window.Cookies ? window.Cookies.get(APP_TOUR_PENDING_COOKIE) : null;
}

function shouldRequireAppTour() {
    if (!currentUser || !currentUser.user_id) {
        return false;
    }

    const pendingValue = getPendingAppTourCookie();
    if (!pendingValue) {
        return false;
    }

    if (pendingValue === 'pending') {
        if (window.Cookies) {
            window.Cookies.set(APP_TOUR_PENDING_COOKIE, String(currentUser.user_id), { sameSite: 'Lax' });
        }
        return true;
    }

    return pendingValue === String(currentUser.user_id);
}

function markAppTourCompleted() {
    const storageKey = getAppTourStorageKey();
    if (storageKey) {
        localStorage.setItem(storageKey, 'true');
    }
    const nudgeDismissedKey = getAppTourNudgeDismissedKey();
    if (nudgeDismissedKey) {
        sessionStorage.setItem(nudgeDismissedKey, 'true');
    }
    if (window.Cookies) {
        window.Cookies.remove(APP_TOUR_PENDING_COOKIE);
    }
}

function hideAppTourNudge() {
    document.getElementById('app-tour-nudge')?.classList.add('app-hidden');
}

function showAppTourNudge() {
    document.getElementById('app-tour-nudge')?.classList.remove('app-hidden');
}

function dismissAppTourNudge() {
    const nudgeDismissedKey = getAppTourNudgeDismissedKey();
    if (nudgeDismissedKey) {
        sessionStorage.setItem(nudgeDismissedKey, 'true');
    }
    hideAppTourNudge();
}

function shouldShowAppTourNudge() {
    const storageKey = getAppTourStorageKey();
    const nudgeDismissedKey = getAppTourNudgeDismissedKey();
    if (!storageKey || !nudgeDismissedKey) {
        return false;
    }

    const hasCompletedTour = localStorage.getItem(storageKey) === 'true';
    const cookiePresent = Boolean(getPendingAppTourCookie());
    const dismissedForSession = sessionStorage.getItem(nudgeDismissedKey) === 'true';

    return hasCompletedTour && !cookiePresent && !dismissedForSession && !appTourIsRequired;
}

async function openAppTour(options = {}) {
    if (!currentUserCanAccessAppTour()) {
        return;
    }
    appTourIsRequired = Boolean(options.forceRequired);
    appTourSteps = getAppTourSteps();
    if (!appTourSteps.length) {
        return;
    }
    appTourCurrentIndex = 0;
    await renderAppTourStep(0);
}

function getAvailableCalendarTourController() {
    if (typeof getCalendarController !== 'function') {
        return null;
    }
    return getCalendarController('available');
}

function resetAppTourPopoverPlacement(popover, popoverArrow) {
    popover.style.transform = 'none';
    popover.style.top = '';
    popover.style.left = '';
    popover.style.removeProperty('--tour-arrow-left');
    popover.style.removeProperty('--tour-arrow-top');
    popover.classList.remove(
        'tour-popover-placement-top',
        'tour-popover-placement-right',
        'tour-popover-placement-bottom',
        'tour-popover-placement-left'
    );
    if (popoverArrow) {
        popoverArrow.className = 'tour-popover-arrow';
    }
}

async function waitForAppTourLayout() {
    await new Promise((resolve) => window.requestAnimationFrame(() => resolve()));
    await new Promise((resolve) => window.requestAnimationFrame(() => resolve()));
}

async function scrollAppTourTargetIntoView(target) {
    if (!(target instanceof HTMLElement)) {
        return;
    }
    target.scrollIntoView({ behavior: 'auto', block: 'center', inline: 'center' });
    await waitForAppTourLayout();
}

async function cleanupAppTourManagedSidebar() {
    if (!appTourManagedSidebarControllerKey) {
        return;
    }
    if (typeof getCalendarController === 'function') {
        getCalendarController(appTourManagedSidebarControllerKey)?.closeSidebar();
    }
    appTourManagedSidebarControllerKey = null;
    await waitForAppTourLayout();
}

async function prepareAppTourStep(step) {
    if (!step?.requiresAvailableCalendarSidebar) {
        return;
    }

    const controller = getAvailableCalendarTourController();
    if (!controller || !isPhoneViewport()) {
        return;
    }

    const sidebar = controller.part?.('sidebar');
    const sidebarWasOpen = sidebar?.classList.contains('open');
    if (!sidebarWasOpen) {
        controller.openSidebar();
        appTourManagedSidebarControllerKey = 'available';
    }
    await waitForAppTourLayout();
}

function applyAppTourHighlight(highlight, rect) {
    const padding = Math.min(18, Math.max(12, Math.round(Math.min(rect.width, rect.height) * 0.08)));
    const top = Math.max(8, rect.top - padding);
    const left = Math.max(8, rect.left - padding);
    const width = Math.min(window.innerWidth - 16, rect.width + padding * 2);
    const height = Math.min(window.innerHeight - 16, rect.height + padding * 2);

    highlight.style.top = `${top}px`;
    highlight.style.left = `${left}px`;
    highlight.style.width = `${width}px`;
    highlight.style.height = `${height}px`;
    highlight.style.borderRadius = `${Math.min(width, height) > 120 ? 24 : 18}px`;
}

function clampAppTourValue(value, min, max) {
    return Math.min(max, Math.max(min, value));
}

function isAppTourOpen() {
    const popover = document.getElementById('app-tour-popover');
    return Boolean(popover && !popover.classList.contains('app-hidden'));
}

function preventAppTourUserScroll(event) {
    if (isAppTourOpen()) {
        event.preventDefault();
    }
}

function preventAppTourKeyboardScroll(event) {
    const popover = document.getElementById('app-tour-popover');
    if (popover?.contains(event.target)) {
        return;
    }

    if (isAppTourOpen() && APP_TOUR_SCROLL_KEYS.has(event.key)) {
        event.preventDefault();
    }
}

function setAppTourScrollLock(locked) {
    if (locked === appTourScrollLockEnabled) {
        return;
    }

    appTourScrollLockEnabled = locked;
    document.documentElement.classList.toggle('app-tour-scroll-locked', locked);
    document.body.classList.toggle('app-tour-scroll-locked', locked);

    const listenerOptions = { passive: false, capture: true };
    if (locked) {
        window.addEventListener('wheel', preventAppTourUserScroll, listenerOptions);
        window.addEventListener('touchmove', preventAppTourUserScroll, listenerOptions);
        window.addEventListener('keydown', preventAppTourKeyboardScroll, true);
    } else {
        window.removeEventListener('wheel', preventAppTourUserScroll, listenerOptions);
        window.removeEventListener('touchmove', preventAppTourUserScroll, listenerOptions);
        window.removeEventListener('keydown', preventAppTourKeyboardScroll, true);
    }
}

function scheduleAppTourReposition() {
    if (!isAppTourOpen() || !appTourSteps || appTourCurrentIndex < 0 || appTourCurrentIndex >= appTourSteps.length) {
        return;
    }

    if (appTourResizeTimeoutId) {
        window.clearTimeout(appTourResizeTimeoutId);
    }

    appTourResizeTimeoutId = window.setTimeout(() => {
        appTourResizeTimeoutId = null;
        if (isAppTourOpen()) {
            renderAppTourStep(appTourCurrentIndex);
        }
    }, 120);
}

function positionAppTourPopover(popover, popoverArrow, rect) {
    const margin = 16;
    const arrowSize = 14;
    const spaceAbove = rect.top - margin;
    const spaceBelow = window.innerHeight - rect.bottom - margin;
    const spaceLeft = rect.left - margin;
    const spaceRight = window.innerWidth - rect.right - margin;
    const popoverWidth = popover.offsetWidth;
    const popoverHeight = popover.offsetHeight;

    let placement = 'bottom';
    if (spaceRight >= popoverWidth + arrowSize) {
        placement = 'right';
    } else if (spaceBelow >= popoverHeight + arrowSize) {
        placement = 'bottom';
    } else if (spaceAbove >= popoverHeight + arrowSize) {
        placement = 'top';
    } else if (spaceLeft >= popoverWidth + arrowSize) {
        placement = 'left';
    } else if (spaceBelow >= spaceAbove) {
        placement = 'bottom';
    } else {
        placement = 'top';
    }

    let top = margin;
    let left = margin;
    const centerX = rect.left + rect.width / 2;
    const centerY = rect.top + rect.height / 2;

    if (placement === 'right') {
        left = clampAppTourValue(rect.right + arrowSize, margin, window.innerWidth - popoverWidth - margin);
        top = clampAppTourValue(centerY - popoverHeight / 2, margin, window.innerHeight - popoverHeight - margin);
    } else if (placement === 'left') {
        left = clampAppTourValue(rect.left - popoverWidth - arrowSize, margin, window.innerWidth - popoverWidth - margin);
        top = clampAppTourValue(centerY - popoverHeight / 2, margin, window.innerHeight - popoverHeight - margin);
    } else if (placement === 'top') {
        top = clampAppTourValue(rect.top - popoverHeight - arrowSize, margin, window.innerHeight - popoverHeight - margin);
        left = clampAppTourValue(centerX - popoverWidth / 2, margin, window.innerWidth - popoverWidth - margin);
    } else {
        top = clampAppTourValue(rect.bottom + arrowSize, margin, window.innerHeight - popoverHeight - margin);
        left = clampAppTourValue(centerX - popoverWidth / 2, margin, window.innerWidth - popoverWidth - margin);
    }

    popover.style.top = `${top}px`;
    popover.style.left = `${left}px`;
    popover.classList.add(`tour-popover-placement-${placement}`);

    if (!popoverArrow) {
        return;
    }

    popoverArrow.classList.add(`tour-popover-arrow-${placement}`);
    if (placement === 'top' || placement === 'bottom') {
        const arrowLeft = clampAppTourValue(centerX - left, 24, popoverWidth - 24);
        popover.style.setProperty('--tour-arrow-left', `${arrowLeft}px`);
    } else {
        const arrowTop = clampAppTourValue(centerY - top, 24, popoverHeight - 24);
        popover.style.setProperty('--tour-arrow-top', `${arrowTop}px`);
    }
}

function closeAppTour(save = true) {
    if (appTourIsRequired && !save) {
        return;
    }

    const highlight = document.getElementById('app-tour-highlighter');
    const backdrop = document.getElementById('app-tour-backdrop');
    const popover = document.getElementById('app-tour-popover');
    const popoverArrow = document.getElementById('app-tour-popover-arrow');

    if (appTourResizeTimeoutId) {
        window.clearTimeout(appTourResizeTimeoutId);
        appTourResizeTimeoutId = null;
    }

    cleanupAppTourManagedSidebar().finally(() => {
        highlight?.classList.add('app-hidden');
        backdrop?.classList.add('app-hidden');
        popover?.classList.add('app-hidden');
        if (popover) {
            resetAppTourPopoverPlacement(popover, popoverArrow);
        }
        setAppTourScrollLock(false);
    });
    if (save) {
        const storageKey = getAppTourStorageKey();
        if (storageKey) {
            localStorage.setItem(storageKey, 'true');
        }
        if (appTourIsRequired) {
            markAppTourCompleted();
        }
    }
    appTourIsRequired = false;
}

async function maybeStartAppTour() {
    if (!currentUserCanAccessAppTour()) {
        hideAppTourNudge();
        return;
    }

    if (shouldRequireAppTour()) {
        appTourSteps = getAppTourSteps();
        if (appTourSteps.length) {
            await openAppTour({ forceRequired: true });
        }
        hideAppTourNudge();
        return;
    }

    if (shouldShowAppTourNudge()) {
        showAppTourNudge();
    } else {
        hideAppTourNudge();
    }
}

async function renderAppTourStep(index) {
    if (!appTourSteps || index < 0 || index >= appTourSteps.length) {
        closeAppTour(true);
        return;
    }

    appTourCurrentIndex = index;
    const step = appTourSteps[index];
    if (step.tab) {
        await activateTab(step.tab);
    }

    const highlight = document.getElementById('app-tour-highlighter');
    const backdrop = document.getElementById('app-tour-backdrop');
    const popover = document.getElementById('app-tour-popover');
    const popoverTitle = document.getElementById('app-tour-popover-title');
    const popoverBody = document.getElementById('app-tour-popover-body');
    const stepCount = document.getElementById('app-tour-step-count');
    const skipBtn = document.getElementById('app-tour-skip-btn');
    const prevBtn = document.getElementById('app-tour-prev-btn');
    const nextBtn = document.getElementById('app-tour-next-btn');
    const popoverArrow = document.getElementById('app-tour-popover-arrow');
    const closeBtn = document.getElementById('app-tour-close-btn');

    if (!highlight || !backdrop || !popover || !popoverTitle || !popoverBody || !stepCount || !skipBtn || !prevBtn || !nextBtn) {
        return;
    }

    await cleanupAppTourManagedSidebar();
    await prepareAppTourStep(step);

    backdrop.classList.remove('app-hidden');
    highlight.classList.remove('app-hidden');
    popover.classList.remove('app-hidden');
    setAppTourScrollLock(true);
    resetAppTourPopoverPlacement(popover, popoverArrow);
    popoverTitle.textContent = step.title;
    popoverBody.textContent = step.body;
    stepCount.textContent = `${index + 1} of ${appTourSteps.length}`;
    prevBtn.disabled = index === 0;
    nextBtn.textContent = index === appTourSteps.length - 1 ? 'Finish' : 'Next';
    if (closeBtn) {
        closeBtn.hidden = appTourIsRequired;
        closeBtn.disabled = appTourIsRequired;
    }

    skipBtn.onclick = () => closeAppTour(true);
    prevBtn.onclick = () => moveAppTourStep(index - 1, prevBtn);
    nextBtn.onclick = () => moveAppTourStep(index + 1, nextBtn);

    const target = step.selector ? document.querySelector(step.selector) : null;
    if (target && isElementVisible(target)) {
        await scrollAppTourTargetIntoView(target);
        const rect = target.getBoundingClientRect();
        applyAppTourHighlight(highlight, rect);
        positionAppTourPopover(popover, popoverArrow, rect);
    } else {
        highlight.style.top = '50%';
        highlight.style.left = '50%';
        highlight.style.width = '0px';
        highlight.style.height = '0px';
        highlight.style.borderRadius = '50%';
        resetAppTourPopoverPlacement(popover, popoverArrow);
        popover.style.transform = 'translate(-50%, -50%)';
        popover.style.top = '50%';
        popover.style.left = '50%';
    }
}

async function moveAppTourStep(index, button) {
    if (appTourStepTransitionInFlight) {
        return;
    }

    const runTransition = async () => {
        appTourStepTransitionInFlight = true;
        try {
            await renderAppTourStep(index);
        } finally {
            appTourStepTransitionInFlight = false;
        }
    };

    if (isLockableButton(button)) {
        await withButtonLock(button, runTransition);
    } else {
        await runTransition();
    }
}

// Setup UI based on role
function setupRoleBasedUI() {
    const isAdmin = currentUserIsAdminCapable();
    const isPantryLead = currentUserHasRole('PANTRY_LEAD');
    const isVolunteer = currentUserHasRole('VOLUNTEER');
    const calendarTab = document.querySelector('.nav-tab[data-tab="calendar"]');
    const calendarContent = document.getElementById('content-calendar');
    const shiftsTab = document.getElementById('tab-shifts');
    const adminTab = document.getElementById('tab-admin');
    const pantriesTab = document.getElementById('tab-pantries');
    const myShiftsTab = document.getElementById('tab-my-shifts');
    const startTourButton = document.getElementById('start-tour-btn');
    let defaultTab = 'calendar';

    const hideCalendarForLead = isPantryLead && !isAdmin && !isVolunteer;
    if (calendarTab) {
        calendarTab.classList.toggle('hidden', hideCalendarForLead);
        if (hideCalendarForLead) {
            calendarContent?.classList.remove('active');
            defaultTab = 'shifts';
        }
    }

    shiftsTab?.classList.toggle('hidden', !(isAdmin || isPantryLead));
    adminTab?.classList.toggle('hidden', !isAdmin);
    pantriesTab?.classList.toggle('hidden', !isVolunteer);
    myShiftsTab?.classList.toggle('hidden', !isVolunteer);
    if (startTourButton) {
        const canAccessAppTour = currentUserCanAccessAppTour();
        startTourButton.hidden = !canAccessAppTour;
        startTourButton.classList.toggle('app-hidden', !canAccessAppTour);
    }
    if (!currentUserCanAccessAppTour()) {
        hideAppTourNudge();
    }

    return defaultTab;
}

async function activateTab(targetTab) {
    // Update active tab style
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    const targetButton = document.querySelector(`.nav-tab[data-tab="${targetTab}"]`);
    targetButton?.classList.add('active');

    // Show target content
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
    });
    document.getElementById(`content-${targetTab}`)?.classList.add('active');

    // Show/hide pantry selector based on tab
    const pantrySelector = document.getElementById('pantry-selector');
    if (pantrySelector) {
        const shouldHideSelector = targetTab === 'calendar' || targetTab === 'pantries' || targetTab === 'my-shifts' || targetTab === 'my-account' || targetTab === 'admin';
        pantrySelector.classList.toggle('app-hidden', shouldHideSelector);
    }

    // Load tab-specific data
    if (targetTab === 'shifts') {
        setManageShiftsSubtab(activeManageShiftsSubtab);
        await loadShiftsTable();
    } else if (targetTab === 'admin') {
        setAdminSubtab(activeAdminSubtab);
        await loadAdminTab();
    } else if (targetTab === 'my-shifts') {
        setMyShiftsViewMode('calendar');
        await loadMyRegisteredShifts();
    } else if (targetTab === 'pantries') {
        await loadVolunteerPantryDirectory();
    } else if (targetTab === 'my-account') {
        await loadMyAccount();
    } else if (targetTab === 'calendar') {
        await loadCalendarShifts();
    }
}

// Load pantries
async function loadPantries() {
    try {
        allPantries = await getPantries();
        allPublicPantries = await getAllPantries();
        const select = document.getElementById('pantry-select');
        const selectedPantryStillExists = allPantries.some(pantry => pantry.pantry_id === currentPantryId);

        select.innerHTML = '';

        if (allPantries.length === 0) {
            currentPantryId = null;
            selectedAdminPantryId = null;
            select.innerHTML = '<option value="">No pantries available</option>';
            clearSelectedAssignPantry(false);
            if (typeof syncCalendarPantryOptions === 'function') {
                syncCalendarPantryOptions();
            }
            if (currentUserIsAdminCapable()) {
                await updatePantriesTable();
            }
            return;
        }

        allPantries.forEach(pantry => {
            const opt = document.createElement('option');
            opt.value = pantry.pantry_id;
            opt.textContent = pantry.name;
            select.appendChild(opt);
        });

        currentPantryId = selectedPantryStillExists ? currentPantryId : allPantries[0].pantry_id;
        if (currentUserIsAdminCapable()) {
            const selectedAdminPantryStillExists = allPantries.some(pantry => intValue(pantry.pantry_id) === intValue(selectedAdminPantryId));
            selectedAdminPantryId = selectedAdminPantryStillExists ? selectedAdminPantryId : allPantries[0].pantry_id;
        }
        select.value = currentPantryId;
        clearSelectedAssignPantry(false);
        renderAssignPantrySearchResults();
        if (typeof syncCalendarPantryOptions === 'function') {
            syncCalendarPantryOptions();
        }

        // Load pantry leads for admin
        if (currentUserIsAdminCapable()) {
            await loadPantryLeads();
        }
    } catch (error) {
        console.error('Failed to load pantries:', error);
        showMessage('calendar', `Failed to load pantries: ${error.message}`, 'error');
    }
}

// Load pantry leads (admin)
async function loadPantryLeads() {
    try {
        pantryLeadUsers = await getAllUsers('PANTRY_LEAD');
        clearSelectedPantryLead(false);
        renderPantryLeadSearchResults();

        // Update pantries table
        await updatePantriesTable();
    } catch (error) {
        console.error('Failed to load leads:', error);
    }
}

function getFilteredVolunteerPantries() {
    const search = volunteerPantrySearchQuery.toLowerCase();
    const filtered = volunteerPantryDirectory.filter((pantry) => {
        if (volunteerPantrySubscriptionFilter === 'subscribed' && !pantry.is_subscribed) {
            return false;
        }
        if (volunteerPantrySubscriptionFilter === 'unsubscribed' && pantry.is_subscribed) {
            return false;
        }
        if (!search) {
            return true;
        }

        const name = String(pantry.name || '').toLowerCase();
        const address = String(pantry.location_address || '').toLowerCase();
        return name.includes(search) || address.includes(search);
    });

    filtered.sort((left, right) => {
        const nameComparison = String(left.name || '').localeCompare(String(right.name || ''), undefined, { sensitivity: 'base' });
        if (volunteerPantrySort === 'name-desc') {
            return nameComparison * -1;
        }
        return nameComparison;
    });

    return filtered;
}

function updateVolunteerPantryFilterUi() {
    document.querySelectorAll('[data-pantry-subscription-filter]').forEach((button) => {
        button.classList.toggle('active', button.dataset.pantrySubscriptionFilter === volunteerPantrySubscriptionFilter);
    });

    const summary = document.getElementById('volunteer-pantries-summary');
    if (!summary) {
        return;
    }

    const filtered = getFilteredVolunteerPantries();
    const total = volunteerPantryDirectory.length;
    const qualifier = volunteerPantrySearchQuery ? ` matching "${volunteerPantrySearchQuery}"` : '';
    summary.textContent = `${filtered.length} of ${total} ${total === 1 ? 'pantry' : 'pantries'} shown${qualifier}.`;
}

function isVolunteerPantryCompactViewport() {
    return window.matchMedia('(max-width: 1023px)').matches;
}

function buildVolunteerPantryDetailMarkup(pantry, options = {}) {
    const inline = Boolean(options.inline);
    const leads = Array.isArray(pantry.leads) ? pantry.leads : [];
    const previewShifts = Array.isArray(pantry.preview_shifts) ? pantry.preview_shifts.slice(0, 1) : [];
    const remainingShiftCount = Math.max(0, Number(pantry.upcoming_shift_count || 0) - previewShifts.length);

    return `
        <div class="volunteer-pantry-detail-head">
            <div>
                <h2 class="volunteer-pantry-detail-title">${escapeHtml(pantry.name || 'Unnamed Pantry')}</h2>
                <p class="volunteer-pantry-detail-address">${escapeHtml(pantry.location_address || 'No address')}</p>
            </div>
            <button
                type="button"
                class="btn ${pantry.is_subscribed ? 'btn-secondary' : 'btn-primary'}"
                data-volunteer-subscribe-id="${pantry.pantry_id}"
                data-subscribed="${pantry.is_subscribed ? 'true' : 'false'}"
            >
                ${pantry.is_subscribed ? 'Unsubscribe' : 'Subscribe'}
            </button>
        </div>
        <div class="volunteer-pantry-detail-section">
            <h3>Pantry Leads</h3>
            ${leads.length > 0
                ? `<div class="volunteer-pantry-leads">${leads.map((lead) => `<span class="volunteer-pantry-lead-pill">${escapeHtml(lead.full_name || lead.email || 'Assigned lead')}</span>`).join('')}</div>`
                : '<p class="volunteer-pantry-preview-empty">No pantry leads listed yet.</p>'}
        </div>
        <div class="volunteer-pantry-detail-section">
            <h3>${inline ? 'Next Incoming Shift' : 'Next Incoming Shift'}</h3>
            ${previewShifts.length > 0
                ? `<div class="volunteer-pantry-preview-list">${previewShifts.map((shift) => `
                    <div class="volunteer-pantry-preview-item">
                        <div class="volunteer-pantry-preview-item-title">${escapeHtml(shift.shift_name || 'Untitled Shift')}</div>
                        <div class="volunteer-pantry-preview-item-time">${escapeHtml(formatLocalTimeRange(shift.start_time, shift.end_time))}</div>
                        <div class="volunteer-pantry-preview-item-meta">${escapeHtml(renderCalendarRoleSummary(shift.roles || []))}</div>
                    </div>
                `).join('')}</div>
                ${remainingShiftCount > 0 ? `<p class="volunteer-pantry-preview-more">${remainingShiftCount} more upcoming shift${remainingShiftCount === 1 ? '' : 's'}.</p>` : ''}`
                : '<p class="volunteer-pantry-preview-empty">No upcoming shifts are posted yet.</p>'}
        </div>
    `;
}

function renderVolunteerPantryList() {
    const listEl = document.getElementById('volunteer-pantries-list');
    if (!listEl) {
        return;
    }

    const filtered = getFilteredVolunteerPantries();
    const compactView = isVolunteerPantryCompactViewport();
    updateVolunteerPantryFilterUi();

    const countEl = document.getElementById('pantry-directory-count');
    if (countEl) {
        const total = volunteerPantryDirectory.length;
        countEl.textContent = filtered.length === total
            ? `${total} pantry${total === 1 ? '' : 's'}`
            : `${filtered.length} of ${total} pantry${total === 1 ? '' : 's'}`;
    }

    if (filtered.length === 0) {
        listEl.innerHTML = '<p class="empty-state">No pantries match the current filters.</p>';
        return;
    }

    listEl.innerHTML = filtered.map((pantry) => {
        const isSelected = Number(pantry.pantry_id) === Number(selectedVolunteerPantryId);
        const toggleLabel = compactView && isSelected ? 'Tap to hide details' : 'Tap to view details';
        return `
            <div class="volunteer-pantry-list-entry${compactView && isSelected ? ' is-selected' : ''}">
                <button type="button" class="volunteer-pantry-list-card${isSelected ? ' is-selected' : ''}" data-volunteer-pantry-id="${pantry.pantry_id}">
                    <div class="volunteer-pantry-list-head">
                        <div>
                            <div class="volunteer-pantry-list-name">${escapeHtml(pantry.name || 'Unnamed Pantry')}</div>
                            <div class="volunteer-pantry-list-address">${escapeHtml(pantry.location_address || 'No address')}</div>
                        </div>
                        <span class="volunteer-pantry-pill${pantry.is_subscribed ? ' is-subscribed' : ''}">${pantry.is_subscribed ? 'Subscribed' : 'Not subscribed'}</span>
                    </div>
                    <div class="volunteer-pantry-list-meta">
                        <span>${Number(pantry.upcoming_shift_count || 0)} upcoming shift${Number(pantry.upcoming_shift_count || 0) === 1 ? '' : 's'}</span>
                        <span>${Array.isArray(pantry.leads) && pantry.leads.length > 0 ? `${pantry.leads.length} lead${pantry.leads.length === 1 ? '' : 's'}` : 'No assigned leads'}</span>
                    </div>
                    ${compactView ? `<div class="volunteer-pantry-list-hint">${toggleLabel}</div>` : ''}
                </button>
                ${compactView && isSelected
                    ? `<div class="volunteer-pantry-detail-card volunteer-pantry-detail-card-inline">${buildVolunteerPantryDetailMarkup(pantry, { inline: true })}</div>`
                    : ''}
            </div>
        `;
    }).join('');
}

function renderVolunteerPantryDetail() {
    const detailEl = document.getElementById('volunteer-pantry-detail');
    if (!detailEl) {
        return;
    }

    if (isVolunteerPantryCompactViewport()) {
        detailEl.innerHTML = '';
        return;
    }

    const pantry = volunteerPantryDirectory.find((item) => Number(item.pantry_id) === Number(selectedVolunteerPantryId));
    if (!pantry) {
        detailEl.innerHTML = '<p class="auth-empty">Select a pantry to see its details and upcoming shifts.</p>';
        return;
    }

    detailEl.innerHTML = buildVolunteerPantryDetailMarkup(pantry);
}

function renderVolunteerPantryDirectory() {
    const filteredPantries = getFilteredVolunteerPantries();
    const availablePantryIds = new Set(filteredPantries.map((pantry) => Number(pantry.pantry_id)));
    if (!selectedVolunteerPantryId || !availablePantryIds.has(Number(selectedVolunteerPantryId))) {
        selectedVolunteerPantryId = filteredPantries.length > 0 ? Number(filteredPantries[0].pantry_id) : null;
    }
    renderVolunteerPantryList();
    renderVolunteerPantryDetail();
}

async function loadVolunteerPantryDirectory() {
    const listEl = document.getElementById('volunteer-pantries-list');
    const detailEl = document.getElementById('volunteer-pantry-detail');
    if (!listEl || !detailEl) {
        return;
    }

    const searchInput = document.getElementById('volunteer-pantry-search');
    const sortInput = document.getElementById('volunteer-pantry-sort');
    if (searchInput && searchInput.value !== volunteerPantrySearchQuery) {
        searchInput.value = volunteerPantrySearchQuery;
    }
    if (sortInput) {
        sortInput.value = volunteerPantrySort;
    }

    listEl.innerHTML = '<div class="loading"><div class="spinner"></div><p>Loading pantry directory...</p></div>';
    detailEl.innerHTML = '<p class="auth-empty">Loading pantry details...</p>';

    try {
        volunteerPantryDirectory = await getVolunteerPantries();
        renderVolunteerPantryDirectory();
    } catch (error) {
        volunteerPantryDirectory = [];
        listEl.innerHTML = `<p class="empty-state">Failed to load pantries: ${escapeHtml(error.message)}</p>`;
        detailEl.innerHTML = '<p class="auth-empty">Pantry details are unavailable right now.</p>';
        showMessage('pantries', `Failed to load pantries: ${error.message}`, 'error');
    }
}

function updateVolunteerPantryDirectoryState(pantryId, isSubscribed) {
    volunteerPantryDirectory = volunteerPantryDirectory.map((pantry) => (
        Number(pantry.pantry_id) === Number(pantryId)
            ? { ...pantry, is_subscribed: isSubscribed }
            : pantry
    ));
    renderVolunteerPantryDirectory();
}

async function toggleVolunteerPantrySubscription(buttonEl) {
    const pantryId = Number(buttonEl.dataset.volunteerSubscribeId || 0);
    if (!pantryId) {
        return;
    }

    await withButtonLock(buttonEl, async () => {
        const isSubscribed = buttonEl.dataset.subscribed === 'true';
        try {
            if (isSubscribed) {
                await unsubscribeFromPantry(pantryId);
                updateVolunteerPantryDirectoryState(pantryId, false);
                showMessage('pantries', 'Pantry unsubscribed successfully.', 'success');
            } else {
                await subscribeToPantry(pantryId);
                updateVolunteerPantryDirectoryState(pantryId, true);
                showMessage('pantries', 'Pantry subscribed successfully.', 'success');
            }
        } catch (error) {
            showMessage('pantries', `Subscription update failed: ${error.message}`, 'error');
        }
    });
}

function handleVolunteerPantriesViewportChange() {
    const compactView = isVolunteerPantryCompactViewport();
    if (lastVolunteerPantriesCompactViewport === compactView) {
        return;
    }

    lastVolunteerPantriesCompactViewport = compactView;
    renderVolunteerPantryDirectory();
}

function getAssignPantrySearchMatches(query) {
    const normalizedQuery = String(query || '').trim().toLowerCase();
    if (!normalizedQuery) {
        return allPantries.slice(0, 8);
    }

    return allPantries
        .filter((pantry) => {
            const name = String(pantry.name || '').toLowerCase();
            const address = String(pantry.location_address || '').toLowerCase();
            return name.includes(normalizedQuery) || address.includes(normalizedQuery);
        })
        .slice(0, 8);
}

function renderAssignPantrySearchResults() {
    const resultsEl = document.getElementById('assign-pantry-results');
    const searchInput = document.getElementById('assign-pantry-search');
    if (!resultsEl || !searchInput) {
        return;
    }

    if (selectedAssignPantryId) {
        resultsEl.innerHTML = '';
        resultsEl.classList.add('app-hidden');
        return;
    }

    const matches = getAssignPantrySearchMatches(searchInput.value);
    if (matches.length === 0) {
        resultsEl.innerHTML = '<div class="pantry-search-empty">No pantries match that search.</div>';
        resultsEl.classList.remove('app-hidden');
        return;
    }

    resultsEl.innerHTML = matches.map((pantry) => `
        <button type="button" class="pantry-search-result" data-pantry-option-id="${pantry.pantry_id}">
            <span class="pantry-search-result-name">${escapeHtml(pantry.name || 'Unnamed Pantry')}</span>
            <span class="pantry-search-result-address">${escapeHtml(pantry.location_address || 'No address')}</span>
        </button>
    `).join('');
    resultsEl.classList.remove('app-hidden');
}

function selectAssignPantry(pantryId) {
    const pantry = allPantries.find((item) => intValue(item.pantry_id) === intValue(pantryId));
    const hiddenInput = document.getElementById('assign-pantry');
    const selectedEl = document.getElementById('assign-pantry-selected');
    const searchInput = document.getElementById('assign-pantry-search');
    const resultsEl = document.getElementById('assign-pantry-results');
    if (!pantry || !hiddenInput || !selectedEl || !searchInput || !resultsEl) {
        return;
    }

    selectedAssignPantryId = intValue(pantry.pantry_id);
    hiddenInput.value = String(selectedAssignPantryId);
    searchInput.value = '';
    selectedEl.innerHTML = `
        <div>
            <div class="pantry-search-selected-name">${escapeHtml(pantry.name || 'Unnamed Pantry')}</div>
            <div class="pantry-search-selected-address">${escapeHtml(pantry.location_address || 'No address')}</div>
        </div>
        <button type="button" class="pantry-search-clear" id="assign-pantry-clear-btn" aria-label="Clear selected pantry">&times;</button>
    `;
    selectedEl.classList.remove('app-hidden');
    resultsEl.innerHTML = '';
    resultsEl.classList.add('app-hidden');

    document.getElementById('assign-pantry-clear-btn')?.addEventListener('click', () => {
        clearSelectedAssignPantry(true);
    });
}

function clearSelectedAssignPantry(shouldRefocus = false) {
    selectedAssignPantryId = null;
    const hiddenInput = document.getElementById('assign-pantry');
    const selectedEl = document.getElementById('assign-pantry-selected');
    const searchInput = document.getElementById('assign-pantry-search');
    const resultsEl = document.getElementById('assign-pantry-results');
    if (hiddenInput) {
        hiddenInput.value = '';
    }
    if (selectedEl) {
        selectedEl.innerHTML = '';
        selectedEl.classList.add('app-hidden');
    }
    if (resultsEl) {
        resultsEl.innerHTML = '';
        resultsEl.classList.add('app-hidden');
    }
    if (searchInput) {
        if (shouldRefocus) {
            searchInput.focus();
        }
        renderAssignPantrySearchResults();
    }
}

function getPantryLeadSearchMatches(query) {
    const normalizedQuery = String(query || '').trim().toLowerCase();
    if (!normalizedQuery) {
        return pantryLeadUsers.slice(0, 8);
    }

    return pantryLeadUsers
        .filter((lead) => {
            const fullName = String(lead.full_name || '').toLowerCase();
            const email = String(lead.email || '').toLowerCase();
            return fullName.includes(normalizedQuery) || email.includes(normalizedQuery);
        })
        .slice(0, 8);
}

function renderPantryLeadSearchResults() {
    const resultsEl = document.getElementById('assign-lead-results');
    const searchInput = document.getElementById('assign-lead-search');
    if (!resultsEl || !searchInput) {
        return;
    }

    if (selectedPantryLeadId) {
        resultsEl.innerHTML = '';
        resultsEl.classList.add('app-hidden');
        return;
    }

    const matches = getPantryLeadSearchMatches(searchInput.value);
    if (matches.length === 0) {
        resultsEl.innerHTML = '<div class="lead-search-empty">No pantry leads match that search.</div>';
        resultsEl.classList.remove('app-hidden');
        return;
    }

    resultsEl.innerHTML = matches.map((lead) => `
        <button type="button" class="lead-search-result" data-lead-option-id="${lead.user_id}">
            <span class="lead-search-result-name">${escapeHtml(lead.full_name || 'Unnamed User')}</span>
            <span class="lead-search-result-email">${escapeHtml(lead.email || 'No email')}</span>
        </button>
    `).join('');
    resultsEl.classList.remove('app-hidden');
}

function selectPantryLead(leadId) {
    const lead = pantryLeadUsers.find((item) => intValue(item.user_id) === intValue(leadId));
    const hiddenInput = document.getElementById('assign-lead');
    const selectedEl = document.getElementById('assign-lead-selected');
    const searchInput = document.getElementById('assign-lead-search');
    const resultsEl = document.getElementById('assign-lead-results');
    if (!lead || !hiddenInput || !selectedEl || !searchInput || !resultsEl) {
        return;
    }

    selectedPantryLeadId = intValue(lead.user_id);
    hiddenInput.value = String(selectedPantryLeadId);
    searchInput.value = '';
    selectedEl.innerHTML = `
        <div>
            <div class="lead-search-selected-name">${escapeHtml(lead.full_name || 'Unnamed User')}</div>
            <div class="lead-search-selected-email">${escapeHtml(lead.email || 'No email')}</div>
        </div>
        <button type="button" class="lead-search-clear" id="assign-lead-clear-btn" aria-label="Clear selected pantry lead">&times;</button>
    `;
    selectedEl.classList.remove('app-hidden');
    resultsEl.innerHTML = '';
    resultsEl.classList.add('app-hidden');

    document.getElementById('assign-lead-clear-btn')?.addEventListener('click', () => {
        clearSelectedPantryLead(true);
    });
}

function clearSelectedPantryLead(shouldRefocus = false) {
    selectedPantryLeadId = null;
    const hiddenInput = document.getElementById('assign-lead');
    const selectedEl = document.getElementById('assign-lead-selected');
    const searchInput = document.getElementById('assign-lead-search');
    const resultsEl = document.getElementById('assign-lead-results');
    if (hiddenInput) {
        hiddenInput.value = '';
    }
    if (selectedEl) {
        selectedEl.innerHTML = '';
        selectedEl.classList.add('app-hidden');
    }
    if (resultsEl) {
        resultsEl.innerHTML = '';
        resultsEl.classList.add('app-hidden');
    }
    if (searchInput) {
        if (shouldRefocus) {
            searchInput.focus();
        }
        renderPantryLeadSearchResults();
    }
}

function getAdminPantryById(pantryId) {
    return allPantries.find((pantry) => intValue(pantry.pantry_id) === intValue(pantryId)) || null;
}

function getAdminPantryLeadIds(pantry) {
    return new Set((Array.isArray(pantry?.leads) ? pantry.leads : []).map((lead) => intValue(lead.user_id)));
}

function getFilteredAdminPantries() {
    const normalizedQuery = String(adminPantrySearchQuery || '').trim().toLowerCase();
    const pantries = normalizedQuery
        ? allPantries.filter((pantry) => {
            const name = String(pantry.name || '').toLowerCase();
            const address = String(pantry.location_address || '').toLowerCase();
            return name.includes(normalizedQuery) || address.includes(normalizedQuery);
        })
        : allPantries.slice();

    return pantries.sort((left, right) => String(left.name || '').localeCompare(String(right.name || ''), undefined, { sensitivity: 'base' }));
}

function getAvailableAdminPantryLeadMatches() {
    const selectedPantry = getAdminPantryById(selectedAdminPantryId);
    if (!selectedPantry) {
        return [];
    }

    const assignedLeadIds = getAdminPantryLeadIds(selectedPantry);
    const normalizedQuery = String(adminPantryLeadSearchQuery || '').trim().toLowerCase();
    return pantryLeadUsers
        .filter((lead) => !assignedLeadIds.has(intValue(lead.user_id)))
        .filter((lead) => {
            if (!normalizedQuery) {
                return true;
            }
            const fullName = String(lead.full_name || '').toLowerCase();
            const email = String(lead.email || '').toLowerCase();
            return fullName.includes(normalizedQuery) || email.includes(normalizedQuery);
        })
        .slice(0, 8);
}

function renderAdminPantryList() {
    const listEl = document.getElementById('admin-pantries-list');
    if (!listEl) {
        return;
    }

    const filteredPantries = getFilteredAdminPantries();
    if (!selectedAdminPantryId && filteredPantries.length > 0) {
        selectedAdminPantryId = intValue(filteredPantries[0].pantry_id);
    }
    if (selectedAdminPantryId && !allPantries.some((pantry) => intValue(pantry.pantry_id) === intValue(selectedAdminPantryId))) {
        selectedAdminPantryId = filteredPantries.length > 0 ? intValue(filteredPantries[0].pantry_id) : null;
    }

    if (allPantries.length === 0) {
        listEl.innerHTML = '<p class="empty-state">No pantries yet. Create a pantry above to start assigning leads.</p>';
        return;
    }

    if (filteredPantries.length === 0) {
        listEl.innerHTML = '<p class="empty-state">No pantries match the current search.</p>';
        return;
    }

    listEl.innerHTML = filteredPantries.map((pantry) => {
        const leads = Array.isArray(pantry.leads) ? pantry.leads : [];
        const isSelected = intValue(pantry.pantry_id) === intValue(selectedAdminPantryId);
        return `
            <button type="button" class="admin-pantry-card ${isSelected ? 'selected' : ''}" data-admin-pantry-id="${pantry.pantry_id}">
                <div class="admin-pantry-card-main">
                    <span class="admin-pantry-card-name">${escapeHtml(pantry.name || 'Unnamed Pantry')}</span>
                    <span class="admin-pantry-card-address">${escapeHtml(pantry.location_address || 'No address')}</span>
                </div>
                <span class="admin-pantry-card-count">${leads.length} lead${leads.length === 1 ? '' : 's'}</span>
            </button>
        `;
    }).join('');
}

function renderAdminPantryLeadSearchResults() {
    const resultsEl = document.getElementById('admin-pantry-lead-results');
    const searchInput = document.getElementById('admin-pantry-lead-search');
    if (!resultsEl || !searchInput) {
        return;
    }

    if (!String(searchInput.value || '').trim()) {
        resultsEl.innerHTML = '';
        resultsEl.classList.add('app-hidden');
        return;
    }

    const matches = getAvailableAdminPantryLeadMatches();
    if (matches.length === 0) {
        const selectedPantry = getAdminPantryById(selectedAdminPantryId);
        const assignedLeadIds = getAdminPantryLeadIds(selectedPantry);
        const allEligibleAssigned = pantryLeadUsers.length > 0 && assignedLeadIds.size >= pantryLeadUsers.length;
        resultsEl.innerHTML = `<p class="admin-pantry-lead-empty">${allEligibleAssigned ? 'All pantry leads are already assigned here.' : 'No pantry leads match that search.'}</p>`;
        resultsEl.classList.remove('app-hidden');
        return;
    }

    resultsEl.innerHTML = matches.map((lead) => `
        <button type="button" class="admin-pantry-lead-option" data-add-admin-pantry-lead="${lead.user_id}" ${adminPantryLeadActionInFlight ? 'disabled' : ''}>
            <span class="admin-pantry-lead-name">${escapeHtml(lead.full_name || 'Unnamed User')}</span>
            <span class="admin-pantry-lead-email">${escapeHtml(lead.email || 'No email')}</span>
        </button>
    `).join('');
    resultsEl.classList.remove('app-hidden');
}

function buildAdminPantryLeadListMarkup(pantry) {
    const leads = Array.isArray(pantry.leads) ? pantry.leads : [];
    if (leads.length === 0) {
        return '<p class="admin-pantry-lead-empty">No leads assigned yet. Search below to add pantry leads.</p>';
    }

    return `
        <div class="admin-pantry-assigned-leads">
            ${leads.map((lead) => `
                <div class="admin-pantry-assigned-lead">
                    <div>
                        <div class="admin-pantry-lead-name">${escapeHtml(lead.full_name || 'Unnamed User')}</div>
                        <div class="admin-pantry-lead-email">${escapeHtml(lead.email || 'No email')}</div>
                    </div>
                    <button type="button" class="btn btn-danger btn-sm" data-remove-admin-pantry-lead="${lead.user_id}" ${adminPantryLeadActionInFlight ? 'disabled' : ''}>Remove</button>
                </div>
            `).join('')}
        </div>
    `;
}

function renderAdminPantryDetail() {
    const panel = document.getElementById('admin-pantry-detail-panel');
    if (!panel) {
        return;
    }

    const pantry = getAdminPantryById(selectedAdminPantryId);
    if (!pantry) {
        panel.innerHTML = '<p class="auth-empty">Select a pantry to view and manage its assigned leads.</p>';
        return;
    }

    const leads = Array.isArray(pantry.leads) ? pantry.leads : [];
    panel.innerHTML = `
        <div class="admin-pantry-detail">
            <div class="admin-pantry-detail-header">
                <div>
                    <h3>${escapeHtml(pantry.name || 'Unnamed Pantry')}</h3>
                    <p>${escapeHtml(pantry.location_address || 'No address')}</p>
                </div>
                <div class="admin-pantry-detail-actions">
                    <button type="button" class="btn btn-secondary btn-sm" data-edit-admin-pantry="${pantry.pantry_id}">Edit</button>
                    <button type="button" class="btn btn-danger btn-sm" data-delete-admin-pantry="${pantry.pantry_id}">Delete</button>
                </div>
            </div>
            <div class="admin-pantry-lead-section">
                <div class="admin-pantry-section-heading">
                    <h4>Assigned Leads</h4>
                    <span>${leads.length} total</span>
                </div>
                ${buildAdminPantryLeadListMarkup(pantry)}
            </div>
            <div class="admin-pantry-lead-section">
                <div class="form-group">
                    <label for="admin-pantry-lead-search">Add Pantry Lead</label>
                    <input type="search" id="admin-pantry-lead-search" placeholder="Search by full name or email" autocomplete="off" value="${escapeHtml(adminPantryLeadSearchQuery)}" ${adminPantryLeadActionInFlight ? 'disabled' : ''}>
                </div>
                <div id="admin-pantry-lead-results" class="admin-pantry-lead-results"></div>
            </div>
        </div>
    `;

    renderAdminPantryLeadSearchResults();
}

function renderAdminPantryWorkspace() {
    renderAdminPantryList();
    renderAdminPantryDetail();
}

function openEditPantryModal(pantry) {
    if (!pantry) {
        return;
    }
    document.getElementById('edit-pantry-id').value = pantry.pantry_id;
    document.getElementById('edit-pantry-name').value = pantry.name || '';
    document.getElementById('edit-pantry-address').value = pantry.location_address || '';
    document.getElementById('edit-pantry-modal').classList.remove('app-hidden');
}

async function deleteAdminPantry(pantryId, buttonEl = null) {
    const pantry = getAdminPantryById(pantryId);
    if (!pantry) {
        return;
    }

    const confirmed = window.confirm(
        `Delete pantry "${pantry.name || 'Unnamed Pantry'}"? This will also remove its shifts, roles, signups, and lead assignments.`
    );

    if (!confirmed) {
        return;
    }

    await withButtonLock(buttonEl, async () => {
        try {
            await deletePantry(pantryId);

            if (intValue(currentPantryId) === intValue(pantryId)) {
                currentPantryId = null;
                resetEditShiftForm();
            }
            if (intValue(selectedAdminPantryId) === intValue(pantryId)) {
                selectedAdminPantryId = null;
            }

            showMessage('pantry', 'Pantry deleted successfully!', 'success');
            await loadPantries();
        } catch (error) {
            showMessage('pantry', `Error: ${error.message}`, 'error');
        }
    });
}

async function assignAdminPantryLead(leadId, buttonEl = null) {
    if (!selectedAdminPantryId || !leadId || adminPantryLeadActionInFlight) {
        return;
    }

    await withButtonLock(buttonEl, async () => {
        adminPantryLeadActionInFlight = true;
        renderAdminPantryDetail();

        try {
            await addPantryLead(selectedAdminPantryId, leadId);
            adminPantryLeadSearchQuery = '';
            showMessage('assign', 'Lead assigned successfully!', 'success');
            await loadPantries();
        } catch (error) {
            showMessage('assign', `Error: ${error.message}`, 'error');
        } finally {
            adminPantryLeadActionInFlight = false;
            renderAdminPantryWorkspace();
        }
    });
}

async function removeAdminPantryLead(leadId, buttonEl = null) {
    if (!selectedAdminPantryId || !leadId || adminPantryLeadActionInFlight) {
        return;
    }

    const selectedPantry = getAdminPantryById(selectedAdminPantryId);
    const lead = (selectedPantry?.leads || []).find((item) => intValue(item.user_id) === intValue(leadId));
    const confirmed = window.confirm(`Remove ${lead?.full_name || lead?.email || 'this lead'} from this pantry?`);
    if (!confirmed) {
        return;
    }

    await withButtonLock(buttonEl, async () => {
        adminPantryLeadActionInFlight = true;
        renderAdminPantryDetail();

        try {
            await removePantryLead(selectedAdminPantryId, leadId);
            showMessage('assign', 'Lead removed successfully!', 'success');
            await loadPantries();
        } catch (error) {
            showMessage('assign', `Error: ${error.message}`, 'error');
        } finally {
            adminPantryLeadActionInFlight = false;
            renderAdminPantryWorkspace();
        }
    });
}

// Update admin pantry workspace
async function updatePantriesTable() {
    renderAdminPantryWorkspace();
}

// Signup for role
async function signupForRole(roleId, buttonEl = null) {
    if (!currentUser || !currentUser.user_id) {
        showMessage('calendar', 'Signup failed: Missing current user context', 'error');
        return false;
    }

    return withButtonLock(buttonEl, async () => {
        try {
            await signupForShift(roleId, currentUser.user_id);
        } catch (error) {
            showMessage('calendar', `Signup failed: ${error.message}`, 'error');
            await loadCalendarShifts();
            return false;
        }

        try {
            const isVolunteer = currentUserHasRole('VOLUNTEER');
            if (isVolunteer) {
                await loadMyRegisteredShifts();
            }
            showMessage('calendar', 'Successfully signed up!', 'success');
        } catch (error) {
            showMessage('calendar', `Signup completed, but refresh failed: ${error.message}`, 'error');
        }

        await loadCalendarShifts(); // Reload to show updated counts no matter the error or success
        return true;
    });
}

function escapeHtml(value) {
    if (value === null || value === undefined) return '';
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function parseApiErrorDetails(error) {
    const raw = String(error && error.message ? error.message : '');
    const jsonStart = raw.indexOf('{');
    if (jsonStart === -1) return null;

    try {
        return JSON.parse(raw.slice(jsonStart));
    } catch (_err) {
        return null;
    }
}

function toStatusClass(prefix, status) {
    const normalized = String(status || 'unknown').toLowerCase().replace(/[^a-z0-9]+/g, '-');
    return `${prefix}-${normalized}`;
}

function safeDateValue(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
}

function sortByDate(a, b, field, direction = 'asc') {
    const aDate = safeDateValue(a[field]);
    const bDate = safeDateValue(b[field]);
    const aMs = aDate ? aDate.getTime() : Number.POSITIVE_INFINITY;
    const bMs = bDate ? bDate.getTime() : Number.POSITIVE_INFINITY;
    return direction === 'asc' ? aMs - bMs : bMs - aMs;
}

function classifyManagedShiftBucket(shift, now = new Date()) {
    const shiftStatus = String(shift.status || 'OPEN').toUpperCase();
    const start = safeDateValue(shift.start_time);
    const end = safeDateValue(shift.end_time);
    if (!start || !end) return 'past';

    // Cancelled shifts that already ended should be treated as past (locked),
    // not actionable cancelled shifts.
    if (shiftStatus === 'CANCELLED') {
        return end <= now ? 'past' : 'cancelled';
    }

    if (start > now) return 'incoming';
    if (start <= now && now < end) return 'ongoing';
    return 'past';
}

function getManagedShiftBuckets(shifts, now = new Date()) {
    const buckets = {
        incoming: [],
        ongoing: [],
        past: [],
        cancelled: [],
    };

    shifts.forEach((shift) => {
        const bucket = classifyManagedShiftBucket(shift, now);
        buckets[bucket].push(shift);
    });

    buckets.incoming.sort((a, b) => sortByDate(a, b, 'start_time', 'asc'));
    buckets.ongoing.sort((a, b) => sortByDate(a, b, 'end_time', 'asc'));
    buckets.past.sort((a, b) => sortByDate(a, b, 'end_time', 'desc'));
    buckets.cancelled.sort((a, b) => sortByDate(a, b, 'start_time', 'desc'));
    return buckets;
}

function isManageShiftsPhoneViewport() {
    return window.matchMedia(MANAGE_SHIFTS_PHONE_QUERY).matches;
}

function setManageShiftsMobileView(view = 'queue') {
    const normalized = ['queue', 'create', 'detail', 'edit'].includes(view) ? view : 'queue';
    managedShiftMobileView = normalized;
    const workspace = document.querySelector('.manage-shifts-workspace');
    if (workspace) {
        workspace.dataset.mobileView = normalized;
    }
}

function syncManageShiftsResponsiveView() {
    const workspace = document.querySelector('.manage-shifts-workspace');
    if (!workspace) return;
    workspace.dataset.mobileView = managedShiftMobileView;
}

function backToManagedShiftQueue() {
    if (managedShiftPanelMode === 'edit') {
        resetEditShiftForm({ preserveSelection: true });
    }
    setManageShiftsMobileView('queue');
    renderManageShiftsTable();
}

function setManageShiftsSubtab(target) {
    const normalized = ['detail', 'edit'].includes(target) ? target : (target === 'view' ? 'detail' : 'create');
    activeManageShiftsSubtab = normalized;
    managedShiftPanelMode = normalized;
    syncManageShiftsResponsiveView();

    document.querySelectorAll('.manage-shifts-subtab').forEach((btn) => {
        btn.classList.toggle('active', btn.dataset.manageSubtab === (normalized === 'create' ? 'create' : 'view'));
    });

    const createCard = document.getElementById('create-shift-card');
    const detailCard = document.getElementById('manage-shift-detail-card');
    const editCard = document.getElementById('edit-shift-card');
    createCard?.classList.toggle('app-hidden', normalized !== 'create');
    createCard?.classList.toggle('active', normalized === 'create');
    detailCard?.classList.toggle('app-hidden', normalized !== 'detail');
    detailCard?.classList.toggle('active', normalized === 'detail');
    editCard?.classList.toggle('app-hidden', normalized !== 'edit');
    editCard?.classList.toggle('active', normalized === 'edit');
}

function setAdminSubtab(target) {
    const normalized = target === 'users' ? 'users' : 'pantries';
    activeAdminSubtab = normalized;

    document.querySelectorAll('.admin-subtab').forEach((btn) => {
        btn.classList.toggle('active', btn.dataset.adminSubtab === normalized);
    });

    document.querySelectorAll('.admin-subcontent').forEach((section) => {
        section.classList.toggle('active', section.id === `admin-subcontent-${normalized}`);
    });
}

function formatAuthProviderLabel(value) {
    const normalized = String(value || '').trim();
    if (!normalized) {
        return 'Not linked';
    }
    return normalized.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

async function ensureAdminRolesLoaded() {
    if (adminRoles.length > 0) {
        return adminRoles;
    }
    adminRoles = await getRoles();
    return adminRoles;
}

async function loadAdminTab() {
    if (activeAdminSubtab === 'users') {
        await loadAdminUsers();
        return;
    }
    await loadPantries();
}

function isPhoneViewport() {
    return window.matchMedia('(max-width: 767px)').matches;
}

function renderAdminUserRoleChips(roles) {
    if (!Array.isArray(roles) || !roles.length) {
        return '<div class="table-user-secondary compact">No roles</div>';
    }

    return `
        <div class="admin-user-chip-list">
            ${roles.map((role) => `<span class="admin-user-chip">${escapeHtml(role)}</span>`).join('')}
        </div>
    `;
}

function renderAdminInlineProfile(userId) {
    if (selectedAdminUserProfileError) {
        return `
            <tr class="admin-user-inline-row">
                <td colspan="5" class="admin-user-inline-cell">
                    <p class="my-shift-load-error">Failed to load user profile: ${escapeHtml(selectedAdminUserProfileError)}</p>
                </td>
            </tr>
        `;
    }

    if (!selectedAdminUserProfile || selectedAdminUserProfile.user_id !== userId) {
        return `
            <tr class="admin-user-inline-row">
                <td colspan="5" class="admin-user-inline-cell">
                    <div class="loading">
                        <div class="spinner"></div>
                        <p>Loading user profile...</p>
                    </div>
                </td>
            </tr>
        `;
    }

    return `
        <tr class="admin-user-inline-row">
            <td colspan="5" class="admin-user-inline-cell">
                <div data-admin-inline-profile="${userId}">
                    ${buildAdminUserProfileMarkup(selectedAdminUserProfile, { inline: true })}
                </div>
            </td>
        </tr>
    `;
}

function renderAdminUserTable() {
    const tbody = document.getElementById('admin-users-table-body');
    if (!tbody) {
        return;
    }

    if (!adminUsers.length) {
        tbody.innerHTML = '<tr><td colspan="5" class="table-empty-cell">No users found.</td></tr>';
        return;
    }

    const phoneView = isPhoneViewport();
    tbody.innerHTML = adminUsers.map((user) => {
        const isSelected = selectedAdminUserId === user.user_id;
        const phoneText = formatAccountValue(user.phone_number, 'No phone');
        const authText = formatAuthProviderLabel(user.auth_provider);
        const viewLabel = phoneView && isSelected ? 'Hide' : 'View';
        return `
            <tr class="admin-user-row ${isSelected ? 'selected' : ''}" data-admin-user-row="${user.user_id}">
                <td data-label="User">
                    <div class="table-user-primary">${escapeHtml(formatAccountValue(user.full_name))}</div>
                    <div class="table-user-secondary">Joined ${escapeHtml(formatAccountTimestamp(user.created_at))}</div>
                </td>
                <td data-label="Contact">
                    <div class="table-user-primary">${escapeHtml(formatAccountValue(user.email))}</div>
                    <div class="table-user-secondary">${escapeHtml(phoneText)}</div>
                </td>
                <td data-label="Access">
                    ${renderAdminUserRoleChips(user.roles)}
                    <div class="table-user-secondary">${escapeHtml(authText)}</div>
                </td>
                <td data-label="Score">${escapeHtml(String(Number(user.attendance_score || 0)))}%</td>
                <td data-label="Open"><button type="button" class="btn btn-secondary btn-sm" data-open-admin-user="${user.user_id}">${viewLabel}</button></td>
            </tr>
            ${phoneView && isSelected ? renderAdminInlineProfile(user.user_id) : ''}
        `;
    }).join('');

    if (!phoneView) {
        tbody.querySelectorAll('[data-admin-user-row]').forEach((row) => {
            row.addEventListener('click', async (event) => {
                if (event.target.closest('[data-open-admin-user]')) {
                    return;
                }
                await openAdminUserProfile(Number(row.dataset.adminUserRow));
            });
        });
    }

    tbody.querySelectorAll('[data-open-admin-user]').forEach((button) => {
        button.addEventListener('click', async () => {
            await withButtonLock(button, () => openAdminUserProfile(Number(button.dataset.openAdminUser)));
        });
    });

    if (phoneView && selectedAdminUserProfile && selectedAdminUserProfile.user_id === selectedAdminUserId) {
        const inlineContainer = tbody.querySelector(`[data-admin-inline-profile="${selectedAdminUserProfile.user_id}"]`);
        if (inlineContainer) {
            bindAdminUserProfileInteractions(inlineContainer, selectedAdminUserProfile);
        }
    }
}

function renderAdminRoleOptions(userProfile, inputName = 'admin-user-role') {
    const editableRoles = adminRoles.filter((role) => role.role_name !== 'SUPER_ADMIN');
    const selectedRole = Array.isArray(userProfile.roles) && userProfile.roles.length ? userProfile.roles[0] : '';
    return editableRoles.map((role) => `
        <label class="admin-role-option ${selectedRole === role.role_name ? 'selected' : ''}">
            <input
                type="radio"
                name="${inputName}"
                value="${role.role_id}"
                ${selectedRole === role.role_name ? 'checked' : ''}
            >
            <span>${escapeHtml(role.role_name)}</span>
        </label>
    `).join('');
}

function buildAdminUserProfileMarkup(userProfile, options = {}) {
    const inline = Boolean(options.inline);
    const rolesText = Array.isArray(userProfile.roles) && userProfile.roles.length ? userProfile.roles.join(', ') : 'No roles';
    const isProtectedSuperAdmin = userProfile.user_id === 1 || (Array.isArray(userProfile.roles) && userProfile.roles.includes('SUPER_ADMIN'));
    const canEditRoles = !isProtectedSuperAdmin;
    const inputName = `admin-user-role-${userProfile.user_id}`;
    const roleNote = isProtectedSuperAdmin
        ? '<div class="account-note memory-note">This protected super admin account is read-only. Its roles cannot be changed or removed.</div>'
        : '<div class="account-note">Update the selected user roles below. SUPER_ADMIN is intentionally excluded from editable controls.</div>';

    return `
        <div class="admin-user-profile ${inline ? 'admin-user-profile-inline' : ''}">
            <div class="account-summary-grid admin-user-summary-grid">
                ${renderAccountSummaryItem('Full Name', formatAccountValue(userProfile.full_name))}
                ${renderAccountSummaryItem('Email', formatAccountValue(userProfile.email))}
                ${renderAccountSummaryItem('Phone Number', formatAccountValue(userProfile.phone_number))}
                ${renderAccountSummaryItem('Roles', rolesText)}
                ${renderAccountSummaryItem('Attendance Score', `${Number(userProfile.attendance_score || 0)}%`)}
                ${renderAccountSummaryItem('Auth Provider', formatAuthProviderLabel(userProfile.auth_provider))}
                ${renderAccountSummaryItem('Auth UID', formatAccountValue(userProfile.auth_uid))}
                ${renderAccountSummaryItem('Created At', formatAccountTimestamp(userProfile.created_at))}
                ${renderAccountSummaryItem('Updated At', formatAccountTimestamp(userProfile.updated_at))}
            </div>
            <div class="admin-user-role-editor">
                <h3 class="admin-user-role-title">Roles</h3>
                ${roleNote}
                <form data-admin-user-role-form="${userProfile.user_id}">
                    <div class="admin-role-options">
                        ${renderAdminRoleOptions(userProfile, inputName)}
                    </div>
                    <div class="admin-user-role-actions">
                        <button type="submit" class="btn btn-primary" ${canEditRoles ? '' : 'disabled'}>Save Roles</button>
                    </div>
                </form>
            </div>
        </div>
    `;
}

function bindAdminUserProfileInteractions(container, userProfile) {
    const isProtectedSuperAdmin = userProfile.user_id === 1 || (Array.isArray(userProfile.roles) && userProfile.roles.includes('SUPER_ADMIN'));
    const canEditRoles = !isProtectedSuperAdmin;
    const inputName = `admin-user-role-${userProfile.user_id}`;
    const roleForm = container.querySelector(`[data-admin-user-role-form="${userProfile.user_id}"]`);

    roleForm?.querySelectorAll(`input[name="${inputName}"]`).forEach((input) => {
        input.addEventListener('change', () => {
            roleForm.querySelectorAll('.admin-role-option').forEach((option) => {
                option.classList.toggle('selected', option.contains(input) && input.checked);
            });
        });
    });
    roleForm?.addEventListener('submit', async (event) => {
        event.preventDefault();

        if (!canEditRoles) {
            showMessage('admin-users', 'The protected super admin account cannot be edited.', 'error');
            return;
        }

        const selectedRoleInput = roleForm.querySelector(`input[name="${inputName}"]:checked`);
        if (!selectedRoleInput) {
            showMessage('admin-users', 'Select one role before saving.', 'error');
            return;
        }

        const selectedRoleIds = [Number(selectedRoleInput.value)];
        const editingSelf = currentUser && currentUser.user_id === userProfile.user_id;

        await withButtonLock(getSubmitButtonFromEvent(event), async () => {
            try {
                const updatedProfile = await updateUserRoles(userProfile.user_id, selectedRoleIds);
                showMessage('admin-users', 'User roles updated successfully.', 'success');
                await refreshCurrentUserState();
                if (editingSelf) {
                    await loadPantries();
                    if (!currentUserIsAdminCapable()) {
                        await activateTab(setupRoleBasedUI());
                        return;
                    }
                }
                await loadAdminUsers({ preserveSelection: true, preferredUserId: updatedProfile.user_id });
            } catch (error) {
                showMessage('admin-users', `Failed to update roles: ${error.message}`, 'error');
            }
        });
    });
}

function renderAdminUserProfile(userProfile) {
    const panel = document.getElementById('admin-user-profile-panel');
    if (!panel) {
        return;
    }

    panel.innerHTML = buildAdminUserProfileMarkup(userProfile);
    bindAdminUserProfileInteractions(panel, userProfile);
}

async function openAdminUserProfile(userId, options = {}) {
    const force = Boolean(options.force);
    if (isPhoneViewport() && !force && selectedAdminUserId === userId) {
        selectedAdminUserId = null;
        selectedAdminUserProfile = null;
        selectedAdminUserProfileError = '';
        renderAdminUserTable();
        return;
    }

    selectedAdminUserId = userId;
    selectedAdminUserProfile = null;
    selectedAdminUserProfileError = '';
    renderAdminUserTable();

    const panel = document.getElementById('admin-user-profile-panel');
    if (!isPhoneViewport() && panel) {
        panel.innerHTML = '<div class="loading"><div class="spinner"></div><p>Loading user profile...</p></div>';
    }

    try {
        const profile = await getUserProfile(userId);
        if (selectedAdminUserId !== userId) {
            return;
        }
        selectedAdminUserProfile = profile;
        if (isPhoneViewport()) {
            renderAdminUserTable();
            return;
        }
        renderAdminUserProfile(profile);
    } catch (error) {
        if (selectedAdminUserId !== userId) {
            return;
        }
        selectedAdminUserProfileError = error.message;
        if (isPhoneViewport()) {
            renderAdminUserTable();
        } else if (panel) {
            panel.innerHTML = `<p class="my-shift-load-error">Failed to load user profile: ${escapeHtml(error.message)}</p>`;
        }
        showMessage('admin-users', `Failed to load user profile: ${error.message}`, 'error');
    }
}

async function loadAdminUsers(options = {}) {
    const preserveSelection = Boolean(options.preserveSelection);
    const preferredUserId = options.preferredUserId || null;
    const searchInput = document.getElementById('admin-user-search');
    const roleFilterSelect = document.getElementById('admin-user-role-filter');
    const panel = document.getElementById('admin-user-profile-panel');

    try {
        await ensureAdminRolesLoaded();

        if (roleFilterSelect && !roleFilterSelect.dataset.initialized) {
            roleFilterSelect.innerHTML = '<option value="">All roles</option>';
            adminRoles.forEach((role) => {
                const option = document.createElement('option');
                option.value = role.role_name;
                option.textContent = role.role_name;
                roleFilterSelect.appendChild(option);
            });
            roleFilterSelect.dataset.initialized = 'true';
        }

        const roleFilter = roleFilterSelect ? roleFilterSelect.value : '';
        const searchQuery = searchInput ? searchInput.value.trim() : '';
        adminUsers = await getAllUsers(roleFilter || null, searchQuery);

        if (!preserveSelection) {
            selectedAdminUserId = null;
            selectedAdminUserProfile = null;
            selectedAdminUserProfileError = '';
        }

        if (preferredUserId) {
            selectedAdminUserId = preferredUserId;
        } else if (selectedAdminUserId && !adminUsers.some((user) => user.user_id === selectedAdminUserId)) {
            selectedAdminUserId = null;
            selectedAdminUserProfile = null;
            selectedAdminUserProfileError = '';
        }

        renderAdminUserTable();

        if (selectedAdminUserId) {
            await openAdminUserProfile(selectedAdminUserId, { force: true });
        } else if (panel) {
            panel.innerHTML = '<p class="auth-empty">Select a user to view the full profile and manage roles.</p>';
        }
    } catch (error) {
        if (panel) {
            panel.innerHTML = `<p class="my-shift-load-error">Failed to load users: ${escapeHtml(error.message)}</p>`;
        }
        showMessage('admin-users', `Failed to load users: ${error.message}`, 'error');
    }
}

function handleAdminUsersViewportChange() {
    const phoneView = isPhoneViewport();
    if (lastAdminUsersPhoneViewport === phoneView) {
        return;
    }

    lastAdminUsersPhoneViewport = phoneView;
    renderAdminUserTable();

    if (!selectedAdminUserId) {
        return;
    }

    if (phoneView) {
        return;
    }

    if (selectedAdminUserProfile) {
        renderAdminUserProfile(selectedAdminUserProfile);
        return;
    }

    openAdminUserProfile(selectedAdminUserId, { force: true });
}

function formatShiftRange(startTime, endTime) {
    return formatLocalTimeRange(startTime, endTime);
}

function formatShiftDuration(startTime, endTime) {
    const start = safeDateValue(startTime);
    const end = safeDateValue(endTime);
    if (!start || !end) return null;
    const mins = Math.round((end - start) / 60000);
    if (mins <= 0) return null;
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    if (h === 0) return `${m}m`;
    if (m === 0) return `${h}h`;
    return `${h}h ${m}m`;
}

function getAttendanceInfo(signupStatus) {
    const normalized = String(signupStatus || '').toUpperCase();
    if (normalized === 'SHOW_UP') {
        return { label: 'Attended', className: 'attendance-badge-attended', isMarked: true };
    }
    if (normalized === 'NO_SHOW') {
        return { label: 'Missed', className: 'attendance-badge-missed', isMarked: true };
    }
    return { label: 'Pending Attendance', className: 'attendance-badge-pending', isMarked: false };
}

function getAttendanceWindowInfo(startTime, endTime, now = new Date()) {
    // TODO(dev): Re-enable client-side attendance window UX before production.
    // Server-side checks are currently disabled for dev, so keep UI unrestricted too.
    return { canMark: true, message: 'Attendance window is open (dev mode).' };

    /*
    const start = safeDateValue(startTime);
    const end = safeDateValue(endTime);
    if (!start || !end) {
        return { canMark: false, message: 'Attendance window unavailable for this shift.' };
    }

    const openAt = new Date(start.getTime() - 15 * 60 * 1000);
    const closeAt = new Date(end.getTime() + 6 * 60 * 60 * 1000);
    if (now < openAt) {
        return { canMark: false, message: 'Attendance opens 15 minutes before shift start.' };
    }
    if (now > closeAt) {
        return { canMark: false, message: 'Attendance window is closed (6 hours after shift end).' };
    }
    return { canMark: true, message: 'Attendance window is open.' };
    */
}

function renderCredibilitySummary(attendanceScore) {
    const normalizedScore = Number.isFinite(Number(attendanceScore))
        ? Math.max(0, Math.min(100, Math.round(Number(attendanceScore))))
        : null;

    if (normalizedScore === null) {
        return `
            <section class="credibility-summary">
                <h3 class="credibility-title">Credibility</h3>
                <p class="credibility-value">N/A</p>
                <p class="credibility-detail">Attendance score unavailable.</p>
            </section>
        `;
    }

    return `
        <section class="credibility-summary">
            <h3 class="credibility-title">Credibility</h3>
            <p class="credibility-value">${normalizedScore}%</p>
            <p class="credibility-detail">Based on marked attendance records.</p>
        </section>
    `;
}

function renderMyShiftsSummary() {
    const container = document.getElementById('my-shifts-summary');
    if (!container || !currentUser) {
        return;
    }

    const now = new Date();
    const upcoming = myRegisteredSignups.filter((s) => {
        const start = safeDateValue(s.start_time);
        return start && start > now && s.signup_status !== 'CANCELLED';
    }).length;

    const upcomingHtml = `<p class="my-shifts-upcoming-count">${upcoming === 0 ? 'No upcoming shifts.' : `You have <strong>${upcoming}</strong> upcoming shift${upcoming === 1 ? '' : 's'}.`}</p>`;

    container.innerHTML = upcomingHtml + renderCredibilitySummary(currentUser.attendance_score);
}

function setMyShiftsViewMode(mode = 'calendar') {
    myShiftsViewMode = mode === 'list' ? 'list' : 'calendar';

    const toggle = document.querySelector('.my-shifts-view-toggle');
    if (toggle) {
        toggle.dataset.activeView = myShiftsViewMode;
    }

    document.querySelectorAll('[data-my-shifts-view]').forEach((button) => {
        button.classList.toggle('active', button.dataset.myShiftsView === myShiftsViewMode);
    });

    document.getElementById('my-shifts-calendar-panel')?.classList.toggle('app-hidden', myShiftsViewMode !== 'calendar');
    document.getElementById('my-shifts-list-panel')?.classList.toggle('app-hidden', myShiftsViewMode !== 'list');
}

function getMyShiftsListPantries(signups = myRegisteredSignups) {
    const pantryMap = new Map();

    (Array.isArray(signups) ? signups : []).forEach((signup) => {
        const pantryId = String(signup.pantry_id || '');
        if (!pantryId || pantryMap.has(pantryId)) {
            return;
        }
        pantryMap.set(pantryId, {
            pantry_id: pantryId,
            name: signup.pantry_name || `Pantry ${pantryId}`
        });
    });

    return [...pantryMap.values()].sort((left, right) => String(left.name || '').localeCompare(String(right.name || '')));
}

function syncMyShiftsListFilters() {
    const searchInput = document.getElementById('my-shifts-list-search');
    const pantrySelect = document.getElementById('my-shifts-list-pantry-filter');
    const timeSelect = document.getElementById('my-shifts-list-time-filter');

    if (searchInput) {
        searchInput.value = myShiftsListFilters.search;
    }
    if (timeSelect) {
        timeSelect.value = myShiftsListFilters.timeBucket;
    }
    if (!pantrySelect) {
        return;
    }

    const pantryOptions = [
        '<option value="all">All pantries</option>',
        ...getMyShiftsListPantries().map((pantry) => `<option value="${escapeHtml(pantry.pantry_id)}">${escapeHtml(pantry.name)}</option>`)
    ];
    pantrySelect.innerHTML = pantryOptions.join('');

    const hasPantry = myShiftsListFilters.pantryId === 'all'
        || getMyShiftsListPantries().some((pantry) => String(pantry.pantry_id) === String(myShiftsListFilters.pantryId));
    myShiftsListFilters.pantryId = hasPantry ? myShiftsListFilters.pantryId : 'all';
    pantrySelect.value = myShiftsListFilters.pantryId;

    const sortSelect = document.getElementById('my-shifts-list-sort');
    if (sortSelect) {
        sortSelect.value = myShiftsListFilters.sort;
    }
}

function filterMyShiftList(signups) {
    return (Array.isArray(signups) ? signups : []).filter((signup) => {
        const searchBlob = [
            signup.shift_name,
            signup.pantry_name,
            signup.pantry_location,
            signup.role_title
        ].filter(Boolean).join(' ').toLowerCase();

        if (myShiftsListFilters.search && !searchBlob.includes(myShiftsListFilters.search.toLowerCase())) {
            return false;
        }

        if (myShiftsListFilters.pantryId !== 'all' && String(signup.pantry_id) !== String(myShiftsListFilters.pantryId)) {
            return false;
        }

        const startDate = safeDateValue(signup.start_time);
        if (myShiftsListFilters.timeBucket !== 'all' && startDate && resolveCalendarTimeBucket(startDate) !== myShiftsListFilters.timeBucket) {
            return false;
        }

        if (myShiftsListFilters.status !== 'all' && signup.signup_status !== myShiftsListFilters.status) {
            return false;
        }

        return true;
    });
}

function getMyRegisteredShiftBuckets(signups, now = new Date()) {
    const buckets = {
        incoming: [],
        ongoing: [],
        past: [],
    };

    (Array.isArray(signups) ? signups : []).forEach((signup) => {
        const bucket = classifyShiftBucket(signup, now);
        buckets[bucket].push(signup);
    });

    const dir = myShiftsListFilters.sort === 'date-desc' ? 'desc' : 'asc';
    buckets.incoming.sort((a, b) => sortByDate(a, b, 'start_time', dir));
    buckets.ongoing.sort((a, b) => sortByDate(a, b, 'end_time', dir));
    buckets.past.sort((a, b) => sortByDate(a, b, 'end_time', dir));
    return buckets;
}

function renderMyShiftList(signups) {
    const container = document.getElementById('my-shifts-list-container');
    if (!container) {
        return;
    }

    syncMyShiftsListFilters();
    const now = new Date();
    container.classList.remove('loading');
    const filteredSignups = filterMyShiftList(signups);

    if (!Array.isArray(signups) || signups.length === 0) {
        container.innerHTML = '<p class="my-shift-empty-all">You have no registered shifts yet.</p>';
        return;
    }

    if (filteredSignups.length === 0) {
        container.innerHTML = '<p class="my-shift-empty-all">No registered shifts match your list filters.</p>';
        return;
    }

    const buckets = getMyRegisteredShiftBuckets(filteredSignups, now);
    container.innerHTML = `
        <div class="my-shifts-sections">
            ${renderMyShiftSection('incoming', 'Incoming Shifts', buckets.incoming, now)}
            ${renderMyShiftSection('ongoing', 'Ongoing Shifts', buckets.ongoing, now)}
            ${renderMyShiftSection('past', 'Past Shifts', buckets.past, now)}
        </div>
    `;
}

function formatAccountValue(value, fallback = '—') {
    if (value === null || value === undefined || value === '') {
        return fallback;
    }
    return String(value);
}

function formatAccountTimestamp(value) {
    return formatLocalDateTime(value) || '—';
}

function renderAccountSummaryItem(label, value) {
    return `
        <div class="account-summary-item">
            <span class="account-summary-label">${escapeHtml(label)}</span>
            <div class="account-summary-value">${escapeHtml(value)}</div>
        </div>
    `;
}

function updateAccountEmailUi() {
    const note = document.getElementById('my-account-email-note');
    const submitButton = document.getElementById('account-email-submit-btn');
    const newEmailInput = document.getElementById('account-new-email');
    const currentEmailInput = document.getElementById('account-current-email');

    if (!note || !submitButton || !newEmailInput || !currentEmailInput || !currentUser) {
        return;
    }

    currentEmailInput.value = currentUser.email || '';

    if (currentUser.email_change_supported) {
        note.className = 'account-note firebase-note';
        note.innerHTML = 'We will ask you to confirm with Google of <b>the current email</b>, send a verification link to the new email, then update the app after your next sign-in.';
        submitButton.disabled = false;
        newEmailInput.disabled = false;
    } else {
        note.className = 'account-note memory-note';
        note.textContent = currentUser.auth_mode === 'firebase'
            ? 'This account is not linked to Firebase yet. Sign out and sign in again with Google before changing email.'
            : 'Demo auth allows editing name and phone number only. Email changes are not available in memory mode.';
        submitButton.disabled = true;
        newEmailInput.disabled = true;
    }
}

function updateDeleteAccountUi() {
    const deleteButton = document.getElementById('delete-account-btn');
    const deleteNote = document.querySelector('.delete-account-note');
    if (!deleteButton || !deleteNote || !currentUser) {
        return;
    }

    const isProtectedSuperAdmin = currentUser.user_id === 1 || currentUserHasRole('SUPER_ADMIN');
    if (isProtectedSuperAdmin) {
        deleteButton.disabled = true;
        deleteNote.textContent = 'The protected super admin account cannot delete itself.';
        return;
    }

    deleteButton.disabled = false;
    deleteNote.textContent = 'Deleting your account removes your local app user, signs you out, and in Firebase mode also deletes the linked Firebase account after a fresh Google reauthentication.';
}

function calcShiftsThisWeek(signups) {
    const now = new Date();
    const weekEnd = new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000);
    const count = (Array.isArray(signups) ? signups : []).filter((s) => {
        const start = safeDateValue(s.start_time);
        return start && start >= now && start <= weekEnd && s.signup_status !== 'CANCELLED';
    }).length;
    return count === 0 ? 'None this week' : `${count} shift${count === 1 ? '' : 's'}`;
}

function calcTotalVolunteerHours(signups) {
    const attended = (Array.isArray(signups) ? signups : []).filter(
        (s) => s.signup_status === 'SHOW_UP'
    );
    const totalMins = attended.reduce((sum, s) => {
        const start = safeDateValue(s.start_time);
        const end = safeDateValue(s.end_time);
        if (!start || !end) return sum;
        return sum + Math.max(0, Math.round((end - start) / 60000));
    }, 0);
    if (totalMins === 0) return '0h';
    const h = Math.floor(totalMins / 60);
    const m = totalMins % 60;
    return m === 0 ? `${h}h` : `${h}h ${m}m`;
}

function renderMyAccountSummary() {
    const container = document.getElementById('my-account-summary');
    if (!container || !currentUser) {
        return;
    }

    const rolesText = Array.isArray(currentUser.roles) && currentUser.roles.length > 0
        ? currentUser.roles.join(', ')
        : 'No roles';

    container.innerHTML = `
        ${renderAccountSummaryItem('Full Name', formatAccountValue(currentUser.full_name))}
        ${renderAccountSummaryItem('Email', formatAccountValue(currentUser.email))}
        ${renderAccountSummaryItem('Phone Number', formatAccountValue(currentUser.phone_number))}
        ${renderAccountSummaryItem('Saved Timezone', formatTimeZoneDisplay(currentUser.timezone || DEFAULT_APP_TIMEZONE))}
        ${renderAccountSummaryItem('Roles', rolesText)}
        ${renderAccountSummaryItem('Attendance Score', `${Number(currentUser.attendance_score || 0)}%`)}
        ${renderAccountSummaryItem('Total Volunteer Hours', calcTotalVolunteerHours(myRegisteredSignups))}
        ${renderAccountSummaryItem('Shifts This Week', calcShiftsThisWeek(myRegisteredSignups))}
        ${renderAccountSummaryItem('Created At', formatAccountTimestamp(currentUser.created_at))}
        ${renderAccountSummaryItem('Updated At', formatAccountTimestamp(currentUser.updated_at))}
    `;

    const timezoneNote = document.getElementById('my-account-timezone-note');
    if (timezoneNote) {
        timezoneNote.textContent = `Times on the web are shown in your browser timezone: ${formatTimeZoneDisplay()}.`;
    }
}

function renderCalendarSyncUi() {
    const note = document.getElementById('my-account-calendar-note');
    const status = document.getElementById('my-account-calendar-status');
    const connectButton = document.getElementById('connect-google-calendar-btn');
    const disconnectButton = document.getElementById('disconnect-google-calendar-btn');

    if (!note || !status || !connectButton || !disconnectButton) {
        return;
    }

    const configured = Boolean(currentGoogleCalendarStatus?.configured);
    const connected = Boolean(currentGoogleCalendarStatus?.connected);
    const connectedEmail = currentGoogleCalendarStatus?.google_email || '';
    const statusError = currentGoogleCalendarStatus?.error || '';

    if (statusError) {
        note.className = 'account-note memory-note';
        note.textContent = 'Google Calendar sync status could not be loaded.';
        status.className = 'account-note';
        status.textContent = statusError;
        connectButton.disabled = true;
        connectButton.hidden = false;
        connectButton.textContent = 'Google Calendar Unavailable';
        disconnectButton.hidden = true;
        disconnectButton.disabled = true;
    } else if (!configured) {
        note.className = 'account-note memory-note';
        note.textContent = 'Server setup for Google Calendar OAuth is incomplete. Add Google OAuth client settings before volunteers can enable full sync.';
        status.className = 'account-note';
        status.textContent = 'Automatic Google Calendar sync is unavailable until the server is configured.';
        connectButton.disabled = true;
        connectButton.hidden = false;
        connectButton.textContent = 'Google Calendar Unavailable';
        disconnectButton.hidden = true;
        disconnectButton.disabled = true;
    } else if (connected) {
        note.className = 'account-note account-note-success';
        note.textContent = 'Automatic sync is active. New signups and later shift changes will be pushed from the app to Google Calendar.';
        status.className = 'account-note';
        status.textContent = connectedEmail
            ? `Connected Google account: ${connectedEmail}`
            : 'Google Calendar is connected.';
        connectButton.disabled = true;
        connectButton.hidden = false;
        connectButton.textContent = 'Auto Sync Enabled';
        disconnectButton.hidden = false;
        disconnectButton.disabled = false;
    } else {
        note.className = 'account-note';
        note.textContent = 'Connect Google Calendar once to let the app create, update, and remove volunteer events automatically.';
        status.className = 'account-note';
        status.textContent = 'Automatic sync is not connected yet.';
        connectButton.disabled = false;
        connectButton.hidden = false;
        connectButton.textContent = 'Connect Google Calendar';
        disconnectButton.hidden = true;
        disconnectButton.disabled = true;
    }
}

async function loadGoogleCalendarStatus() {
    if (!currentUser || typeof getGoogleCalendarStatus !== 'function') {
        return;
    }

    try {
        currentGoogleCalendarStatus = await getGoogleCalendarStatus();
    } catch (error) {
        currentGoogleCalendarStatus = {
            configured: false,
            connected: false,
            error: error.message
        };
    }

    renderCalendarSyncUi();
}

function syncMyAccountForms() {
    if (!currentUser) {
        return;
    }

    const fullNameInput = document.getElementById('account-full-name');
    const phoneInput = document.getElementById('account-phone-number');
    const newEmailInput = document.getElementById('account-new-email');

    if (fullNameInput) {
        fullNameInput.value = currentUser.full_name || '';
    }
    if (phoneInput) {
        phoneInput.value = currentUser.phone_number || '';
    }
    if (newEmailInput) {
        newEmailInput.value = '';
    }

    updateAccountEmailUi();
    updateDeleteAccountUi();
    renderCalendarSyncUi();
}

async function refreshCurrentUserState() {
    currentUser = await getCurrentUser();
    document.getElementById('user-email').textContent = currentUser.email;
    document.getElementById('user-role').textContent = currentUser.roles.join(', ');
    setupRoleBasedUI();
    renderMyAccountSummary();
    syncMyAccountForms();
    await loadGoogleCalendarStatus();
}

async function loadMyAccount() {
    if (!currentUser) {
        return;
    }
    if (myRegisteredSignups.length === 0) {
        try {
            const signups = await getUserSignups(currentUser.user_id);
            myRegisteredSignups = Array.isArray(signups) ? signups : [];
        } catch (_) {}
    }
    renderMyAccountSummary();
    syncMyAccountForms();
    await loadGoogleCalendarStatus();
}

async function connectGoogleCalendarFromAccount() {
    if (typeof startGoogleCalendarConnect !== 'function') {
        throw new Error('Google Calendar sync is unavailable right now.');
    }

    const response = await startGoogleCalendarConnect();
    if (!response?.auth_url) {
        throw new Error('Google Calendar authorization URL was not returned by the server.');
    }

    const popup = window.open(response.auth_url, 'google-calendar-connect', 'width=620,height=760');
    if (!popup) {
        throw new Error('Popup blocked. Allow popups for this site and try again.');
    }

    return await new Promise((resolve, reject) => {
        let settled = false;

        const finish = async (message, isError = false) => {
            if (settled) {
                return;
            }
            settled = true;
            window.removeEventListener('message', handleMessage);
            try {
                await loadGoogleCalendarStatus();
            } catch (error) {
                console.error('Failed to refresh Google Calendar status:', error);
            }
            if (isError) {
                reject(new Error(message || 'Google Calendar authorization failed.'));
            } else {
                resolve(message || 'Google Calendar sync connected.');
            }
        };

        const popupPoll = window.setInterval(() => {
            if (popup.closed) {
                window.clearInterval(popupPoll);
                finish('Google Calendar authorization window was closed before finishing.', true);
            }
        }, 500);

        const handleMessage = (event) => {
            if (event.origin !== window.location.origin) {
                return;
            }
            if (event.data?.type !== 'google-calendar-oauth-complete') {
                return;
            }
            window.clearInterval(popupPoll);
            finish(event.data.message, event.data.ok !== true);
        };

        window.addEventListener('message', handleMessage);
    });
}

function renderMyShiftCard(signup, now) {
    const signupStatus = String(signup.signup_status || 'UNKNOWN').toUpperCase();
    const shiftStatus = String(signup.shift_status || 'OPEN').toUpperCase();
    const attendanceInfo = getAttendanceInfo(signupStatus);
    const showCancelByTime = canCancelSignup(signup, now);
    const nonActionableStatuses = new Set(['CANCELLED', 'WAITLISTED']);
    const showCancel = showCancelByTime
        && !nonActionableStatuses.has(signupStatus)
        && shiftStatus !== 'CANCELLED';
    const showSignupStatusBadge = !attendanceInfo.isMarked;
    const isPendingReconfirm = signupStatus === 'PENDING_CONFIRMATION';
    const reconfirmAvailable = Boolean(signup.reconfirm_available);

    let actionsHtml = '';
    if (isPendingReconfirm) {
        actionsHtml = `
            <div class="my-shift-actions">
                ${reconfirmAvailable
                ? `<button class="btn btn-success btn-compact" onclick="reconfirmMySignup(${signup.signup_id}, 'CONFIRM', this)">Confirm</button>`
                : `<span class="reconfirm-note">Role is full or unavailable for reconfirmation.</span>`
            }
                <button class="btn btn-danger btn-compact" onclick="reconfirmMySignup(${signup.signup_id}, 'CANCEL', this)">Cancel</button>
            </div>
        `;
    } else if (showCancel) {
        actionsHtml = `
            <div class="my-shift-actions">
                <button class="btn btn-danger btn-compact" onclick="cancelMySignup(${signup.signup_id}, this)">Cancel Signup</button>
            </div>
        `;
    }

    return `
        <article class="my-shift-card">
            <div class="my-shift-card-header">
                <div>
                    <h4 class="my-shift-title">${escapeHtml(signup.shift_name || 'Untitled Shift')}</h4>
                    <p class="my-shift-role">Role: ${escapeHtml(signup.role_title || 'Unassigned')}${signup.filled_count != null && signup.required_count != null ? ` <span style="color:#718096;font-size:0.82rem;">(${signup.filled_count}/${signup.required_count} filled)</span>` : ''}</p>
                </div>
                <div class="my-shift-badges">
                    <span class="status-badge attendance-badge ${attendanceInfo.className}">${escapeHtml(attendanceInfo.label)}</span>
                    ${showSignupStatusBadge
            ? `<span class="status-badge ${toStatusClass('signup-status', signupStatus)}">${escapeHtml(signupStatus)}</span>`
            : ''
        }
                    <span class="status-badge ${toStatusClass('shift-status', shiftStatus)}">${escapeHtml(shiftStatus)}</span>
                </div>
            </div>
            <div class="my-shift-meta">
                <p><strong>When:</strong> ${escapeHtml(formatShiftRange(signup.start_time, signup.end_time))}${formatShiftDuration(signup.start_time, signup.end_time) ? ` <span style="color:#718096;">(${escapeHtml(formatShiftDuration(signup.start_time, signup.end_time))})</span>` : ''}</p>
                <p><strong>Pantry:</strong> ${escapeHtml(signup.pantry_name || 'Unknown Pantry')}</p>
                <p><strong>Location:</strong> ${escapeHtml(signup.pantry_location || 'No location listed')}</p>
            </div>
            ${actionsHtml}
        </article>
    `;
}

function renderMyShiftSection(sectionId, title, signups, now) {
    if (!signups || signups.length === 0) {
        return `
            <section class="my-shift-section" id="my-shift-section-${sectionId}">
                <h3 class="my-shift-section-title">${title}</h3>
                <p class="my-shift-empty">No ${title.toLowerCase()}.</p>
            </section>
        `;
    }

    return `
        <section class="my-shift-section" id="my-shift-section-${sectionId}">
            <h3 class="my-shift-section-title">${title}</h3>
            <div class="my-shifts-grid">
                ${signups.map(signup => renderMyShiftCard(signup, now)).join('')}
            </div>
        </section>
    `;
}

async function loadMyRegisteredShifts() {
    const listContainer = document.getElementById('my-shifts-list-container');
    if (!listContainer || !currentUser) return;

    renderMyShiftsSummary();
    listContainer.innerHTML = '<div class="loading"><div class="spinner"></div><p>Loading your registered shifts...</p></div>';

    const myShiftsCalendarController = typeof getCalendarController === 'function'
        ? getCalendarController('my-shifts')
        : null;
    myShiftsCalendarController?.showLoading('Loading your registered shifts...');

    try {
        const signups = await getUserSignups(currentUser.user_id);
        myRegisteredSignups = Array.isArray(signups) ? signups : [];
        renderMyShiftList(myRegisteredSignups);
        if (typeof setMyShiftsCalendarItems === 'function') {
            await setMyShiftsCalendarItems(myRegisteredSignups, true);
        }
    } catch (error) {
        console.error('Failed to load my shifts:', error);
        myRegisteredSignups = [];
        listContainer.classList.remove('loading');
        listContainer.innerHTML = `<p class="my-shift-load-error">Failed to load your registered shifts: ${escapeHtml(error.message)}</p>`;
        myShiftsCalendarController?.showError('Failed to load registered shifts', error.message);
        showMessage('my-shifts', `Failed to load shifts: ${error.message}`, 'error');
    }
}

async function cancelMySignup(signupId, buttonEl = null) {
    if (!confirm('Cancel this signup?')) return false;

    return withButtonLock(buttonEl, async () => {
        try {
            await cancelSignup(signupId);
            showMessage('my-shifts', 'Signup cancelled successfully!', 'success');
            await Promise.all([loadMyRegisteredShifts(), loadCalendarShifts()]);
            return true;
        } catch (error) {
            showMessage('my-shifts', `Cancel failed: ${error.message}`, 'error');
            return false;
        }
    });
}

async function reconfirmMySignup(signupId, action, buttonEl = null) {
    const normalizedAction = String(action || '').toUpperCase();
    const actionLabel = normalizedAction === 'CONFIRM' ? 'confirm this updated shift' : 'cancel this updated shift signup';
    if (!confirm(`Do you want to ${actionLabel}?`)) return false;

    return withButtonLock(buttonEl, async () => {
        try {
            await reconfirmSignup(signupId, normalizedAction);
            showMessage('my-shifts', normalizedAction === 'CONFIRM' ? 'Shift reconfirmed successfully!' : 'Signup cancelled successfully!', 'success');
            await Promise.all([loadMyRegisteredShifts(), loadCalendarShifts()]);
            return true;
        } catch (error) {
            const details = parseApiErrorDetails(error);
            if (details && details.code === 'ROLE_FULL_OR_UNAVAILABLE') {
                showMessage('my-shifts', 'This role is full or unavailable. Please cancel or pick another shift.', 'error');
            } else if (details && details.code === 'RESERVATION_EXPIRED') {
                showMessage('my-shifts', 'Your reservation expired. Please sign up again if slots are available.', 'error');
            } else {
                showMessage('my-shifts', `Action failed: ${error.message}`, 'error');
            }
            await loadMyRegisteredShifts();
            return false;
        }
    });
}

async function markSignupAttendance(signupId, attendanceStatus, shiftId, buttonEl = null) {
    await withButtonLock(buttonEl, async () => {
        try {
            await markAttendance(signupId, attendanceStatus);
            showMessage('shifts', 'Attendance updated successfully!', 'success');

            if (typeof shiftId === 'number') {
                delete registrationsCache[shiftId];
            }
            if (Number(attendanceModalShiftId) === Number(shiftId)) {
                attendanceModalRegistrations = await getShiftRegistrations(shiftId);
                registrationsCache[shiftId] = attendanceModalRegistrations;
                renderTakeAttendanceModalList();
            }

            if (managedShiftPanelMode === 'detail' && Number(selectedManagedShiftId) === Number(shiftId)) {
                await loadSelectedShiftRegistrations(shiftId);
            }

            if (expandedShiftContext && expandedShiftContext.shiftId === shiftId) {
                const activeTbody = document.getElementById(expandedShiftContext.tbodyId);
                const detailsRow = activeTbody
                    ? activeTbody.querySelector(`.shift-registrations-row[data-shift-id="${shiftId}"]`)
                    : null;
                if (detailsRow) {
                    const refreshedRegistrations = await getShiftRegistrations(shiftId);
                    registrationsCache[shiftId] = refreshedRegistrations;
                    detailsRow.innerHTML = `<td colspan="4">${renderRegistrationsRowContent(refreshedRegistrations)}</td>`;
                }
            }

            const myShiftsTab = document.getElementById('content-my-shifts');
            if (myShiftsTab && myShiftsTab.classList.contains('active')) {
                await loadMyRegisteredShifts();
            }
        } catch (error) {
            showMessage('shifts', `Attendance update failed: ${error.message}`, 'error');
        }
    });
}

function renderRegistrationsRowContent(shiftRegistrations, options = {}) {
    const roles = shiftRegistrations.roles || [];
    const windowInfo = getAttendanceWindowInfo(shiftRegistrations.start_time, shiftRegistrations.end_time);
    const canMarkAttendance = options.showAttendanceActions !== false
        && currentUser
        && (currentUserIsAdminCapable() || currentUserHasRole('PANTRY_LEAD'));

    if (roles.length === 0) {
        return `
            <div class="shift-registrations">
                <h4 class="registrations-title">Registrations by Role</h4>
                <p class="registrations-empty">No roles configured for this shift.</p>
            </div>
        `;
    }

    const roleBlocks = roles.map(role => {
        const required = role.required_count || 0;
        const filled = role.filled_count || 0;
        const signups = role.signups || [];
        const pendingReconfirmCount = Number(role.pending_reconfirm_count || 0);

        const signupsHtml = signups.length > 0
            ? `
                <ul class="registrant-list">
                    ${signups.map(signup => {
                const user = signup.user || {};
                const userName = escapeHtml(user.full_name || 'Unknown volunteer');
                const userEmail = escapeHtml(user.email || 'No email');
                const attendanceInfo = getAttendanceInfo(signup.signup_status);
                const disabledAttr = windowInfo.canMark ? '' : 'disabled';
                const disabledReason = escapeHtml(windowInfo.message);
                const attendanceActions = canMarkAttendance
                    ? `
                        <div class="registrant-actions">
                            <button
                                class="btn btn-secondary btn-compact btn-attendance btn-attendance-showup"
                                onclick="markSignupAttendance(${signup.signup_id}, 'SHOW_UP', ${shiftRegistrations.shift_id}, this)"
                                ${disabledAttr}
                                title="${disabledReason}"
                            >
                                Mark Show Up
                            </button>
                            <button
                                class="btn btn-secondary btn-compact btn-attendance btn-attendance-noshow"
                                onclick="markSignupAttendance(${signup.signup_id}, 'NO_SHOW', ${shiftRegistrations.shift_id}, this)"
                                ${disabledAttr}
                                title="${disabledReason}"
                            >
                                Mark No Show
                            </button>
                        </div>
                    `
                    : '';

                return `
                            <li class="registrant-item">
                                <div class="registrant-main">
                                    <div class="registrant-name">${userName}</div>
                                    <div class="registrant-email">${userEmail}</div>
                                </div>
                                <div class="registrant-right">
                                    <span class="registrant-status ${attendanceInfo.className}">${escapeHtml(attendanceInfo.label)}</span>
                                    ${attendanceActions}
                                </div>
                            </li>
                        `;
            }).join('')}
                </ul>
            `
            : '<p class="registrations-empty">No volunteers registered yet.</p>';

        return `
            <div class="registration-role">
                <div class="registration-role-header">
                    <div class="registration-role-title">${escapeHtml(role.role_title || 'Untitled Role')}</div>
                    <div class="registration-role-capacity">${filled}/${required} reserved</div>
                </div>
                ${pendingReconfirmCount > 0
                    ? `<p class="reconfirm-note">${pendingReconfirmCount} volunteer(s) pending reconfirmation.</p>`
                    : ''
                }
                ${signupsHtml}
            </div>
        `;
    }).join('');

    return `
        <div class="shift-registrations">
            <h4 class="registrations-title">Registrations by Role</h4>
            ${canMarkAttendance ? `<p class="attendance-window-note ${windowInfo.canMark ? 'attendance-window-open' : 'attendance-window-closed'}">${escapeHtml(windowInfo.message)}</p>` : ''}
            <div class="registration-role-grid">
                ${roleBlocks}
            </div>
        </div>
    `;
}

async function toggleShiftRegistrations(shiftId, buttonEl) {
    const tbody = buttonEl ? buttonEl.closest('tbody') : null;
    if (!tbody) return;
    const tbodyId = tbody.id;

    const targetRow = tbody.querySelector(`tr[data-shift-id="${shiftId}"]`);
    if (!targetRow) return;

    const isTogglingSameShift = expandedShiftContext
        && expandedShiftContext.shiftId === shiftId
        && expandedShiftContext.tbodyId === tbodyId;

    if (expandedShiftContext) {
        const previousTbody = document.getElementById(expandedShiftContext.tbodyId);
        if (previousTbody) {
            const previousDetailsRow = previousTbody.querySelector(`.shift-registrations-row[data-shift-id="${expandedShiftContext.shiftId}"]`);
            if (previousDetailsRow) {
                previousDetailsRow.remove();
            }

            const previousButton = previousTbody.querySelector(`button[data-registrations-btn="${expandedShiftContext.shiftId}"]`);
            if (previousButton) {
                previousButton.textContent = 'View Registrations';
            }
        }
    }

    if (isTogglingSameShift) {
        expandedShiftContext = null;
        return;
    }

    expandedShiftContext = {
        shiftId,
        tbodyId,
    };
    if (buttonEl) {
        buttonEl.textContent = 'Hide Registrations';
    }

    const detailsRow = document.createElement('tr');
    detailsRow.className = 'shift-registrations-row';
    detailsRow.dataset.shiftId = String(shiftId);
    detailsRow.innerHTML = `
        <td colspan="4">
            <div class="shift-registrations shift-registrations-loading">Loading registrations...</div>
        </td>
    `;
    targetRow.insertAdjacentElement('afterend', detailsRow);

    try {
        if (!registrationsCache[shiftId]) {
            registrationsCache[shiftId] = await getShiftRegistrations(shiftId);
        }

        if (!expandedShiftContext || expandedShiftContext.shiftId !== shiftId || expandedShiftContext.tbodyId !== tbodyId) return;
        detailsRow.innerHTML = `<td colspan="4">${renderRegistrationsRowContent(registrationsCache[shiftId])}</td>`;
    } catch (error) {
        console.error('Failed to load registrations:', error);
        if (!expandedShiftContext || expandedShiftContext.shiftId !== shiftId || expandedShiftContext.tbodyId !== tbodyId) return;

        detailsRow.innerHTML = `
            <td colspan="4">
                <div class="shift-registrations">
                    <p class="registrations-error">Failed to load registrations: ${escapeHtml(error.message || 'Unknown error')}</p>
                </div>
            </td>
        `;
        showMessage('shifts', `Failed to load registrations: ${error.message}`, 'error');
    }
}

function collapseExpandedRegistrations() {
    if (!expandedShiftContext) return;

    const previousTbody = document.getElementById(expandedShiftContext.tbodyId);
    if (previousTbody) {
        const previousDetailsRow = previousTbody.querySelector(`.shift-registrations-row[data-shift-id="${expandedShiftContext.shiftId}"]`);
        if (previousDetailsRow) {
            previousDetailsRow.remove();
        }

        const previousButton = previousTbody.querySelector(`button[data-registrations-btn="${expandedShiftContext.shiftId}"]`);
        if (previousButton) {
            previousButton.textContent = 'View Registrations';
        }
    }

    expandedShiftContext = null;
}

function getHelpBroadcastModalElements() {
    return {
        modal: document.getElementById('help-broadcast-modal'),
        summary: document.getElementById('help-broadcast-shift-summary'),
        search: document.getElementById('help-broadcast-search'),
        selected: document.getElementById('help-broadcast-selected'),
        count: document.getElementById('help-broadcast-count'),
        results: document.getElementById('help-broadcast-results'),
        resultsTitle: document.getElementById('help-broadcast-results-title'),
        error: document.getElementById('help-broadcast-error'),
        send: document.getElementById('help-broadcast-send')
    };
}

function setHelpBroadcastError(message = '') {
    const { error } = getHelpBroadcastModalElements();
    if (!error) return;
    error.textContent = message;
    error.classList.toggle('app-hidden', !message);
}

function renderHelpBroadcastSelected() {
    const { selected, count, send } = getHelpBroadcastModalElements();
    if (!selected) return;

    if (helpBroadcastSelected.length === 0) {
        selected.innerHTML = '<span class="help-broadcast-selected-empty">No volunteers selected.</span>';
    } else {
        selected.innerHTML = helpBroadcastSelected.map((candidate) => `
            <span class="help-broadcast-chip">
                ${escapeHtml(candidate.full_name || candidate.email || 'Volunteer')}
                <button type="button" aria-label="Remove ${escapeHtml(candidate.full_name || 'volunteer')}" onclick="removeHelpBroadcastRecipient(${candidate.user_id})">&times;</button>
            </span>
        `).join('');
    }

    if (count) {
        count.textContent = `${helpBroadcastSelected.length}/${HELP_BROADCAST_MAX_RECIPIENTS} selected`;
    }
    if (send) {
        send.disabled = helpBroadcastSelected.length === 0;
    }
}

function addHelpBroadcastRecipient(candidate) {
    if (!candidate || !candidate.user_id) return;
    if (helpBroadcastSelected.some((selected) => Number(selected.user_id) === Number(candidate.user_id))) {
        return;
    }
    if (helpBroadcastSelected.length >= HELP_BROADCAST_MAX_RECIPIENTS) {
        setHelpBroadcastError(`Select at most ${HELP_BROADCAST_MAX_RECIPIENTS} volunteers.`);
        return;
    }
    helpBroadcastSelected.push(candidate);
    setHelpBroadcastError('');
    renderHelpBroadcastSelected();
    renderHelpBroadcastCandidates(helpBroadcastCandidateCache, helpBroadcastCandidateQuery);
}

function addHelpBroadcastRecipientById(userId) {
    const candidate = helpBroadcastCandidateMap.get(Number(userId));
    addHelpBroadcastRecipient(candidate);
}

function removeHelpBroadcastRecipient(userId) {
    helpBroadcastSelected = helpBroadcastSelected.filter((candidate) => Number(candidate.user_id) !== Number(userId));
    setHelpBroadcastError('');
    renderHelpBroadcastSelected();
    renderHelpBroadcastCandidates(helpBroadcastCandidateCache, helpBroadcastCandidateQuery);
}

function renderHelpBroadcastCandidates(candidates, query = '') {
    const { results, resultsTitle } = getHelpBroadcastModalElements();
    if (!results) return;

    if (resultsTitle) {
        resultsTitle.textContent = query ? 'Search Results' : 'Suggested Volunteers';
    }

    const selectedIds = new Set(helpBroadcastSelected.map((candidate) => Number(candidate.user_id)));
    const visibleCandidates = (Array.isArray(candidates) ? candidates : [])
        .filter((candidate) => !selectedIds.has(Number(candidate.user_id)))
        .slice(0, query ? 20 : 5);
    helpBroadcastCandidateMap = new Map(
        (Array.isArray(candidates) ? candidates : []).map((candidate) => [Number(candidate.user_id), candidate])
    );

    if (visibleCandidates.length === 0) {
        results.innerHTML = `<p class="help-broadcast-empty">${query ? 'No volunteers match this search.' : 'No suggested volunteers found.'}</p>`;
        return;
    }

    results.innerHTML = visibleCandidates.map((candidate) => {
        const attendedText = candidate.has_attended_pantry ? 'Attended this pantry' : 'Volunteer';
        return `
            <button type="button" class="help-broadcast-candidate" onclick="addHelpBroadcastRecipientById(${Number(candidate.user_id)})">
                <span class="help-broadcast-candidate-main">
                    <strong>${escapeHtml(candidate.full_name || 'Unnamed volunteer')}</strong>
                    <span>${escapeHtml(candidate.email || 'No email')}</span>
                </span>
                <span class="help-broadcast-candidate-meta">
                    <span>${Number(candidate.attendance_score || 0)}%</span>
                    <span>${escapeHtml(attendedText)}</span>
                </span>
            </button>
        `;
    }).join('');
}

async function loadHelpBroadcastCandidates() {
    if (!helpBroadcastShift) return;
    const { search, results } = getHelpBroadcastModalElements();
    const query = search ? search.value.trim() : '';
    const requestToken = ++helpBroadcastRequestToken;

    if (results) {
        results.innerHTML = '<p class="help-broadcast-empty">Loading volunteers...</p>';
    }

    try {
        const candidates = await getHelpBroadcastCandidates(helpBroadcastShift.shift_id, query);
        if (requestToken !== helpBroadcastRequestToken) return;
        helpBroadcastCandidateCache = Array.isArray(candidates) ? candidates : [];
        helpBroadcastCandidateQuery = query;
        renderHelpBroadcastCandidates(candidates, query);
    } catch (error) {
        if (requestToken !== helpBroadcastRequestToken) return;
        if (results) {
            results.innerHTML = `<p class="help-broadcast-empty">Failed to load volunteers: ${escapeHtml(error.message || 'Unknown error')}</p>`;
        }
    }
}

function closeHelpBroadcastModal() {
    const { modal } = getHelpBroadcastModalElements();
    if (modal) {
        modal.classList.add('app-hidden');
    }
    helpBroadcastShift = null;
    helpBroadcastSelected = [];
    helpBroadcastCandidateMap = new Map();
    helpBroadcastCandidateCache = [];
    helpBroadcastCandidateQuery = '';
    helpBroadcastRequestToken += 1;
    if (helpBroadcastSearchTimer) {
        clearTimeout(helpBroadcastSearchTimer);
        helpBroadcastSearchTimer = null;
    }
}

function getTakeAttendanceModalElements() {
    return {
        modal: document.getElementById('take-attendance-modal'),
        summary: document.getElementById('take-attendance-shift-summary'),
        search: document.getElementById('take-attendance-search'),
        note: document.getElementById('take-attendance-window-note'),
        list: document.getElementById('take-attendance-list')
    };
}

function flattenShiftRegistrants(shiftRegistrations) {
    const rows = [];
    (shiftRegistrations?.roles || []).forEach((role) => {
        (role.signups || []).forEach((signup) => {
            rows.push({
                ...signup,
                role_title: role.role_title || signup.role_title || 'Untitled Role',
                required_count: role.required_count,
                filled_count: role.filled_count
            });
        });
    });
    return rows;
}

function renderTakeAttendanceModalList() {
    const { list, note } = getTakeAttendanceModalElements();
    if (!list) return;

    if (!attendanceModalRegistrations) {
        list.innerHTML = '<p class="help-broadcast-empty">Loading registrants...</p>';
        return;
    }

    const windowInfo = getAttendanceWindowInfo(attendanceModalRegistrations.start_time, attendanceModalRegistrations.end_time);
    if (note) {
        note.textContent = windowInfo.message;
        note.classList.toggle('attendance-window-open', windowInfo.canMark);
        note.classList.toggle('attendance-window-closed', !windowInfo.canMark);
    }

    const query = attendanceModalSearchQuery.toLowerCase();
    const rows = flattenShiftRegistrants(attendanceModalRegistrations).filter((signup) => {
        if (!query) return true;
        const user = signup.user || {};
        const haystack = [
            user.full_name,
            user.email,
            signup.role_title,
            signup.signup_status
        ].map((value) => String(value || '').toLowerCase()).join(' ');
        return haystack.includes(query);
    });

    if (rows.length === 0) {
        list.innerHTML = `<p class="help-broadcast-empty">${query ? 'No registrants match this search.' : 'No registrants for this shift.'}</p>`;
        return;
    }

    const disabledAttr = windowInfo.canMark ? '' : 'disabled';
    const disabledReason = escapeHtml(windowInfo.message);
    list.innerHTML = rows.map((signup) => {
        const user = signup.user || {};
        const attendanceInfo = getAttendanceInfo(signup.signup_status);
        return `
            <div class="take-attendance-row">
                <div class="take-attendance-main">
                    <strong>${escapeHtml(user.full_name || 'Unknown volunteer')}</strong>
                    <span>${escapeHtml(user.email || 'No email')}</span>
                    <span>${escapeHtml(signup.role_title || 'Untitled Role')}</span>
                </div>
                <div class="take-attendance-actions">
                    <span class="registrant-status ${attendanceInfo.className}">${escapeHtml(attendanceInfo.label)}</span>
                    <button
                        type="button"
                        class="btn btn-secondary btn-compact btn-attendance btn-attendance-showup"
                        onclick="markSignupAttendance(${signup.signup_id}, 'SHOW_UP', ${attendanceModalRegistrations.shift_id}, this)"
                        ${disabledAttr}
                        title="${disabledReason}"
                    >
                        Mark Show Up
                    </button>
                    <button
                        type="button"
                        class="btn btn-secondary btn-compact btn-attendance btn-attendance-noshow"
                        onclick="markSignupAttendance(${signup.signup_id}, 'NO_SHOW', ${attendanceModalRegistrations.shift_id}, this)"
                        ${disabledAttr}
                        title="${disabledReason}"
                    >
                        Mark No Show
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

async function openTakeAttendanceModal(shiftId, buttonEl = null) {
    const shift = managedShifts.find((candidate) => Number(candidate.shift_id) === Number(shiftId));
    if (!shift) {
        showMessage('shifts', 'Shift not found. Reload the shifts table and try again.', 'error');
        return;
    }

    await withButtonLock(buttonEl, async () => {
        attendanceModalShiftId = Number(shiftId);
        attendanceModalRegistrations = registrationsCache[attendanceModalShiftId] || null;
        attendanceModalSearchQuery = '';
        const { modal, summary, search } = getTakeAttendanceModalElements();
        if (!modal) return;

        if (summary) {
            const startDate = safeDateValue(shift.start_time);
            const endDate = safeDateValue(shift.end_time);
            const timeText = startDate && endDate ? formatLocalTimeRange(startDate, endDate) : 'Time unavailable';
            summary.innerHTML = `
                <strong>${escapeHtml(shift.shift_name || 'Untitled Shift')}</strong>
                <span>${escapeHtml(timeText)}</span>
            `;
        }
        if (search) {
            search.value = '';
        }

        modal.classList.remove('app-hidden');
        renderTakeAttendanceModalList();
        search?.focus();

        try {
            attendanceModalRegistrations = await getShiftRegistrations(attendanceModalShiftId);
            registrationsCache[attendanceModalShiftId] = attendanceModalRegistrations;
            if (Number(attendanceModalShiftId) === Number(shiftId)) {
                renderTakeAttendanceModalList();
            }
        } catch (error) {
            const { list } = getTakeAttendanceModalElements();
            if (list) {
                list.innerHTML = `<p class="help-broadcast-empty">Failed to load registrants: ${escapeHtml(error.message || 'Unknown error')}</p>`;
            }
        }
    });
}

function closeTakeAttendanceModal() {
    const { modal } = getTakeAttendanceModalElements();
    modal?.classList.add('app-hidden');
    attendanceModalShiftId = null;
    attendanceModalRegistrations = null;
    attendanceModalSearchQuery = '';
}

async function openHelpBroadcastModal(shiftId, buttonEl = null) {
    const shift = managedShifts.find((candidate) => Number(candidate.shift_id) === Number(shiftId));
    if (!shift) {
        showMessage('shifts', 'Shift not found. Reload the shifts table and try again.', 'error');
        return;
    }

    await withButtonLock(buttonEl, async () => {
        helpBroadcastShift = shift;
        helpBroadcastSelected = [];
        const { modal, summary, search, results } = getHelpBroadcastModalElements();
        if (!modal) return;

        if (summary) {
            const startDate = safeDateValue(shift.start_time);
            const endDate = safeDateValue(shift.end_time);
            const timeText = startDate && endDate ? formatLocalTimeRange(startDate, endDate) : 'Time unavailable';
            summary.innerHTML = `
                <strong>${escapeHtml(shift.shift_name || 'Untitled Shift')}</strong>
                <span>${escapeHtml(timeText)}</span>
            `;
        }
        if (search) {
            search.value = '';
        }
        if (results) {
            results.innerHTML = '<p class="help-broadcast-empty">Loading volunteers...</p>';
        }
        setHelpBroadcastError('');
        renderHelpBroadcastSelected();
        modal.classList.remove('app-hidden');
        if (search) {
            search.focus();
        }
        await loadHelpBroadcastCandidates();
    });
}

async function submitHelpBroadcast(buttonEl = null) {
    if (!helpBroadcastShift || helpBroadcastSelected.length === 0) return;

    await withButtonLock(buttonEl || getHelpBroadcastModalElements().send, async () => {
        const { send } = getHelpBroadcastModalElements();
        if (send) {
            send.textContent = 'Sending...';
        }
        setHelpBroadcastError('');

        try {
            const recipientIds = helpBroadcastSelected.map((candidate) => Number(candidate.user_id));
            const response = await sendHelpBroadcast(helpBroadcastShift.shift_id, recipientIds);
            const sentCount = Number(response.sent_count || 0);
            const failedCount = Number(response.failed_count || 0);
            closeHelpBroadcastModal();
            showMessage(
                'shifts',
                failedCount > 0
                    ? `Help broadcast sent to ${sentCount} volunteer(s); ${failedCount} failed.`
                    : `Help broadcast sent to ${sentCount} volunteer(s).`,
                failedCount > 0 ? 'info' : 'success'
            );
        } catch (error) {
            const cooldownEndsAt = error.body?.cooldown_ends_at;
            if (error.status === 429 && cooldownEndsAt) {
                const cooldownDate = new Date(cooldownEndsAt);
                const seconds = Math.max(1, Math.ceil((cooldownDate.getTime() - Date.now()) / 1000));
                setHelpBroadcastError(`Please wait ${seconds} second(s) before sending another help broadcast.`);
            } else {
                setHelpBroadcastError(error.message || 'Failed to send help broadcast.');
            }
        }
    });
    const { send } = getHelpBroadcastModalElements();
    if (send) {
        send.textContent = 'Send Broadcast';
        send.disabled = helpBroadcastSelected.length === 0;
    }
}

function getManageShiftsStatusLabel(statusKey) {
    const labels = {
        incoming: 'incoming',
        ongoing: 'ongoing',
        past: 'past',
        cancelled: 'canceled',
    };
    return labels[statusKey] || 'incoming';
}

function getShiftCoverage(shift) {
    const activeRoles = (Array.isArray(shift?.roles) ? shift.roles : [])
        .filter((role) => String(role.status || 'OPEN').toUpperCase() !== 'CANCELLED');
    const totalRequired = activeRoles.reduce((sum, role) => sum + Number(role.required_count || 0), 0);
    const totalFilled = activeRoles.reduce((sum, role) => sum + Number(role.filled_count || 0), 0);
    const openSlots = Math.max(totalRequired - totalFilled, 0);
    const roleGaps = activeRoles
        .map((role) => ({
            ...role,
            filled: Number(role.filled_count || 0),
            required: Number(role.required_count || 0),
            gap: Math.max(Number(role.required_count || 0) - Number(role.filled_count || 0), 0)
        }))
        .filter((role) => role.gap > 0);

    return {
        totalRequired,
        totalFilled,
        openSlots,
        roleGaps,
        hasRoles: activeRoles.length > 0
    };
}

function getShiftCoverageLabel(shift, bucketKey = null) {
    const shiftStatus = String(shift.status || 'OPEN').toUpperCase();
    const bucket = bucketKey || classifyManagedShiftBucket(shift, new Date());
    const coverage = getShiftCoverage(shift);

    if (shiftStatus === 'CANCELLED') return { label: 'Canceled', className: 'coverage-canceled' };
    if (bucket === 'past') return { label: 'Past', className: 'coverage-past' };
    if (bucket === 'ongoing') return { label: 'Ongoing', className: coverage.openSlots > 0 ? 'coverage-needs' : 'coverage-ongoing' };
    if (!coverage.hasRoles) return { label: 'No roles', className: 'coverage-neutral' };
    if (coverage.openSlots > 0) return { label: `Needs ${coverage.openSlots}`, className: 'coverage-needs' };
    return { label: 'Filled', className: 'coverage-filled' };
}

function updateManageShiftsFilterUi() {
    document.querySelectorAll('[data-shift-status-filter]').forEach((button) => {
        button.classList.toggle('active', button.dataset.shiftStatusFilter === manageShiftsStatusFilter);
    });

    const searchInput = document.getElementById('manage-shifts-search-input');
    if (searchInput && searchInput.value !== manageShiftsSearchQuery) {
        searchInput.value = manageShiftsSearchQuery;
    }

    const summary = document.getElementById('manage-shifts-filter-summary');
    if (!summary) {
        return;
    }

    const filteredShifts = getFilteredManagedShifts(managedShifts, new Date());
    const needingHelp = filteredShifts.filter((shift) => getShiftCoverage(shift).openSlots > 0).length;
    const baseLabel = `${filteredShifts.length} ${getManageShiftsStatusLabel(manageShiftsStatusFilter)} shift(s)`;
    const searchLabel = manageShiftsSearchQuery ? ` matching "${manageShiftsSearchQuery}"` : '';
    const gapLabel = needingHelp > 0 ? ` · ${needingHelp} need coverage` : '';
    summary.textContent = `${baseLabel}${searchLabel}${gapLabel}.`;
}

function getFilteredManagedShifts(shifts, now = new Date()) {
    const filtered = (Array.isArray(shifts) ? shifts : []).filter((shift) => {
        const bucket = classifyManagedShiftBucket(shift, now);
        if (bucket !== manageShiftsStatusFilter) {
            return false;
        }

        if (!manageShiftsSearchQuery) {
            return true;
        }

        const shiftName = String(shift.shift_name || '').toLowerCase();
        const roleText = (shift.roles || []).map((role) => String(role.role_title || '')).join(' ').toLowerCase();
        const query = manageShiftsSearchQuery.toLowerCase();
        return shiftName.includes(query) || roleText.includes(query);
    });

    filtered.sort((a, b) => {
        if (manageShiftsStatusFilter === 'incoming') {
            const aNeeds = getShiftCoverage(a).openSlots > 0 ? 0 : 1;
            const bNeeds = getShiftCoverage(b).openSlots > 0 ? 0 : 1;
            if (aNeeds !== bNeeds) return aNeeds - bNeeds;
            return sortByDate(a, b, 'start_time', 'asc');
        }
        if (manageShiftsStatusFilter === 'ongoing') return sortByDate(a, b, 'end_time', 'asc');
        if (manageShiftsStatusFilter === 'past') return sortByDate(a, b, 'end_time', 'desc');
        return sortByDate(a, b, 'start_time', 'desc');
    });
    return filtered;
}

function renderManageShiftsTable() {
    const list = document.getElementById('manage-shifts-card-list');
    if (!list) {
        return;
    }

    collapseExpandedRegistrations();
    updateManageShiftsFilterUi();
    setManageShiftsSubtab(managedShiftPanelMode);
    syncManageShiftsResponsiveView();

    if (!currentPantryId) {
        list.innerHTML = '<div class="empty-state">Please select a pantry first.</div>';
        renderManagedShiftDetailPanel();
        return;
    }

    const filteredShifts = getFilteredManagedShifts(managedShifts, new Date());
    const emptyText = manageShiftsSearchQuery
        ? `No ${getManageShiftsStatusLabel(manageShiftsStatusFilter)} shifts match "${manageShiftsSearchQuery}".`
        : `No ${getManageShiftsStatusLabel(manageShiftsStatusFilter)} shifts.`;

    if (!filteredShifts || filteredShifts.length === 0) {
        list.innerHTML = `<div class="empty-state">${escapeHtml(emptyText)}</div>`;
        renderManagedShiftDetailPanel();
        return;
    }

    if (
        managedShiftPanelMode !== 'create'
        && selectedManagedShiftId
        && !filteredShifts.some((shift) => Number(shift.shift_id) === Number(selectedManagedShiftId))
    ) {
        selectedManagedShiftId = null;
        managedShiftPanelMode = 'create';
        setManageShiftsSubtab('create');
    }

    list.innerHTML = filteredShifts.map((shift) => renderManagedShiftCard(shift)).join('');
    renderManagedShiftDetailPanel(selectedManagedShiftId ? registrationsCache[Number(selectedManagedShiftId)] : null);
}

function renderManagedShiftCard(shift) {
    const startDate = safeDateValue(shift.start_time);
    const endDate = safeDateValue(shift.end_time);
    const timeText = startDate && endDate ? formatLocalTimeRange(startDate, endDate) : 'Time unavailable';
    const shiftStatus = String(shift.status || 'OPEN').toUpperCase();
    const bucket = classifyManagedShiftBucket(shift, new Date());
    const coverage = getShiftCoverage(shift);
    const coverageLabel = getShiftCoverageLabel(shift, bucket);
    const selectedClass = Number(selectedManagedShiftId) === Number(shift.shift_id) && managedShiftPanelMode !== 'create'
        ? 'selected'
        : '';
    const progress = coverage.totalRequired > 0
        ? Math.min(100, Math.round((coverage.totalFilled / coverage.totalRequired) * 100))
        : 0;
    const gapText = coverage.roleGaps.length > 0
        ? coverage.roleGaps.slice(0, 2).map((role) => `${escapeHtml(role.role_title || 'Role')} -${role.gap}`).join(' · ')
        : 'No role gaps';
    const moreGaps = coverage.roleGaps.length > 2 ? ` +${coverage.roleGaps.length - 2} more` : '';

    return `
        <button type="button" class="manage-shift-card ${selectedClass}" onclick="selectManagedShift(${Number(shift.shift_id)}, this)">
            <span class="manage-shift-card-top">
                <span class="manage-shift-card-title">${escapeHtml(shift.shift_name || 'Untitled Shift')}</span>
                <span class="coverage-pill ${coverageLabel.className}">${escapeHtml(coverageLabel.label)}</span>
            </span>
            <span class="manage-shift-card-meta">
                <span>${escapeHtml(timeText)}</span>
                <span class="status-badge ${toStatusClass('shift-status', shiftStatus)}">${escapeHtml(shiftStatus)}</span>
                ${shift.is_recurring ? '<span class="status-badge recurrence-badge">Recurring</span>' : ''}
            </span>
            <span class="coverage-meter" aria-hidden="true">
                <span style="width: ${progress}%"></span>
            </span>
            <span class="manage-shift-card-coverage">
                <strong>${coverage.totalFilled}/${coverage.totalRequired}</strong>
                <span>${escapeHtml(gapText)}${escapeHtml(moreGaps)}</span>
            </span>
        </button>
    `;
}

async function selectManagedShift(shiftId, buttonEl = null) {
    await withButtonLock(buttonEl, async () => {
        selectedManagedShiftId = Number(shiftId);
        managedShiftPanelMode = 'detail';
        setManageShiftsMobileView('detail');
        setManageShiftsSubtab('detail');
        resetEditShiftForm({ preserveSelection: true });
        renderManageShiftsTable();
        await loadSelectedShiftRegistrations(shiftId);
    });
}

function showCreateShiftPanel() {
    selectedManagedShiftId = null;
    managedShiftPanelMode = 'create';
    setManageShiftsMobileView(isManageShiftsPhoneViewport() ? 'create' : 'queue');
    resetEditShiftForm({ preserveSelection: true });
    setManageShiftsSubtab('create');
    renderManageShiftsTable();
}

function getSelectedManagedShift() {
    return managedShifts.find((shift) => Number(shift.shift_id) === Number(selectedManagedShiftId)) || null;
}

function renderManagedShiftDetailPanel(registrations = null, registrationsError = '') {
    const detailCard = document.getElementById('manage-shift-detail-card');
    if (!detailCard || managedShiftPanelMode !== 'detail') {
        return;
    }

    const shift = getSelectedManagedShift();
    if (!shift) {
        detailCard.innerHTML = '<div class="empty-state">Select a shift to inspect coverage and registrations.</div>';
        return;
    }

    const startDate = safeDateValue(shift.start_time);
    const endDate = safeDateValue(shift.end_time);
    const timeText = startDate && endDate ? formatLocalTimeRange(startDate, endDate) : 'Time unavailable';
    const bucket = classifyManagedShiftBucket(shift, new Date());
    const isPastBucket = bucket === 'past';
    const shiftStatus = String(shift.status || 'OPEN').toUpperCase();
    const coverage = getShiftCoverage(shift);
    const coverageLabel = getShiftCoverageLabel(shift, bucket);
    const canBroadcast = !isPastBucket && shiftStatus !== 'CANCELLED' && coverage.openSlots > 0;
    const rolesHtml = renderManagedShiftRoleCoverage(shift);
    const registrationsHtml = registrations
        ? renderRegistrationsRowContent(registrations, { showAttendanceActions: false })
        : `<div class="shift-registrations shift-registrations-loading">${registrationsError ? escapeHtml(registrationsError) : 'Loading registrations...'}</div>`;
    const cancelOrRevokeButton = isPastBucket
        ? '<button class="btn btn-secondary btn-sm" disabled title="Past shifts are locked">Locked</button>'
        : shiftStatus === 'CANCELLED'
            ? `<button class="btn btn-success btn-sm" onclick="revokeShiftConfirm(${Number(shift.shift_id)}, this)">Revoke</button>`
            : `<button class="btn btn-sm btn-cancel-shift" onclick="cancelShiftConfirm(${Number(shift.shift_id)}, this)">Cancel Shift</button>`;

    detailCard.innerHTML = `
        <button type="button" class="btn btn-secondary btn-sm manage-shifts-mobile-back" onclick="backToManagedShiftQueue()">Back to shifts</button>
        <div class="manage-shift-detail-header">
            <div>
                <h2 class="card-title">${escapeHtml(shift.shift_name || 'Untitled Shift')}</h2>
                <p class="shift-view-copy">${escapeHtml(timeText)}</p>
            </div>
            <span class="coverage-pill ${coverageLabel.className}">${escapeHtml(coverageLabel.label)}</span>
        </div>
        <div class="manage-shift-detail-badges">
            <span class="status-badge ${toStatusClass('shift-status', shiftStatus)}">${escapeHtml(shiftStatus)}</span>
            ${shift.is_recurring ? '<span class="status-badge recurrence-badge">Recurring</span>' : ''}
        </div>
        <div class="coverage-summary-panel">
            <div>
                <span class="coverage-summary-number">${coverage.totalFilled}/${coverage.totalRequired}</span>
                <span class="coverage-summary-label">slots filled</span>
            </div>
            <div>
                <span class="coverage-summary-number">${coverage.openSlots}</span>
                <span class="coverage-summary-label">people needed</span>
            </div>
        </div>
        <div class="manage-shift-panel-actions">
            <button class="btn btn-primary btn-sm" onclick="openEditShift(${Number(shift.shift_id)}, this)" ${isPastBucket ? 'disabled title="Past shifts are locked"' : ''}>Edit</button>
            <button class="btn btn-sm btn-broadcast-help" onclick="openHelpBroadcastModal(${Number(shift.shift_id)}, this)" ${canBroadcast ? '' : 'disabled title="Broadcast is available only when this open shift has coverage gaps"'}>Broadcast Help</button>
            <button class="btn btn-sm btn-take-attendance" onclick="openTakeAttendanceModal(${Number(shift.shift_id)}, this)" ${shiftStatus === 'CANCELLED' ? 'disabled title="Attendance is unavailable for canceled shifts"' : ''}>Take Attendance</button>
            ${cancelOrRevokeButton}
        </div>
        <div class="manage-shift-section">
            <h3>Coverage by Role</h3>
            ${rolesHtml}
        </div>
    `;
}

function renderManagedShiftRoleCoverage(shift) {
    const roles = (Array.isArray(shift.roles) ? shift.roles : [])
        .filter((role) => String(role.status || 'OPEN').toUpperCase() !== 'CANCELLED');
    if (roles.length === 0) {
        return '<p class="registrations-empty">No roles configured for this shift.</p>';
    }

    return `
        <div class="manage-shift-role-list">
            ${roles.map((role) => {
                const filled = Number(role.filled_count || 0);
                const required = Number(role.required_count || 0);
                const gap = Math.max(required - filled, 0);
                const progress = required > 0 ? Math.min(100, Math.round((filled / required) * 100)) : 0;
                return `
                    <div class="manage-shift-role-row">
                        <div>
                            <strong>${escapeHtml(role.role_title || 'Untitled Role')}</strong>
                            <span>${filled}/${required} filled</span>
                        </div>
                        <div class="manage-shift-role-right">
                            <span class="coverage-pill ${gap > 0 ? 'coverage-needs' : 'coverage-filled'}">${gap > 0 ? `Needs ${gap}` : 'Filled'}</span>
                            <span class="coverage-meter" aria-hidden="true"><span style="width: ${progress}%"></span></span>
                        </div>
                    </div>
                `;
            }).join('')}
        </div>
    `;
}

async function loadSelectedShiftRegistrations(shiftId) {
    if (!shiftId || managedShiftPanelMode !== 'detail') return;
    const normalizedShiftId = Number(shiftId);
    try {
        const registrations = await getShiftRegistrations(normalizedShiftId);
        registrationsCache[normalizedShiftId] = registrations;
        if (managedShiftPanelMode === 'detail' && Number(selectedManagedShiftId) === normalizedShiftId) {
            renderManagedShiftDetailPanel(registrations);
        }
    } catch (error) {
        if (managedShiftPanelMode === 'detail' && Number(selectedManagedShiftId) === normalizedShiftId) {
            renderManagedShiftDetailPanel(null, `Failed to load registrations: ${error.message || 'Unknown error'}`);
        }
        showMessage('shifts', `Failed to load registrations: ${error.message}`, 'error');
    }
}

// Load shifts table (admin)
async function loadShiftsTable() {
    const list = document.getElementById('manage-shifts-card-list');

    try {
        registrationsCache = {};

        if (!currentPantryId) {
            managedShifts = [];
            if (isManageShiftsPhoneViewport()) {
                setManageShiftsMobileView('queue');
            }
            renderManageShiftsTable();
            return;
        }

        managedShifts = await getShifts(currentPantryId);
        renderManageShiftsTable();
        if (managedShiftPanelMode === 'detail' && selectedManagedShiftId) {
            await loadSelectedShiftRegistrations(selectedManagedShiftId);
        }
    } catch (error) {
        console.error('Failed to load shifts table:', error);
        managedShifts = [];
        if (list) {
            list.innerHTML = `<div class="empty-state">Failed to load shifts: ${escapeHtml(error.message)}</div>`;
        }
        showMessage('shifts', `Failed to load shifts: ${error.message}`, 'error');
    }
}

function buildEditRoleRow(role = null) {
    const roleId = role && role.shift_role_id ? String(role.shift_role_id) : '';
    const roleTitle = role && role.role_title ? role.role_title : '';
    const roleCount = role && role.required_count ? Number(role.required_count) : 1;

    const roleGroup = document.createElement('div');
    roleGroup.className = 'role-input-group';
    roleGroup.dataset.roleId = roleId;
    roleGroup.innerHTML = `
        <div class="form-grid">
            <div class="form-group">
                <label>Role Title *</label>
                <input type="text" class="edit-role-title" value="${escapeHtml(roleTitle)}" placeholder="e.g., Food Sorter" required>
            </div>
            <div class="form-group">
                <label>Required Count *</label>
                <input type="number" class="edit-role-count" min="1" value="${roleCount}" required>
            </div>
            <div class="form-group role-input-actions">
                <label>Action</label>
                <button type="button" class="btn btn-danger remove-edit-role-btn">Remove</button>
            </div>
        </div>
    `;
    roleGroup.querySelector('.remove-edit-role-btn').addEventListener('click', () => {
        roleGroup.remove();
    });
    return roleGroup;
}

function resetEditShiftForm(options = {}) {
    editingShiftSnapshot = null;
    document.getElementById('edit-shift-id').value = '';
    document.getElementById('edit-shift-name').value = '';
    document.getElementById('edit-shift-start').value = '';
    document.getElementById('edit-shift-end').value = '';
    document.getElementById('edit-roles-container').innerHTML = '';
    if (!options.preserveSelection && managedShiftPanelMode === 'edit') {
        managedShiftPanelMode = selectedManagedShiftId ? 'detail' : 'create';
        setManageShiftsMobileView(managedShiftPanelMode);
    }
    setManageShiftsSubtab(managedShiftPanelMode);
    resetEditRecurrenceForm();
}

async function openEditShift(shiftId, buttonEl = null) {
    await withButtonLock(buttonEl, async () => {
        try {
            selectedManagedShiftId = Number(shiftId);
            managedShiftPanelMode = 'edit';
            setManageShiftsMobileView('edit');
            setManageShiftsSubtab('edit');
            const shift = await getShift(shiftId);
            editingShiftSnapshot = shift;

            document.getElementById('edit-shift-id').value = String(shift.shift_id);
            document.getElementById('edit-shift-name').value = shift.shift_name || '';
            document.getElementById('edit-shift-start').value = formatDateTimeForInput(shift.start_time);
            document.getElementById('edit-shift-end').value = formatDateTimeForInput(shift.end_time);

            const container = document.getElementById('edit-roles-container');
            container.innerHTML = '';
            const roles = shift.roles || [];
            if (roles.length === 0) {
                container.appendChild(buildEditRoleRow(null));
            } else {
                roles.forEach(role => {
                    container.appendChild(buildEditRoleRow(role));
                });
            }

            populateEditRecurrenceForm(shift);
            renderManageShiftsTable();
            document.getElementById('edit-shift-card').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        } catch (error) {
            showMessage('shifts', `Failed to load shift for editing: ${error.message}`, 'error');
        }
    });
}

function collectAffectedContacts(responses) {
    const seen = new Set();
    let affectedCount = 0;

    responses.forEach(response => {
        if (!response) return;
        affectedCount += Number(response.affected_signup_count || 0);
        const contacts = response.affected_volunteer_contacts || [];
        contacts.forEach(contact => {
            if (!contact || !contact.email) return;
            seen.add(contact.email);
        });
    });

    return {
        affectedCount,
        uniqueVolunteers: seen.size
    };
}

// Cancel shift with confirmation
async function cancelShiftConfirm(shiftId, buttonEl = null) {
    const shift = managedShifts.find((candidate) => Number(candidate.shift_id) === Number(shiftId)) || editingShiftSnapshot;
    let applyScope = 'single';
    if (shift && shift.is_recurring) {
        const choice = await promptRecurringScope('cancel');
        if (!choice || choice === 'cancel') {
            return;
        }
        applyScope = choice;
    } else if (!confirm('Cancel this shift? Volunteers will need to reconfirm and no new signups will be accepted.')) {
        return;
    }

    await withButtonLock(buttonEl, async () => {
        try {
            const response = await cancelShiftWithScope(shiftId, applyScope);
            const affected = response.affected_signup_count || 0;
            const cancelledOccurrences = Number(response.cancelled_occurrence_count || 0);
            const recurringText = applyScope === 'future' && cancelledOccurrences > 0
                ? ` ${cancelledOccurrences} occurrence(s) were cancelled.`
                : '';
            showMessage('shifts', `Shift cancelled successfully! ${affected} volunteer signup(s) moved to pending confirmation and volunteers were notified.${recurringText}`, 'success');
            await loadShiftsTable();
            await loadCalendarShifts(); // Update calendar view too
            const myShiftsTab = document.getElementById('content-my-shifts');
            if (myShiftsTab && myShiftsTab.classList.contains('active')) {
                await loadMyRegisteredShifts();
            }
        } catch (error) {
            showMessage('shifts', `Cancel failed: ${error.message}`, 'error');
        }
    });
}

async function revokeShiftConfirm(shiftId, buttonEl = null) {
    if (!confirm('Revoke this cancelled shift? Previously signed-up volunteers will stay pending confirmation.')) return;

    await withButtonLock(buttonEl, async () => {
        try {
            const response = await updateShift(shiftId, { status: 'OPEN' });
            const affected = response.affected_signup_count || 0;
            const notifiedMsg = affected > 0
                ? ` ${affected} volunteer(s) were notified to review and reconfirm.`
                : '';
            showMessage('shifts', `Shift revoked successfully! Volunteers remain pending confirmation until they reconfirm.${notifiedMsg}`, 'success');
            await loadShiftsTable();
            await loadCalendarShifts();
            const myShiftsTab = document.getElementById('content-my-shifts');
            if (myShiftsTab && myShiftsTab.classList.contains('active')) {
                await loadMyRegisteredShifts();
            }
        } catch (error) {
            showMessage('shifts', `Revoke failed: ${error.message}`, 'error');
        }
    });
}

// Setup event listeners
function setupEventListeners() {
    setManageShiftsSubtab(activeManageShiftsSubtab);
    setManageShiftsMobileView('queue');
    setAdminSubtab(activeAdminSubtab);
    setMyShiftsViewMode(myShiftsViewMode);
    lastAdminUsersPhoneViewport = isPhoneViewport();
    lastVolunteerPantriesCompactViewport = isVolunteerPantryCompactViewport();
    window.addEventListener('resize', handleAdminUsersViewportChange);
    window.addEventListener('resize', handleVolunteerPantriesViewportChange);
    window.addEventListener('resize', scheduleAppTourReposition);
    window.addEventListener('resize', syncManageShiftsResponsiveView);
    if (typeof initializeCalendarUi === 'function') {
        initializeCalendarUi();
    }

    document.getElementById('manage-shifts-create-btn')?.addEventListener('click', showCreateShiftPanel);
    document.querySelectorAll('[data-manage-mobile-back="queue"]').forEach((button) => {
        button.addEventListener('click', backToManagedShiftQueue);
    });

    document.querySelectorAll('.manage-shifts-subtab').forEach((button) => {
        button.addEventListener('click', async () => {
            const targetSubtab = button.dataset.manageSubtab === 'view' ? 'view' : 'create';
            setManageShiftsSubtab(targetSubtab);
            if (targetSubtab === 'view') {
                await withButtonLock(button, loadShiftsTable);
            }
        });
    });

    document.getElementById('manage-shifts-search-input')?.addEventListener('input', () => {
        manageShiftsSearchQuery = document.getElementById('manage-shifts-search-input')?.value.trim() || '';
        renderManageShiftsTable();
        if (managedShiftPanelMode === 'detail' && selectedManagedShiftId && !registrationsCache[Number(selectedManagedShiftId)]) {
            loadSelectedShiftRegistrations(selectedManagedShiftId);
        }
    });

    document.querySelectorAll('[data-shift-status-filter]').forEach((button) => {
        button.addEventListener('click', () => {
            const nextFilter = button.dataset.shiftStatusFilter || 'incoming';
            if (!['incoming', 'ongoing', 'past', 'cancelled'].includes(nextFilter)) {
                return;
            }
            manageShiftsStatusFilter = nextFilter;
            renderManageShiftsTable();
            if (managedShiftPanelMode === 'detail' && selectedManagedShiftId && !registrationsCache[Number(selectedManagedShiftId)]) {
                loadSelectedShiftRegistrations(selectedManagedShiftId);
            }
        });
    });

    document.querySelectorAll('.admin-subtab').forEach((button) => {
        button.addEventListener('click', async () => {
            const targetSubtab = button.dataset.adminSubtab === 'users' ? 'users' : 'pantries';
            setAdminSubtab(targetSubtab);
            await withButtonLock(button, loadAdminTab);
        });
    });

    document.getElementById('volunteer-pantry-search')?.addEventListener('input', () => {
        volunteerPantrySearchQuery = document.getElementById('volunteer-pantry-search')?.value.trim() || '';
        renderVolunteerPantryDirectory();
    });

    document.getElementById('volunteer-pantry-sort')?.addEventListener('change', () => {
        volunteerPantrySort = document.getElementById('volunteer-pantry-sort')?.value || 'name-asc';
        renderVolunteerPantryDirectory();
    });

    document.querySelectorAll('[data-pantry-subscription-filter]').forEach((button) => {
        button.addEventListener('click', () => {
            const nextFilter = button.dataset.pantrySubscriptionFilter || 'all';
            if (!['all', 'subscribed', 'unsubscribed'].includes(nextFilter)) {
                return;
            }
            volunteerPantrySubscriptionFilter = nextFilter;
            renderVolunteerPantryDirectory();
        });
    });

    document.getElementById('volunteer-pantries-list')?.addEventListener('click', (event) => {
        const subscribeButton = event.target instanceof HTMLElement ? event.target.closest('[data-volunteer-subscribe-id]') : null;
        if (subscribeButton instanceof HTMLElement) {
            toggleVolunteerPantrySubscription(subscribeButton);
            return;
        }

        const target = event.target instanceof HTMLElement ? event.target.closest('[data-volunteer-pantry-id]') : null;
        if (!(target instanceof HTMLElement)) {
            return;
        }

        const pantryId = Number(target.dataset.volunteerPantryId || 0) || null;
        if (isVolunteerPantryCompactViewport() && pantryId && Number(selectedVolunteerPantryId) === pantryId) {
            selectedVolunteerPantryId = null;
            renderVolunteerPantryDirectory();
            return;
        }

        selectedVolunteerPantryId = pantryId;
        renderVolunteerPantryDirectory();
    });

    document.getElementById('volunteer-pantry-detail')?.addEventListener('click', async (event) => {
        const target = event.target instanceof HTMLElement ? event.target.closest('[data-volunteer-subscribe-id]') : null;
        if (!(target instanceof HTMLElement)) {
            return;
        }
        await toggleVolunteerPantrySubscription(target);
    });

    document.getElementById('assign-pantry-search')?.addEventListener('input', () => {
        selectedAssignPantryId = null;
        const hiddenInput = document.getElementById('assign-pantry');
        const selectedEl = document.getElementById('assign-pantry-selected');
        if (hiddenInput) {
            hiddenInput.value = '';
        }
        if (selectedEl) {
            selectedEl.innerHTML = '';
            selectedEl.classList.add('app-hidden');
        }
        renderAssignPantrySearchResults();
    });

    document.getElementById('assign-pantry-search')?.addEventListener('focus', () => {
        renderAssignPantrySearchResults();
    });

    document.getElementById('assign-pantry-results')?.addEventListener('click', (event) => {
        const target = event.target instanceof HTMLElement ? event.target.closest('[data-pantry-option-id]') : null;
        if (!(target instanceof HTMLElement)) {
            return;
        }
        selectAssignPantry(parseInt(target.dataset.pantryOptionId || '0', 10));
    });

    document.getElementById('assign-lead-search')?.addEventListener('input', () => {
        selectedPantryLeadId = null;
        const hiddenInput = document.getElementById('assign-lead');
        const selectedEl = document.getElementById('assign-lead-selected');
        if (hiddenInput) {
            hiddenInput.value = '';
        }
        if (selectedEl) {
            selectedEl.innerHTML = '';
            selectedEl.classList.add('app-hidden');
        }
        renderPantryLeadSearchResults();
    });

    document.getElementById('assign-lead-search')?.addEventListener('focus', () => {
        renderPantryLeadSearchResults();
    });

    document.getElementById('assign-lead-results')?.addEventListener('click', (event) => {
        const target = event.target instanceof HTMLElement ? event.target.closest('[data-lead-option-id]') : null;
        if (!(target instanceof HTMLElement)) {
            return;
        }
        selectPantryLead(parseInt(target.dataset.leadOptionId || '0', 10));
    });

    document.addEventListener('click', (event) => {
        const leadShell = document.querySelector('.lead-search-shell');
        const leadResultsEl = document.getElementById('assign-lead-results');
        if (leadShell && leadResultsEl && !leadShell.contains(event.target)) {
            leadResultsEl.classList.add('app-hidden');
        }

        const pantryShell = document.querySelector('.pantry-search-shell');
        const pantryResultsEl = document.getElementById('assign-pantry-results');
        if (pantryShell && pantryResultsEl && !pantryShell.contains(event.target)) {
            pantryResultsEl.classList.add('app-hidden');
        }
    });

    document.getElementById('admin-pantry-search')?.addEventListener('input', (event) => {
        adminPantrySearchQuery = event.target.value.trim();
        const filteredPantries = getFilteredAdminPantries();
        if (selectedAdminPantryId && !filteredPantries.some((pantry) => intValue(pantry.pantry_id) === intValue(selectedAdminPantryId))) {
            selectedAdminPantryId = filteredPantries.length > 0 ? intValue(filteredPantries[0].pantry_id) : null;
            adminPantryLeadSearchQuery = '';
        }
        renderAdminPantryWorkspace();
    });

    document.getElementById('admin-pantries-list')?.addEventListener('click', (event) => {
        const target = event.target instanceof HTMLElement ? event.target.closest('[data-admin-pantry-id]') : null;
        if (!(target instanceof HTMLElement)) {
            return;
        }
        selectedAdminPantryId = intValue(target.dataset.adminPantryId || 0);
        adminPantryLeadSearchQuery = '';
        renderAdminPantryWorkspace();
    });

    document.getElementById('admin-pantry-detail-panel')?.addEventListener('input', (event) => {
        const target = event.target;
        if (!(target instanceof HTMLInputElement) || target.id !== 'admin-pantry-lead-search') {
            return;
        }
        adminPantryLeadSearchQuery = target.value.trim();
        renderAdminPantryLeadSearchResults();
    });

    document.getElementById('admin-pantry-detail-panel')?.addEventListener('click', async (event) => {
        const target = event.target instanceof HTMLElement ? event.target : null;
        const editButton = target?.closest('[data-edit-admin-pantry]');
        const deleteButton = target?.closest('[data-delete-admin-pantry]');
        const addButton = target?.closest('[data-add-admin-pantry-lead]');
        const removeButton = target?.closest('[data-remove-admin-pantry-lead]');

        if (editButton instanceof HTMLElement) {
            openEditPantryModal(getAdminPantryById(editButton.dataset.editAdminPantry));
            return;
        }
        if (deleteButton instanceof HTMLElement) {
            await deleteAdminPantry(intValue(deleteButton.dataset.deleteAdminPantry || 0), deleteButton);
            return;
        }
        if (addButton instanceof HTMLElement) {
            await assignAdminPantryLead(intValue(addButton.dataset.addAdminPantryLead || 0), addButton);
            return;
        }
        if (removeButton instanceof HTMLElement) {
            await removeAdminPantryLead(intValue(removeButton.dataset.removeAdminPantryLead || 0), removeButton);
        }
    });

    document.querySelectorAll('[data-my-shifts-view]').forEach((button) => {
        button.addEventListener('click', () => {
            setMyShiftsViewMode(button.dataset.myShiftsView || 'calendar');
        });
    });

    document.getElementById('my-shifts-list-search')?.addEventListener('input', () => {
        myShiftsListFilters.search = document.getElementById('my-shifts-list-search')?.value.trim() || '';
        renderMyShiftList(myRegisteredSignups);
    });

    document.getElementById('my-shifts-list-pantry-filter')?.addEventListener('change', () => {
        myShiftsListFilters.pantryId = document.getElementById('my-shifts-list-pantry-filter')?.value || 'all';
        renderMyShiftList(myRegisteredSignups);
    });

    document.getElementById('my-shifts-list-time-filter')?.addEventListener('change', () => {
        myShiftsListFilters.timeBucket = document.getElementById('my-shifts-list-time-filter')?.value || 'all';
        renderMyShiftList(myRegisteredSignups);
    });

    document.getElementById('my-shifts-list-status-filter')?.addEventListener('change', () => {
        myShiftsListFilters.status = document.getElementById('my-shifts-list-status-filter')?.value || 'all';
        renderMyShiftList(myRegisteredSignups);
    });

    document.getElementById('my-shifts-list-sort')?.addEventListener('change', () => {
        myShiftsListFilters.sort = document.getElementById('my-shifts-list-sort')?.value || 'date-asc';
        renderMyShiftList(myRegisteredSignups);
    });

    document.getElementById('my-shifts-list-clear-filters')?.addEventListener('click', () => {
        myShiftsListFilters = { search: '', pantryId: 'all', timeBucket: 'all', status: 'all', sort: 'date-asc' };
        document.getElementById('my-shifts-list-status-filter').value = 'all';
        syncMyShiftsListFilters();
        renderMyShiftList(myRegisteredSignups);
    });

    // Tab navigation
    document.querySelectorAll('.nav-tab').forEach(tab => {
        tab.addEventListener('click', async () => {
            await withButtonLock(tab, () => activateTab(tab.dataset.tab));
        });
    });

    document.getElementById('start-tour-btn')?.addEventListener('click', async (event) => {
        await withButtonLock(event.currentTarget, () => openAppTour({ forceRequired: false }));
    });

    document.getElementById('app-tour-nudge-start-btn')?.addEventListener('click', async (event) => {
        dismissAppTourNudge();
        await withButtonLock(event.currentTarget, () => openAppTour({ forceRequired: false }));
    });

    document.getElementById('app-tour-nudge-skip-btn')?.addEventListener('click', () => {
        dismissAppTourNudge();
    });

    document.getElementById('app-tour-backdrop')?.addEventListener('click', () => {
        // The tour must be dismissed through its own controls.
    });

    document.getElementById('admin-user-search-btn')?.addEventListener('click', async (event) => {
        await withButtonLock(event.currentTarget, loadAdminUsers);
    });

    document.getElementById('admin-user-search')?.addEventListener('keydown', async (event) => {
        if (event.key === 'Enter') {
            event.preventDefault();
            await loadAdminUsers();
        }
    });

    document.getElementById('admin-user-role-filter')?.addEventListener('change', async () => {
        await loadAdminUsers();
    });

    document.getElementById('my-account-profile-form').addEventListener('submit', async (event) => {
        event.preventDefault();

        const fullName = document.getElementById('account-full-name').value.trim();
        const phoneNumber = document.getElementById('account-phone-number').value.trim();
        if (!fullName) {
            showMessage('my-account', 'Full name is required.', 'error');
            return;
        }

        await withButtonLock(getSubmitButtonFromEvent(event), async () => {
            try {
                currentUser = await updateCurrentUserProfile({
                    full_name: fullName,
                    phone_number: phoneNumber
                });
                await refreshCurrentUserState();
                showMessage('my-account', 'Basic information updated successfully.', 'success');
            } catch (error) {
                showMessage('my-account', `Failed to update profile: ${error.message}`, 'error');
            }
        });
    });

    document.getElementById('my-account-email-form').addEventListener('submit', async (event) => {
        event.preventDefault();

        if (!currentUser?.email_change_supported) {
            showMessage('my-account', 'Email changes are unavailable for this account.', 'error');
            return;
        }

        const newEmail = document.getElementById('account-new-email').value.trim().toLowerCase();
        if (!newEmail) {
            showMessage('my-account', 'Enter a new email address first.', 'error');
            return;
        }

        await withButtonLock(getSubmitButtonFromEvent(event), async () => {
            try {
                await prepareCurrentUserEmailChange(newEmail);
                const result = await window.requestFirebaseEmailChange(currentUser, newEmail);
                const note = document.getElementById('my-account-email-note');
                if (note && result?.message) {
                    note.className = 'account-note account-note-success';
                    note.textContent = result.message;
                }
                document.getElementById('account-new-email').value = '';
                showMessage('my-account', 'Email verification started. Confirm the change from your email, then <b>log out this tab</b> and sign in again.', 'success');
            } catch (error) {
                updateAccountEmailUi();
                showMessage('my-account', `Failed to start email change: ${error.message}`, 'error');
            }
        });
    });

    document.getElementById('connect-google-calendar-btn')?.addEventListener('click', async (event) => {
        await withButtonLock(event.currentTarget, async () => {
            try {
                const message = await connectGoogleCalendarFromAccount();
                showMessage('my-account', message || 'Google Calendar sync connected.', 'success');
            } catch (error) {
                showMessage('my-account', `Failed to connect Google Calendar: ${error.message}`, 'error');
            }
        });
    });

    document.getElementById('disconnect-google-calendar-btn')?.addEventListener('click', async (event) => {
        const confirmed = confirm('Turn off automatic Google Calendar sync for this account? Existing synced events will be removed from Google Calendar.');
        if (!confirmed) {
            return;
        }

        await withButtonLock(event.currentTarget, async () => {
            try {
                await disconnectGoogleCalendar();
                await loadGoogleCalendarStatus();
                showMessage('my-account', 'Automatic Google Calendar sync has been disconnected.', 'success');
            } catch (error) {
                showMessage('my-account', `Failed to disconnect Google Calendar: ${error.message}`, 'error');
            }
        });
    });

    document.getElementById('delete-account-btn').addEventListener('click', async () => {
        if (!currentUser) {
            showMessage('my-account', 'No user is loaded.', 'error');
            return;
        }

        const confirmed = confirm('Delete your account permanently? This cannot be undone.');
        if (!confirmed) {
            return;
        }

        await withButtonLock(event.currentTarget, async () => {
            try {
                let payload = {};
                if (currentUser.auth_mode === 'firebase' && currentUser.auth_provider === 'firebase') {
                    const result = await window.requestFirebaseAccountDeletion(currentUser);
                    payload = { id_token: result.idToken };
                }

                await deleteCurrentUserAccount(payload);
                window.location.reload();
            } catch (error) {
                showMessage('my-account', `Failed to delete account: ${error.message}`, 'error');
            }
        });
    });

    // Edit pantry modal - cancel
    document.getElementById('cancel-edit-pantry-btn').addEventListener('click', () => {
        document.getElementById('edit-pantry-modal').classList.add('app-hidden');
    });

    document.getElementById('edit-pantry-modal').addEventListener('click', (event) => {
        if (event.target === event.currentTarget) {
            event.currentTarget.classList.add('app-hidden');
        }
    });

    document.getElementById('notification-modal-close-btn').addEventListener('click', () => {
        document.getElementById('notification-modal').classList.add('app-hidden');
    });

    document.getElementById('notification-modal').addEventListener('click', (event) => {
        if (event.target === event.currentTarget) {
            event.currentTarget.classList.add('app-hidden');
        }
    });

    document.getElementById('recurring-scope-modal-close')?.addEventListener('click', () => {
        closeRecurringScopeModal(null);
    });

    document.getElementById('recurring-scope-modal')?.addEventListener('click', (event) => {
        const target = event.target instanceof HTMLElement ? event.target : null;
        if (target === event.currentTarget) {
            closeRecurringScopeModal(null);
            return;
        }
        const scopeButton = target?.closest('[data-recurring-scope-choice]');
        if (!(scopeButton instanceof HTMLElement)) {
            return;
        }
        closeRecurringScopeModal(scopeButton.dataset.recurringScopeChoice || null);
    });

    document.getElementById('help-broadcast-close')?.addEventListener('click', closeHelpBroadcastModal);
    document.getElementById('help-broadcast-cancel')?.addEventListener('click', closeHelpBroadcastModal);
    document.getElementById('help-broadcast-modal')?.addEventListener('click', (event) => {
        if (event.target === event.currentTarget) {
            closeHelpBroadcastModal();
        }
    });
    document.getElementById('help-broadcast-send')?.addEventListener('click', (event) => submitHelpBroadcast(event.currentTarget));
    document.getElementById('help-broadcast-search')?.addEventListener('input', () => {
        if (helpBroadcastSearchTimer) {
            clearTimeout(helpBroadcastSearchTimer);
        }
        helpBroadcastSearchTimer = setTimeout(() => {
            loadHelpBroadcastCandidates();
        }, 250);
    });

    document.getElementById('take-attendance-close')?.addEventListener('click', closeTakeAttendanceModal);
    document.getElementById('take-attendance-cancel')?.addEventListener('click', closeTakeAttendanceModal);
    document.getElementById('take-attendance-modal')?.addEventListener('click', (event) => {
        if (event.target === event.currentTarget) {
            closeTakeAttendanceModal();
        }
    });
    document.getElementById('take-attendance-search')?.addEventListener('input', () => {
        attendanceModalSearchQuery = document.getElementById('take-attendance-search')?.value.trim() || '';
        renderTakeAttendanceModalList();
    });

    // Edit pantry modal - save
    document.getElementById('save-edit-pantry-btn').addEventListener('click', async (event) => {
        const pantryId = parseInt(document.getElementById('edit-pantry-id').value);
        const name = document.getElementById('edit-pantry-name').value.trim();
        const location_address = document.getElementById('edit-pantry-address').value.trim();

        if (!name || !location_address) {
            showMessage('edit-pantry', 'Both fields are required.', 'error');
            return;
        }

        await withButtonLock(event.currentTarget, async () => {
            try {
                await updatePantry(pantryId, { name, location_address });
                document.getElementById('edit-pantry-modal').classList.add('app-hidden');
                showMessage('pantry', 'Pantry updated successfully!', 'success');
                await loadPantries();
            } catch (error) {
                showMessage('edit-pantry', `Error: ${error.message}`, 'error');
            }
        });
    });

    // Pantry selection
    document.getElementById('pantry-select').addEventListener('change', async (e) => {
        currentPantryId = parseInt(e.target.value);
        selectedManagedShiftId = null;
        managedShiftPanelMode = 'create';
        setManageShiftsMobileView('queue');
        resetEditShiftForm();
        await loadCalendarShifts();
        if (currentUserIsAdminCapable() || currentUserHasRole('PANTRY_LEAD')) {
            await loadShiftsTable();
        }
    });

    // Create pantry form
    document.getElementById('create-pantry-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const formData = new FormData(e.target);
        const data = {
            name: formData.get('name'),
            location_address: formData.get('location_address')
        };

        await withButtonLock(getSubmitButtonFromEvent(e), async () => {
            try {
                await createPantry(data);
                showMessage('pantry', 'Pantry created successfully!', 'success');
                e.target.reset();
                await loadPantries();
            } catch (error) {
                showMessage('pantry', `Error: ${error.message}`, 'error');
            }
        });
    });

    // Assign lead
    document.getElementById('assign-lead-btn')?.addEventListener('click', async (event) => {
        const pantryId = parseInt(document.getElementById('assign-pantry').value);
        const leadId = parseInt(document.getElementById('assign-lead').value);

        if (!pantryId || !leadId) {
            showMessage('assign', 'Please select both pantry and lead', 'error');
            return;
        }

        await withButtonLock(event.currentTarget, async () => {
            try {
                await addPantryLead(pantryId, leadId);
                showMessage('assign', 'Lead assigned successfully!', 'success');
                clearSelectedAssignPantry(false);
                clearSelectedPantryLead(false);
                await loadPantries();
            } catch (error) {
                showMessage('assign', `Error: ${error.message}`, 'error');
            }
        });
    });

    // Remove lead
    document.getElementById('remove-lead-btn')?.addEventListener('click', async (event) => {
        const pantryId = parseInt(document.getElementById('assign-pantry').value);
        const leadId = parseInt(document.getElementById('assign-lead').value);

        if (!pantryId || !leadId) {
            showMessage('assign', 'Please select both pantry and lead', 'error');
            return;
        }

        if (!confirm('Remove this lead from the pantry?')) return;

        await withButtonLock(event.currentTarget, async () => {
            try {
                await removePantryLead(pantryId, leadId);
                showMessage('assign', 'Lead removed successfully!', 'success');
                clearSelectedAssignPantry(false);
                clearSelectedPantryLead(false);
                await loadPantries();
            } catch (error) {
                showMessage('assign', `Error: ${error.message}`, 'error');
            }
        });
    });

    // Add role button
    document.getElementById('add-role-btn').addEventListener('click', () => {
        const container = document.getElementById('roles-container');
        const roleGroup = document.createElement('div');
        roleGroup.className = 'role-input-group';
        roleGroup.innerHTML = `
                    <div class="form-grid">
                        <div class="form-group">
                            <label>Role Title *</label>
                            <input type="text" class="role-title" placeholder="e.g., Food Sorter" required>
                        </div>
                        <div class="form-group">
                            <label>Required Count *</label>
                            <input type="number" class="role-count" min="1" value="1" required>
                        </div>
                        <div class="form-group role-input-actions">
                            <label>Action</label>
                            <button type="button" class="btn btn-danger" onclick="this.closest('.role-input-group').remove()">Remove</button>
                        </div>
                    </div>
                `;
        container.appendChild(roleGroup);
    });

    document.getElementById('shift-repeat-toggle')?.addEventListener('change', toggleCreateRecurrenceFields);
    document.getElementById('shift-start')?.addEventListener('change', () => {
        if (document.getElementById('shift-repeat-toggle')?.checked) {
            toggleCreateRecurrenceFields();
        }
    });

    document.querySelectorAll('#shift-repeat-weekdays [data-weekday], #edit-shift-repeat-weekdays [data-weekday]').forEach((button) => {
        button.addEventListener('click', () => {
            button.classList.toggle('active');
        });
    });

    document.querySelectorAll('input[name="shift-repeat-end-mode"]').forEach((input) => {
        input.addEventListener('change', () => {
            setRecurrenceEndMode('shift', input.value);
        });
    });

    document.querySelectorAll('input[name="edit-shift-repeat-end-mode"]').forEach((input) => {
        input.addEventListener('change', () => {
            setRecurrenceEndMode('edit-shift', input.value);
        });
    });

    document.getElementById('cancel-edit-shift-btn').addEventListener('click', () => {
        resetEditShiftForm();
        renderManageShiftsTable();
        if (selectedManagedShiftId) {
            loadSelectedShiftRegistrations(selectedManagedShiftId);
        }
    });

    document.getElementById('add-edit-role-btn').addEventListener('click', () => {
        const container = document.getElementById('edit-roles-container');
        container.appendChild(buildEditRoleRow(null));
    });

    document.getElementById('edit-shift-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        if (!editingShiftSnapshot) {
            showMessage('shifts', 'No shift selected for editing', 'error');
            return;
        }

        const shiftId = parseInt(document.getElementById('edit-shift-id').value, 10);
        if (!shiftId) {
            showMessage('shifts', 'Invalid shift selected', 'error');
            return;
        }

        const updatedShiftPayload = {
            shift_name: document.getElementById('edit-shift-name').value.trim(),
            start_time: new Date(document.getElementById('edit-shift-start').value).toISOString(),
            end_time: new Date(document.getElementById('edit-shift-end').value).toISOString(),
            status: String(editingShiftSnapshot.status || 'OPEN').toUpperCase()
        };

        if (!updatedShiftPayload.shift_name || Number.isNaN(new Date(updatedShiftPayload.start_time).getTime()) || Number.isNaN(new Date(updatedShiftPayload.end_time).getTime())) {
            showMessage('shifts', 'Please provide valid shift name and time range', 'error');
            return;
        }

        const roleRows = Array.from(document.querySelectorAll('#edit-roles-container .role-input-group'));
        if (roleRows.length === 0) {
            showMessage('shifts', 'Shift must include at least one role', 'error');
            return;
        }

        const roleInputs = roleRows.map((row) => {
            const roleIdRaw = row.dataset.roleId || '';
            const roleTitle = row.querySelector('.edit-role-title')?.value.trim() || '';
            const requiredCount = parseInt(row.querySelector('.edit-role-count')?.value || '0', 10);
            return {
                shift_role_id: roleIdRaw ? parseInt(roleIdRaw, 10) : null,
                role_title: roleTitle,
                required_count: requiredCount
            };
        });

        const invalidRole = roleInputs.find((role) => !role.role_title || Number.isNaN(role.required_count) || role.required_count < 1);
        if (invalidRole) {
            showMessage('shifts', 'Each role requires a title and required count >= 1', 'error');
            return;
        }

        let applyScope = 'single';
        let recurrencePayload = null;
        if (editingShiftSnapshot.is_recurring) {
            const choice = await promptRecurringScope('edit');
            if (!choice || choice === 'cancel') {
                return;
            }
            applyScope = choice;
            if (applyScope === 'future') {
                recurrencePayload = buildRecurrencePayloadFromForm('edit-shift', 'edit-shift-start');
            }
        }

        await withButtonLock(getSubmitButtonFromEvent(e), async () => {
            try {
                const response = await updateFullShift(shiftId, {
                    ...updatedShiftPayload,
                    apply_scope: applyScope,
                    ...(recurrencePayload ? { recurrence: recurrencePayload } : {}),
                    roles: roleInputs.map(role => ({
                        ...(role.shift_role_id ? { shift_role_id: role.shift_role_id } : {}),
                        role_title: role.role_title,
                        required_count: role.required_count
                    }))
                });

                const impacted = collectAffectedContacts([response]);
                const recurringSummary = response.apply_scope === 'future'
                    ? ` Updated ${Number(response.updated_occurrence_count || 0)} occurrence(s), created ${Number(response.created_occurrence_count || 0)}, cancelled ${Number(response.cancelled_occurrence_count || 0)}.`
                    : '';
                const impactedMsg = impacted.uniqueVolunteers > 0
                    ? ` ${impacted.uniqueVolunteers} volunteer(s) need reconfirmation.`
                    : '';
                showMessage('shifts', `Shift updated successfully.${recurringSummary}${impactedMsg}`, 'success');

                resetEditShiftForm();
                await loadShiftsTable();
                await loadCalendarShifts();
                const myShiftsTab = document.getElementById('content-my-shifts');
                if (myShiftsTab && myShiftsTab.classList.contains('active')) {
                    await loadMyRegisteredShifts();
                }
            } catch (error) {
                showMessage('shifts', `Update failed: ${error.message}`, 'error');
            }
        });
    });

    // Create shift form
    document.getElementById('create-shift-form').addEventListener('submit', async (e) => {
        e.preventDefault();

        if (!currentPantryId) {
            showMessage('shifts', 'Please select a pantry first', 'error');
            return;
        }

        const formData = new FormData(e.target);
        const shiftData = {
            shift_name: formData.get('shift_name'),
            start_time: new Date(formData.get('start_time')).toISOString(),
            end_time: new Date(formData.get('end_time')).toISOString()
        };

        // Collect roles
        const roleTitles = document.querySelectorAll('.role-title');
        const roleCounts = document.querySelectorAll('.role-count');
        const roles = [];

        for (let i = 0; i < roleTitles.length; i++) {
            const title = roleTitles[i].value.trim();
            const count = parseInt(roleCounts[i].value);
            if (title && count > 0) {
                roles.push({ role_title: title, required_count: count });
            }
        }

        if (roles.length === 0) {
            showMessage('shifts', 'Please add at least one role', 'error');
            return;
        }

        const recurrence = buildRecurrencePayloadFromForm('shift', 'shift-start');

        await withButtonLock(getSubmitButtonFromEvent(e), async () => {
            try {
                const response = await createFullShift(currentPantryId, {
                    ...shiftData,
                    roles,
                    ...(recurrence ? { recurrence } : {})
                });

                const createdCount = Number(response.created_shift_count || 1);
                const recurringText = response.shift_series_id
                    ? ` Created ${createdCount} recurring shift occurrence(s).`
                    : '';
                showMessage('shifts', `Shift created successfully with all roles!${recurringText}`, 'success');
                e.target.reset();
                resetCreateRecurrenceForm();

                // Reset roles container to single role
                document.getElementById('roles-container').innerHTML = `
                        <div class="role-input-group">
                            <div class="form-grid">
                                <div class="form-group">
                                    <label>Role Title *</label>
                                    <input type="text" class="role-title" placeholder="e.g., Greeter" required>
                                </div>
                                <div class="form-group">
                                    <label>Required Count *</label>
                                    <input type="number" class="role-count" min="1" value="1" required>
                                </div>
                            </div>
                        </div>
                    `;

                await loadShiftsTable();
                await loadCalendarShifts();
            } catch (error) {
                showMessage('shifts', `Error: ${error.message}`, 'error');
            }
        });
    });
}

// Show message helper
function showMessage(target, text, type = 'info') {
    const modal = document.getElementById('notification-modal');
    const box = document.getElementById('notification-modal-box');
    const textEl = document.getElementById('notification-modal-text');
    const iconEl = document.getElementById('notification-modal-icon');
    if (!modal || !textEl) return;

    const styles = {
        success: { icon: '✓', color: '#22543d', bg: '#c6f6d5', border: '#48bb78' },
        error:   { icon: '✕', color: '#742a2a', bg: '#fed7d7', border: '#f56565' },
        info:    { icon: 'ℹ', color: '#2c5282', bg: '#bee3f8', border: '#4299e1' },
    };
    const s = styles[type] || styles.info;

    box.style.borderTop = `4px solid ${s.border}`;
    box.style.background = s.bg;
    iconEl.textContent = s.icon;
    iconEl.style.color = s.border;
    textEl.innerHTML = text;
    textEl.style.color = s.color;

    modal.classList.remove('app-hidden');
}

// Make functions globally available
window.signupForRole = signupForRole;
window.cancelShiftConfirm = cancelShiftConfirm;
window.revokeShiftConfirm = revokeShiftConfirm;
window.openEditShift = openEditShift;
window.selectManagedShift = selectManagedShift;
window.showCreateShiftPanel = showCreateShiftPanel;
window.backToManagedShiftQueue = backToManagedShiftQueue;
window.openHelpBroadcastModal = openHelpBroadcastModal;
window.openTakeAttendanceModal = openTakeAttendanceModal;
window.addHelpBroadcastRecipientById = addHelpBroadcastRecipientById;
window.removeHelpBroadcastRecipient = removeHelpBroadcastRecipient;
window.toggleShiftRegistrations = toggleShiftRegistrations;
window.cancelMySignup = cancelMySignup;
window.reconfirmMySignup = reconfirmMySignup;
window.markSignupAttendance = markSignupAttendance;
window.initializeDashboardApp = initializeDashboardApp;
