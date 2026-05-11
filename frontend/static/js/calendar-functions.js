const CALENDAR_WEEKDAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const CALENDAR_WEEKDAY_LONG_LABELS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const CALENDAR_COLOR_PALETTE = [
    { solid: '#2563eb', soft: '#dbeafe', text: '#1d4ed8' },
    { solid: '#16a34a', soft: '#dcfce7', text: '#15803d' },
    { solid: '#9333ea', soft: '#f3e8ff', text: '#7e22ce' },
    { solid: '#ea580c', soft: '#ffedd5', text: '#c2410c' },
    { solid: '#0891b2', soft: '#cffafe', text: '#0e7490' },
    { solid: '#dc2626', soft: '#fee2e2', text: '#b91c1c' },
    { solid: '#ca8a04', soft: '#fef9c3', text: '#a16207' },
    { solid: '#4f46e5', soft: '#e0e7ff', text: '#4338ca' }
];
const CALENDAR_NEUTRAL_PALETTE = {
    solid: '#94a3b8',
    soft: '#f1f5f9',
    text: '#475569'
};

const calendarControllers = new Map();
let calendarResizeHandlerBound = false;

function createDefaultCalendarState() {
    return {
        initialized: false,
        view: isPhoneViewport() ? 'week' : 'month',
        hasUserChangedView: false,
        selectedDate: startOfCalendarDay(new Date()),
        miniDate: startOfCalendarMonth(new Date()),
        sourceItems: [],
        events: [],
        filteredEvents: [],
        filters: {
            pantryId: 'all',
            search: '',
            timeBucket: 'all'
        },
        activeEventId: null,
        loadingKey: '',
        lastRangeKey: '',
        lastViewportIsPhone: isPhoneViewport(),
        hasLoaded: false
    };
}

function initializeCalendarUi() {
    ensureCalendarControllersRegistered();
    calendarControllers.forEach((controller) => controller.initialize());
}

function ensureCalendarControllersRegistered() {
    registerCalendarController('available', buildAvailableCalendarConfig());
    registerCalendarController('my-shifts', buildMyShiftsCalendarConfig());

    if (!calendarResizeHandlerBound) {
        calendarResizeHandlerBound = true;
        window.addEventListener('resize', () => {
            calendarControllers.forEach((controller) => controller.handleViewportResize());
        });
    }
}

function registerCalendarController(key, config) {
    const root = document.querySelector(`[data-calendar-root="${key}"]`);
    if (!root) {
        return null;
    }

    const modal = document.querySelector(`[data-calendar-modal="${key}"]`);
    const existing = calendarControllers.get(key);
    if (existing) {
        existing.root = root;
        existing.modal = modal;
        existing.config = config;
        return existing;
    }

    const controller = createCalendarController(key, root, modal, config);
    calendarControllers.set(key, controller);
    return controller;
}

function getCalendarController(key) {
    ensureCalendarControllersRegistered();
    return calendarControllers.get(key) || null;
}

function createCalendarController(key, root, modal, config) {
    const controller = {
        key,
        root,
        modal,
        config,
        state: createDefaultCalendarState(),

        initialize() {
            if (this.state.initialized) {
                this.syncPantryOptions();
                this.renderMiniPicker();
                this.renderActiveModal();
                return;
            }

            this.state.initialized = true;
            this.renderMiniWeekdays();
            this.bindEvents();
            this.syncPantryOptions();
            this.renderMiniPicker();
            this.updateToolbarState();
            this.updateFilterSummary();
            this.renderActiveModal();
        },

        bindEvents() {
            this.part('sidebar-toggle')?.addEventListener('click', () => this.openSidebar());
            this.part('sidebar-close')?.addEventListener('click', () => this.closeSidebar());
            this.part('sidebar-backdrop')?.addEventListener('click', () => this.closeSidebar());

            this.part('today-btn')?.addEventListener('click', async (event) => {
                this.state.selectedDate = startOfCalendarDay(new Date());
                this.state.miniDate = startOfCalendarMonth(this.state.selectedDate);
                await withButtonLock(event.currentTarget, () => this.load(true));
            });

            this.part('prev-btn')?.addEventListener('click', async (event) => {
                shiftCalendarAnchorForController(this, -1);
                await withButtonLock(event.currentTarget, () => this.load(true));
            });

            this.part('next-btn')?.addEventListener('click', async (event) => {
                shiftCalendarAnchorForController(this, 1);
                await withButtonLock(event.currentTarget, () => this.load(true));
            });

            this.part('mini-prev')?.addEventListener('click', () => {
                this.state.miniDate = startOfCalendarMonth(addMonths(this.state.miniDate, -1));
                this.renderMiniPicker();
            });

            this.part('mini-next')?.addEventListener('click', () => {
                this.state.miniDate = startOfCalendarMonth(addMonths(this.state.miniDate, 1));
                this.renderMiniPicker();
            });

            this.parts('view-button').forEach((button) => {
                button.addEventListener('click', async () => {
                    const nextView = String(button.dataset.calendarView || 'month');
                    if (!['month', 'week', 'day'].includes(nextView)) {
                        return;
                    }
                    this.state.view = nextView;
                    this.state.hasUserChangedView = true;
                    await withButtonLock(button, () => this.load(true));
                });
            });

            this.part('search-input')?.addEventListener('input', () => {
                this.state.filters.search = this.part('search-input')?.value.trim() || '';
                this.render();
            });

            this.part('pantry-filter')?.addEventListener('change', () => {
                this.state.filters.pantryId = this.part('pantry-filter')?.value || 'all';
                this.render();
            });

            this.part('time-filter')?.addEventListener('change', () => {
                this.state.filters.timeBucket = this.part('time-filter')?.value || 'all';
                this.render();
            });

            this.part('clear-filters')?.addEventListener('click', () => {
                this.resetFilters();
                this.render();
            });

            this.part('container')?.addEventListener('click', async (event) => {
                const target = event.target instanceof HTMLElement
                    ? event.target.closest('[data-calendar-event-id], [data-calendar-more-day]')
                    : null;
                if (!(target instanceof HTMLElement)) {
                    return;
                }

                if (target.dataset.calendarMoreDay) {
                    this.state.selectedDate = parseCalendarDateKey(target.dataset.calendarMoreDay) || this.state.selectedDate;
                    this.state.view = 'day';
                    this.state.hasUserChangedView = true;
                    await withButtonLock(target, () => this.load(true));
                    return;
                }

                if (target.dataset.calendarEventId) {
                    this.openEventModal(parseInt(target.dataset.calendarEventId, 10));
                }
            });

            this.modalPart('close')?.addEventListener('click', () => this.closeModal());
            this.modal?.addEventListener('click', (event) => {
                if (event.target === event.currentTarget) {
                    this.closeModal();
                }
            });
            this.modalPart('body')?.addEventListener('click', async (event) => {
                const target = event.target instanceof HTMLElement
                    ? event.target.closest('[data-calendar-action]')
                    : null;
                if (!(target instanceof HTMLElement) || typeof this.config.handleAction !== 'function') {
                    return;
                }

                const actionSucceeded = await this.config.handleAction(this, target);

                if (actionSucceeded) {
                    this.closeModal();
                }
            });
        },

        part(name) {
            return this.root?.querySelector(`[data-calendar-part="${name}"]`) || null;
        },

        parts(name) {
            return Array.from(this.root?.querySelectorAll(`[data-calendar-part="${name}"]`) || []);
        },

        modalPart(name) {
            return this.modal?.querySelector(`[data-calendar-modal-part="${name}"]`) || null;
        },

        resetFilters() {
            this.state.filters = { pantryId: 'all', search: '', timeBucket: 'all' };
            const searchInput = this.part('search-input');
            const pantrySelect = this.part('pantry-filter');
            const timeSelect = this.part('time-filter');
            if (searchInput) searchInput.value = '';
            if (pantrySelect) pantrySelect.value = 'all';
            if (timeSelect) timeSelect.value = 'all';
        },

        openSidebar() {
            this.part('sidebar')?.classList.add('open');
            this.part('sidebar-backdrop')?.classList.remove('app-hidden');
        },

        closeSidebar() {
            this.part('sidebar')?.classList.remove('open');
            this.part('sidebar-backdrop')?.classList.add('app-hidden');
        },

        handleViewportResize() {
            const nextIsPhone = isPhoneViewport();
            if (nextIsPhone !== this.state.lastViewportIsPhone && !this.state.hasUserChangedView) {
                this.state.view = nextIsPhone ? 'week' : 'month';
            }
            this.state.lastViewportIsPhone = nextIsPhone;
            if (!nextIsPhone) {
                this.closeSidebar();
            }
            this.render();
        },

        syncPantryOptions() {
            const select = this.part('pantry-filter');
            if (!select) {
                return;
            }

            const pantryList = this.getPantryList();
            const previousValue = this.state.filters.pantryId || 'all';
            const options = [
                '<option value="all">All pantries</option>',
                ...pantryList.map((pantry) => `<option value="${pantry.pantry_id}">${escapeHtml(pantry.name || `Pantry ${pantry.pantry_id}`)}</option>`)
            ];
            select.innerHTML = options.join('');

            const hasPreviousValue = previousValue === 'all'
                || pantryList.some((pantry) => String(pantry.pantry_id) === String(previousValue));
            this.state.filters.pantryId = hasPreviousValue ? previousValue : 'all';
            select.value = this.state.filters.pantryId;
            this.renderLegend();
        },

        getPantryList() {
            return typeof this.config.getPantries === 'function'
                ? normalizeCalendarPantryList(this.config.getPantries(this))
                : [];
        },

        renderMiniWeekdays() {
            const container = this.part('mini-weekdays');
            if (!container) {
                return;
            }
            container.innerHTML = CALENDAR_WEEKDAY_LABELS.map((label) => `<span>${label.slice(0, 2)}</span>`).join('');
        },

        renderMiniPicker() {
            const label = this.part('mini-label');
            const grid = this.part('mini-grid');
            if (!label || !grid) {
                return;
            }

            label.textContent = formatCalendarDateLabel(this.state.miniDate, { month: 'long', year: 'numeric' });
            const monthStart = startOfCalendarMonth(this.state.miniDate);
            const visibleStart = startOfCalendarWeek(monthStart);
            const cells = [];
            for (let index = 0; index < 42; index += 1) {
                const cellDate = addDays(visibleStart, index);
                const isCurrentMonth = cellDate.getMonth() === monthStart.getMonth();
                const isToday = isSameCalendarDay(cellDate, new Date());
                const isSelected = isSameCalendarDay(cellDate, this.state.selectedDate);
                cells.push(`
                    <button
                        type="button"
                        class="calendar-mini-day${isCurrentMonth ? '' : ' is-outside'}${isToday ? ' is-today' : ''}${isSelected ? ' is-selected' : ''}"
                        data-calendar-mini-date="${getCalendarDateKey(cellDate)}"
                    >${cellDate.getDate()}</button>
                `);
            }
            grid.innerHTML = cells.join('');
            grid.querySelectorAll('[data-calendar-mini-date]').forEach((button) => {
                button.addEventListener('click', async () => {
                    const date = parseCalendarDateKey(button.dataset.calendarMiniDate);
                    if (!date) {
                        return;
                    }
                    this.state.selectedDate = date;
                    this.state.miniDate = startOfCalendarMonth(date);
                    await withButtonLock(button, () => this.load(true));
                    if (isPhoneViewport()) {
                        this.closeSidebar();
                    }
                });
            });
        },

        renderLegend() {
            const container = this.part('legend');
            if (!container) {
                return;
            }

            const pantries = this.getPantryList();
            container.innerHTML = pantries.length > 0
                ? pantries.map((pantry) => {
                    const palette = getCalendarPantryPalette(pantry.pantry_id);
                    return `
                        <div class="calendar-legend-item">
                            <span class="calendar-legend-swatch" style="background:${palette.solid}"></span>
                            <span>${escapeHtml(pantry.name || `Pantry ${pantry.pantry_id}`)}</span>
                        </div>
                    `;
                }).join('')
                : '<p class="empty-state empty-state-compact">No pantries available.</p>';
        },

        showLoading(message) {
            const container = this.part('container');
            if (!container) {
                return;
            }
            container.classList.add('loading');
            container.innerHTML = `<div class="loading"><div class="spinner"></div><p>${escapeHtml(message)}</p></div>`;
        },

        showError(title, message) {
            const container = this.part('container');
            if (!container) {
                return;
            }
            container.classList.remove('loading');
            container.innerHTML = `<div class="error-state-card"><h3>${escapeHtml(title)}</h3><p><strong>${escapeHtml(message || 'Unknown error')}</strong></p></div>`;
        },

        async setSourceItems(items, forceReload = true) {
            this.state.sourceItems = Array.isArray(items) ? items : [];
            this.state.lastRangeKey = '';
            await this.load(forceReload);
        },

        async load(forceReload = true) {
            this.initialize();
            if (!this.state.hasUserChangedView && isPhoneViewport()) {
                this.state.view = 'week';
            }

            const visibleRange = getCalendarVisibleRangeForController(this);
            const rangeKey = `${visibleRange.start.toISOString()}|${visibleRange.end.toISOString()}|${this.state.view}`;
            this.state.miniDate = startOfCalendarMonth(this.state.selectedDate);
            this.updateToolbarState();
            this.renderMiniPicker();

            if (!forceReload && this.state.lastRangeKey === rangeKey && this.state.hasLoaded) {
                this.render();
                return;
            }

            this.state.loadingKey = rangeKey;
            this.state.lastRangeKey = rangeKey;
            this.showLoading(this.config.loadingText || 'Loading shifts for this range...');

            try {
                const rawItems = await this.config.loadEvents({
                    start: visibleRange.start,
                    end: visibleRange.end,
                    controller: this
                });
                if (this.state.loadingKey !== rangeKey) {
                    return;
                }

                this.state.sourceItems = Array.isArray(rawItems) ? rawItems : [];
                this.state.events = normalizeCalendarEvents(this, this.state.sourceItems);
                this.state.hasLoaded = true;
                this.syncPantryOptions();
                this.render();
            } catch (error) {
                if (this.state.loadingKey !== rangeKey) {
                    return;
                }

                this.showError(this.config.errorTitle || 'Failed to load calendar', error.message || 'Unknown error');
            }
        },

        updateToolbarState() {
            this.parts('view-button').forEach((button) => {
                button.classList.toggle('active', button.dataset.calendarView === this.state.view);
            });

            const label = this.part('range-label');
            if (label) {
                label.textContent = getCalendarRangeLabel(this);
            }
        },

        updateFilterSummary() {
            const summary = this.part('filter-summary');
            if (!summary) {
                return;
            }

            const chips = [];
            if (this.state.filters.pantryId !== 'all') {
                chips.push(`Pantry: ${escapeHtml(getCalendarPantryNameById(this, Number(this.state.filters.pantryId)) || 'Selected pantry')}`);
            }
            if (this.state.filters.search) {
                chips.push(`Search: ${escapeHtml(this.state.filters.search)}`);
            }
            if (this.state.filters.timeBucket !== 'all') {
                chips.push(`Time: ${escapeHtml(capitalizeCalendarLabel(this.state.filters.timeBucket))}`);
            }

            const hintText = typeof this.config.filterHintText === 'function'
                ? this.config.filterHintText(this)
                : (this.config.filterHintText || 'Showing all shifts in the selected range.');

            summary.innerHTML = chips.length > 0
                ? chips.map((chip) => `<span class="calendar-filter-chip">${chip}</span>`).join('')
                : `<span class="calendar-filter-hint">${escapeHtml(hintText)}</span>`;
        },

        render() {
            const container = this.part('container');
            if (!container) {
                return;
            }

            this.updateToolbarState();
            this.updateFilterSummary();
            this.state.filteredEvents = filterCalendarEvents(this, this.state.events);
            this.renderActiveModal();

            container.classList.remove('loading');
            if (isPhoneViewport()) {
                renderPhoneCalendarAgenda(this, container, this.state.filteredEvents);
                return;
            }

            if (this.state.view === 'week') {
                renderDesktopWeekCalendar(this, container, this.state.filteredEvents);
                return;
            }
            if (this.state.view === 'day') {
                renderDesktopDayCalendar(this, container, this.state.filteredEvents);
                return;
            }
            renderDesktopMonthCalendar(this, container, this.state.filteredEvents);
        },

        openEventModal(eventId) {
            this.state.activeEventId = eventId;
            this.renderActiveModal();
            this.modal?.classList.remove('app-hidden');
        },

        closeModal() {
            this.state.activeEventId = null;
            this.modal?.classList.add('app-hidden');
        },

        renderActiveModal() {
            const modalBody = this.modalPart('body');
            if (!this.modal || !modalBody) {
                return;
            }

            if (!this.state.activeEventId) {
                this.modal.classList.add('app-hidden');
                modalBody.innerHTML = '';
                return;
            }

            const event = this.state.events.find((item) => intValue(item.id) === intValue(this.state.activeEventId));
            if (!event) {
                this.closeModal();
                return;
            }

            modalBody.innerHTML = typeof this.config.renderModalBody === 'function'
                ? this.config.renderModalBody(this, event)
                : '';
        }
    };

    return controller;
}

function buildAvailableCalendarConfig() {
    return {
        loadingText: 'Loading shifts for this range...',
        errorTitle: 'Failed to load calendar',
        filterHintText: 'Showing all available shifts in the selected range.',
        noEventsText: 'No available shifts in this range.',
        noMatchesText: 'No available shifts match the selected range and filters.',
        getPantries: () => getCalendarPantryList(),
        loadEvents: async ({ start, end }) => {
            const params = new URLSearchParams({
                start: start.toISOString(),
                end: end.toISOString()
            });
            return apiGet(`/api/calendar/shifts?${params.toString()}`);
        },
        normalizeEvents: normalizeAvailableCalendarEvents,
        getDayCountText: (count) => `${count} shift${count === 1 ? '' : 's'} available`,
        getEventBadgeText: (event) => event.isPast ? 'Past' : '',
        getEventMetaLines: (event, view) => {
            if (view === 'week') {
                return [event.pantry_name];
            }
            if (view === 'phone') {
                return [renderCalendarRoleSummary(event.roles || [])];
            }
            if (view === 'day') {
                return [
                    `${event.pantry_name}${event.location ? ` • ${event.location}` : ''}`,
                    renderCalendarRoleSummary(event.roles || [])
                ];
            }
            return [];
        },
        renderModalBody: (_controller, event) => {
            const palette = getCalendarEventPalette(event);
            return `
                <div class="calendar-modal-header" style="border-top-color:${palette.solid}">
                    <span class="calendar-modal-pantry-badge" style="background:${palette.soft}; color:${palette.text};">${escapeHtml(event.pantry_name)}</span>
                    <h2 class="calendar-modal-title">${escapeHtml(event.title)}</h2>
                    <p class="calendar-modal-time">${escapeHtml(formatLocalTimeRange(event.startDate, event.endDate))}</p>
                    ${getCalendarSpanIndicator(event) ? `<p class="calendar-modal-span">${escapeHtml(getCalendarSpanIndicator(event))}</p>` : ''}
                    <p class="calendar-modal-location">${escapeHtml(event.location || 'Location unavailable')}</p>
                </div>
                <div class="calendar-modal-section">
                    <h3>Roles</h3>
                    <div class="calendar-modal-role-list">
                        ${(event.roles || []).map((role) => renderAvailableCalendarModalRole(role, event)).join('')}
                    </div>
                </div>
            `;
        },
        handleAction: async (_controller, target) => {
            if (target.dataset.calendarAction !== 'signup-role') {
                return false;
            }
            const roleId = parseInt(target.dataset.roleId || '0', 10);
            if (!roleId) {
                return false;
            }
            return signupForRole(roleId, target);
        }
    };
}

function buildMyShiftsCalendarConfig() {
    return {
        loadingText: 'Loading your registered shifts...',
        errorTitle: 'Failed to load registered shifts',
        filterHintText: 'Showing all registered shifts in the selected range.',
        noEventsText: 'You have no registered shifts yet.',
        noMatchesText: 'No registered shifts match the selected range and filters.',
        getPantries: (controller) => getCalendarPantriesFromEvents(controller.state.events),
        loadEvents: async ({ controller }) => controller.state.sourceItems,
        normalizeEvents: normalizeMyShiftCalendarEvents,
        getDayCountText: (count) => `${count} registered shift${count === 1 ? '' : 's'}`,
        getMonthSubtitle: (event) => event.role_title || '',
        getEventBadgeText: (event) => getMyShiftCalendarBadgeText(event),
        getEventMetaLines: (event, view) => {
            const statusLine = `Signup: ${formatCalendarStatusLabel(event.signup_status)} • Shift: ${formatCalendarStatusLabel(event.shift_status)}`;
            if (view === 'week') {
                return [event.role_title || 'Unassigned role', statusLine];
            }
            if (view === 'phone') {
                return [
                    `Role: ${event.role_title || 'Unassigned role'}`,
                    statusLine
                ];
            }
            if (view === 'day') {
                return [
                    `${event.pantry_name}${event.location ? ` • ${event.location}` : ''}`,
                    `Role: ${event.role_title || 'Unassigned role'}`,
                    statusLine
                ];
            }
            return [];
        },
        renderModalBody: (_controller, event) => {
            const palette = getCalendarEventPalette(event);
            const attendanceInfo = typeof getAttendanceInfo === 'function'
                ? getAttendanceInfo(event.signup_status)
                : { label: 'Pending Attendance', className: 'attendance-badge-pending', isMarked: false };
            const showSignupBadge = !attendanceInfo.isMarked;
            return `
                <div class="calendar-modal-header" style="border-top-color:${palette.solid}">
                    <span class="calendar-modal-pantry-badge" style="background:${palette.soft}; color:${palette.text};">${escapeHtml(event.pantry_name)}</span>
                    <h2 class="calendar-modal-title">${escapeHtml(event.title)}</h2>
                    <p class="calendar-modal-time">${escapeHtml(formatLocalTimeRange(event.startDate, event.endDate))}</p>
                    ${getCalendarSpanIndicator(event) ? `<p class="calendar-modal-span">${escapeHtml(getCalendarSpanIndicator(event))}</p>` : ''}
                    <p class="calendar-modal-location">${escapeHtml(event.location || 'Location unavailable')}</p>
                    <div class="calendar-modal-status-row">
                        <span class="status-badge attendance-badge ${attendanceInfo.className}">${escapeHtml(attendanceInfo.label)}</span>
                        ${showSignupBadge
                            ? `<span class="status-badge ${toStatusClass('signup-status', event.signup_status)}">${escapeHtml(formatCalendarStatusLabel(event.signup_status))}</span>`
                            : ''}
                        <span class="status-badge ${toStatusClass('shift-status', event.shift_status)}">${escapeHtml(formatCalendarStatusLabel(event.shift_status))}</span>
                        ${event.isPast ? '<span class="status-badge calendar-status-badge-past">Past Shift</span>' : ''}
                    </div>
                </div>
                <div class="calendar-modal-section">
                    <h3>Registration Details</h3>
                    <div class="calendar-modal-role-list">
                        <div class="calendar-modal-role-item">
                            <div class="calendar-modal-role-info">
                                <div class="calendar-modal-role-title">${escapeHtml(event.role_title || 'Unassigned Role')}</div>
                                <div class="calendar-modal-role-meta">${escapeHtml(event.pantry_name)}</div>
                                ${event.reconfirm_reason ? `<div class="calendar-modal-role-meta">${escapeHtml(formatCalendarStatusLabel(event.reconfirm_reason))}</div>` : ''}
                            </div>
                        </div>
                    </div>
                    ${renderMyShiftCalendarModalActions(event)}
                </div>
            `;
        },
        handleAction: async (_controller, target) => {
            const action = target.dataset.calendarAction || '';
            const signupId = parseInt(target.dataset.signupId || '0', 10);
            if (!signupId) {
                return false;
            }

            if (action === 'cancel-signup') {
                return cancelMySignup(signupId, target);
            }
            if (action === 'confirm-signup') {
                return reconfirmMySignup(signupId, 'CONFIRM', target);
            }
            if (action === 'cancel-reconfirm-signup') {
                return reconfirmMySignup(signupId, 'CANCEL', target);
            }
            return false;
        }
    };
}

function normalizeAvailableCalendarEvents(items) {
    if (!Array.isArray(items)) {
        return [];
    }

    return items
        .map((shift) => {
            const startDate = safeDateValue(shift.start_time);
            const endDate = safeDateValue(shift.end_time);
            if (!startDate || !endDate) {
                return null;
            }

            const pantry = shift.pantry || {};
            const pantryId = Number(pantry.pantry_id || shift.pantry_id || 0);
            const pantryName = pantry.name || 'Pantry';
            const location = pantry.location_address || '';
            const roleTitles = Array.isArray(shift.roles)
                ? shift.roles.map((role) => role.role_title || '').filter(Boolean)
                : [];
            const isPast = endDate < new Date();

            return {
                ...shift,
                id: intValue(shift.shift_id),
                title: shift.shift_name || 'Untitled Shift',
                pantry: {
                    pantry_id: pantryId,
                    name: pantryName,
                    location_address: location
                },
                pantry_id: pantryId,
                pantry_name: pantryName,
                location,
                startDate,
                endDate,
                searchBlob: [
                    shift.shift_name,
                    pantryName,
                    location,
                    roleTitles.join(' ')
                ].filter(Boolean).join(' ').toLowerCase(),
                isPast
            };
        })
        .filter(Boolean)
        .sort((left, right) => left.startDate.getTime() - right.startDate.getTime());
}

function normalizeMyShiftCalendarEvents(items) {
    if (!Array.isArray(items)) {
        return [];
    }

    return items
        .map((signup) => {
            const startDate = safeDateValue(signup.start_time);
            const endDate = safeDateValue(signup.end_time);
            if (!startDate || !endDate) {
                return null;
            }

            const bucket = classifyShiftBucket(signup, new Date());
            return {
                ...signup,
                id: intValue(signup.signup_id),
                title: signup.shift_name || 'Untitled Shift',
                pantry: {
                    pantry_id: intValue(signup.pantry_id),
                    name: signup.pantry_name || 'Unknown Pantry',
                    location_address: signup.pantry_location || ''
                },
                pantry_id: intValue(signup.pantry_id),
                pantry_name: signup.pantry_name || 'Unknown Pantry',
                location: signup.pantry_location || '',
                role_title: signup.role_title || 'Unassigned',
                startDate,
                endDate,
                searchBlob: [
                    signup.shift_name,
                    signup.pantry_name,
                    signup.pantry_location,
                    signup.role_title
                ].filter(Boolean).join(' ').toLowerCase(),
                isPast: bucket === 'past',
                shift_id: intValue(signup.shift_id),
                signup_id: intValue(signup.signup_id),
                bucket
            };
        })
        .filter(Boolean)
        .sort((left, right) => left.startDate.getTime() - right.startDate.getTime());
}

function normalizeCalendarEvents(controller, items) {
    const normalize = typeof controller.config.normalizeEvents === 'function'
        ? controller.config.normalizeEvents
        : ((rows) => rows);
    return normalize(items, controller);
}

function filterCalendarEvents(controller, events) {
    return events.filter((event) => {
        if (controller.state.filters.pantryId !== 'all' && String(event.pantry_id) !== String(controller.state.filters.pantryId)) {
            return false;
        }
        if (controller.state.filters.search && !String(event.searchBlob || '').includes(controller.state.filters.search.toLowerCase())) {
            return false;
        }
        if (controller.state.filters.timeBucket !== 'all' && resolveCalendarTimeBucket(event.startDate) !== controller.state.filters.timeBucket) {
            return false;
        }
        return isEventInVisibleCalendarRange(controller, event);
    });
}

function renderDesktopMonthCalendar(controller, container, events) {
    const monthStart = startOfCalendarMonth(controller.state.selectedDate);
    const visibleStart = startOfCalendarWeek(monthStart);
    const cells = [];
    for (let index = 0; index < 42; index += 1) {
        const cellDate = addDays(visibleStart, index);
        const dayKey = getCalendarDateKey(cellDate);
        const dayEvents = events.filter((event) => getCalendarDateKey(event.startDate) === dayKey);
        const visibleEvents = dayEvents.slice(0, 2);
        const overflowCount = Math.max(0, dayEvents.length - visibleEvents.length);
        const isCurrentMonth = cellDate.getMonth() === monthStart.getMonth();
        const isToday = isSameCalendarDay(cellDate, new Date());
        const isSelected = isSameCalendarDay(cellDate, controller.state.selectedDate);
        cells.push(`
            <div class="calendar-month-cell${isCurrentMonth ? '' : ' is-outside'}${isToday ? ' is-today' : ''}${isSelected ? ' is-selected' : ''}">
                <button type="button" class="calendar-month-day-number" data-calendar-more-day="${dayKey}">${cellDate.getDate()}</button>
                <div class="calendar-month-events">
                    ${visibleEvents.map((event) => renderCalendarMonthEvent(controller, event)).join('')}
                    ${overflowCount > 0 ? `<button type="button" class="calendar-more-link" data-calendar-more-day="${dayKey}">+${overflowCount} more</button>` : ''}
                </div>
            </div>
        `);
    }

    container.innerHTML = `
        <div class="calendar-month-view">
            <div class="calendar-month-weekdays">
                ${CALENDAR_WEEKDAY_LONG_LABELS.map((label) => `<div>${label}</div>`).join('')}
            </div>
            <div class="calendar-month-grid">
                ${cells.join('')}
            </div>
        </div>
    `;
}

function renderCalendarMonthEvent(controller, event) {
    const palette = getCalendarEventPalette(event);
    const subtitle = typeof controller.config.getMonthSubtitle === 'function'
        ? controller.config.getMonthSubtitle(event, controller)
        : '';
    const badgeText = getCalendarEventBadgeText(controller, event);
    const spanIndicator = getCalendarSpanIndicator(event);

    return `
        <button
            type="button"
            class="calendar-month-event"
            data-calendar-event-id="${event.id}"
            style="background:${palette.soft}; color:${palette.text}; border-left-color:${palette.solid};"
        >
            <span class="calendar-month-event-time">${escapeHtml(formatLocalTimeRange(event.startDate, event.endDate, { includeDate: false }))}</span>
            <span class="calendar-month-event-title">${escapeHtml(event.title)}</span>
            ${subtitle ? `<span class="calendar-month-event-subtitle">${escapeHtml(subtitle)}</span>` : ''}
            ${badgeText ? `<span class="calendar-month-event-badge">${escapeHtml(badgeText)}</span>` : ''}
            ${spanIndicator ? `<span class="calendar-month-event-span">${escapeHtml(spanIndicator)}</span>` : ''}
        </button>
    `;
}

function renderDesktopWeekCalendar(controller, container, events) {
    const weekStart = startOfCalendarWeek(controller.state.selectedDate);
    const dayColumns = Array.from({ length: 7 }, (_, index) => addDays(weekStart, index));
    const hourBounds = getCalendarHourBounds(events);
    const slotHeight = 64;
    const totalHeight = (hourBounds.endHour - hourBounds.startHour) * slotHeight;
    const timeLabels = [];
    for (let hour = hourBounds.startHour; hour < hourBounds.endHour; hour += 1) {
        const hourDate = new Date(weekStart);
        hourDate.setHours(hour, 0, 0, 0);
        timeLabels.push(`
            <div class="calendar-week-time-slot" style="height:${slotHeight}px">
                <span>${escapeHtml(formatCalendarHourLabel(hourDate))}</span>
            </div>
        `);
    }

    const columnsHtml = dayColumns
        .map((dayDate) => renderWeekDayColumn(controller, dayDate, events, hourBounds, slotHeight, totalHeight))
        .join('');

    container.innerHTML = `
        <div class="calendar-week-view">
            <div class="calendar-week-header">
                <div class="calendar-week-time-gutter"></div>
                ${dayColumns.map((dayDate) => renderWeekDayHeader(dayDate)).join('')}
            </div>
            <div class="calendar-week-body">
                <div class="calendar-week-time-column">
                    ${timeLabels.join('')}
                </div>
                <div class="calendar-week-grid">
                    ${columnsHtml}
                </div>
            </div>
        </div>
    `;
}

function renderWeekDayHeader(dayDate) {
    const isToday = isSameCalendarDay(dayDate, new Date());
    return `
        <div class="calendar-week-day-header${isToday ? ' is-today' : ''}">
            <span class="calendar-week-day-label">${escapeHtml(formatCalendarDateLabel(dayDate, { weekday: 'short', month: 'short', day: 'numeric' }))}</span>
        </div>
    `;
}

function renderWeekDayColumn(controller, dayDate, events, hourBounds, slotHeight, totalHeight) {
    const dayEvents = events.filter((event) => isSameCalendarDay(event.startDate, dayDate));
    const layouts = layoutWeekDayEvents(dayEvents);
    const hourLines = [];
    for (let hour = hourBounds.startHour; hour < hourBounds.endHour; hour += 1) {
        hourLines.push(`<div class="calendar-week-hour-line" style="top:${(hour - hourBounds.startHour) * slotHeight}px"></div>`);
    }

    return `
        <div class="calendar-week-day-column">
            <div class="calendar-week-day-surface" style="height:${totalHeight}px">
                ${hourLines.join('')}
                ${layouts.map((entry) => renderWeekEventBlock(controller, entry, hourBounds.startHour, slotHeight)).join('')}
            </div>
        </div>
    `;
}

function layoutWeekDayEvents(dayEvents) {
    if (dayEvents.length === 0) {
        return [];
    }

    const sorted = [...dayEvents].sort((left, right) => left.startDate.getTime() - right.startDate.getTime());
    const groups = [];
    let currentGroup = [];
    let currentGroupEnd = null;

    sorted.forEach((event) => {
        if (currentGroup.length === 0) {
            currentGroup = [event];
            currentGroupEnd = event.endDate.getTime();
            return;
        }
        if (event.startDate.getTime() < Number(currentGroupEnd)) {
            currentGroup.push(event);
            currentGroupEnd = Math.max(Number(currentGroupEnd), event.endDate.getTime());
            return;
        }
        groups.push(currentGroup);
        currentGroup = [event];
        currentGroupEnd = event.endDate.getTime();
    });
    if (currentGroup.length > 0) {
        groups.push(currentGroup);
    }

    const layouts = [];
    groups.forEach((group) => {
        const laneEndTimes = [];
        group.forEach((event) => {
            const startMs = event.startDate.getTime();
            let laneIndex = laneEndTimes.findIndex((laneEnd) => laneEnd <= startMs);
            if (laneIndex === -1) {
                laneIndex = laneEndTimes.length;
                laneEndTimes.push(event.endDate.getTime());
            } else {
                laneEndTimes[laneIndex] = event.endDate.getTime();
            }
            layouts.push({
                event,
                laneIndex,
                laneCount: 0
            });
        });

        const laneCount = Math.max(1, laneEndTimes.length);
        layouts.forEach((entry) => {
            if (group.includes(entry.event)) {
                entry.laneCount = laneCount;
            }
        });
    });

    return layouts;
}

function renderWeekEventBlock(controller, entry, startHour, slotHeight) {
    const event = entry.event;
    const palette = getCalendarEventPalette(event);
    const startDecimal = event.startDate.getHours() + (event.startDate.getMinutes() / 60);
    const visualEnd = getCalendarDisplayEndDate(event);
    const endDecimal = visualEnd.getHours() + (visualEnd.getMinutes() / 60) + (visualEnd.getSeconds() / 3600);
    const top = Math.max(0, (startDecimal - startHour) * slotHeight);
    const height = Math.max(32, (endDecimal - startDecimal) * slotHeight);
    const laneWidth = 100 / entry.laneCount;
    const left = laneWidth * entry.laneIndex;
    const subtitle = typeof controller.config.getMonthSubtitle === 'function'
        ? controller.config.getMonthSubtitle(event, controller)
        : '';
    const badgeText = getCalendarEventBadgeText(controller, event);
    const spanIndicator = getCalendarSpanIndicator(event);
    const metaLines = getCalendarEventMetaLines(controller, event, 'week');

    return `
        <button
            type="button"
            class="calendar-week-event"
            data-calendar-event-id="${event.id}"
            style="
                top:${top}px;
                height:${height}px;
                left:calc(${left}% + 4px);
                width:calc(${laneWidth}% - 8px);
                background:${palette.soft};
                color:${palette.text};
                border-left-color:${palette.solid};
            "
        >
            <span class="calendar-week-event-title">${escapeHtml(event.title)}</span>
            ${subtitle ? `<span class="calendar-week-event-subtitle">${escapeHtml(subtitle)}</span>` : ''}
            <span class="calendar-week-event-meta">${escapeHtml(formatLocalTimeRange(event.startDate, event.endDate, { includeDate: false }))}</span>
            ${metaLines.map((line) => `<span class="calendar-week-event-meta">${escapeHtml(line)}</span>`).join('')}
            ${badgeText ? `<span class="calendar-week-event-badge">${escapeHtml(badgeText)}</span>` : ''}
            ${spanIndicator ? `<span class="calendar-week-event-span">${escapeHtml(spanIndicator)}</span>` : ''}
        </button>
    `;
}

function renderDesktopDayCalendar(controller, container, events) {
    const selectedDayKey = getCalendarDateKey(controller.state.selectedDate);
    const dayEvents = events
        .filter((event) => getCalendarDateKey(event.startDate) === selectedDayKey)
        .sort((left, right) => left.startDate.getTime() - right.startDate.getTime());

    container.innerHTML = `
        <div class="calendar-day-view">
            <div class="calendar-day-header">
                <h3>${escapeHtml(formatLocalDate(controller.state.selectedDate, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' }))}</h3>
                <p>${escapeHtml(controller.config.getDayCountText(dayEvents.length))}</p>
            </div>
            <div class="calendar-day-agenda">
                ${dayEvents.length > 0
                    ? dayEvents.map((event) => renderCalendarDayAgendaCard(controller, event)).join('')
                    : `<p class="empty-state">${escapeHtml(getCalendarEmptyText(controller))}</p>`}
            </div>
        </div>
    `;
}

function renderCalendarDayAgendaCard(controller, event) {
    const palette = getCalendarEventPalette(event);
    const subtitle = typeof controller.config.getMonthSubtitle === 'function'
        ? controller.config.getMonthSubtitle(event, controller)
        : '';
    const badgeText = getCalendarEventBadgeText(controller, event);
    const spanIndicator = getCalendarSpanIndicator(event);
    const metaLines = getCalendarEventMetaLines(controller, event, 'day');

    return `
        <button
            type="button"
            class="calendar-day-card"
            data-calendar-event-id="${event.id}"
            style="border-left-color:${palette.solid}"
        >
            <div class="calendar-day-card-time">${escapeHtml(formatLocalTimeRange(event.startDate, event.endDate, { includeDate: false }))}</div>
            <div class="calendar-day-card-title">${escapeHtml(event.title)}</div>
            ${subtitle ? `<div class="calendar-day-card-subtitle">${escapeHtml(subtitle)}</div>` : ''}
            ${badgeText ? `<div class="calendar-day-card-badge">${escapeHtml(badgeText)}</div>` : ''}
            ${spanIndicator ? `<div class="calendar-day-card-span">${escapeHtml(spanIndicator)}</div>` : ''}
            ${metaLines.map((line) => `<div class="calendar-day-card-meta">${escapeHtml(line)}</div>`).join('')}
        </button>
    `;
}

function renderPhoneCalendarAgenda(controller, container, events) {
    const grouped = groupPhoneAgendaEvents(events);
    const phoneViewName = capitalizeCalendarLabel(controller.state.view);
    const emptyText = getCalendarEmptyText(controller);

    container.innerHTML = `
        <div class="calendar-phone-view">
            <div class="calendar-phone-summary">
                <h3>${phoneViewName} Agenda</h3>
                <p>${escapeHtml(getCalendarRangeLabel(controller))}</p>
            </div>
            ${grouped.length > 0
                ? grouped.map((section) => renderPhoneAgendaSection(controller, section)).join('')
                : `<p class="empty-state">${escapeHtml(emptyText)}</p>`}
        </div>
    `;
}

function groupPhoneAgendaEvents(events) {
    const byPantry = new Map();
    events.forEach((event) => {
        const pantryKey = String(event.pantry_id);
        if (!byPantry.has(pantryKey)) {
            byPantry.set(pantryKey, {
                pantryId: event.pantry_id,
                pantryName: event.pantry_name,
                location: event.location || '',
                days: new Map()
            });
        }

        const pantrySection = byPantry.get(pantryKey);
        const dayKey = getCalendarDateKey(event.startDate);
        if (!pantrySection.days.has(dayKey)) {
            pantrySection.days.set(dayKey, {
                dayKey,
                label: formatLocalDate(event.startDate, { weekday: 'long', month: 'short', day: 'numeric', year: 'numeric' }),
                events: []
            });
        }
        pantrySection.days.get(dayKey).events.push(event);
    });

    return [...byPantry.values()]
        .sort((left, right) => left.pantryName.localeCompare(right.pantryName))
        .map((section) => ({
            ...section,
            days: [...section.days.values()].sort((left, right) => left.dayKey.localeCompare(right.dayKey))
        }));
}

function renderPhoneAgendaSection(controller, section) {
    const palette = getCalendarPantryPalette(section.pantryId);
    return `
        <section class="calendar-phone-pantry-section">
            <div class="calendar-phone-pantry-header" style="border-left-color:${palette.solid}">
                <h4>${escapeHtml(section.pantryName)}</h4>
                <p>${escapeHtml(section.location || 'Location unavailable')}</p>
            </div>
            <div class="calendar-phone-day-groups">
                ${section.days.map((dayGroup) => `
                    <div class="calendar-phone-day-group">
                        <div class="calendar-phone-day-title">${escapeHtml(dayGroup.label)}</div>
                        <div class="calendar-phone-event-list">
                            ${dayGroup.events
                                .sort((left, right) => left.startDate.getTime() - right.startDate.getTime())
                                .map((event) => renderPhoneAgendaEvent(controller, event))
                                .join('')}
                        </div>
                    </div>
                `).join('')}
            </div>
        </section>
    `;
}

function renderPhoneAgendaEvent(controller, event) {
    const palette = getCalendarEventPalette(event);
    const subtitle = typeof controller.config.getMonthSubtitle === 'function'
        ? controller.config.getMonthSubtitle(event, controller)
        : '';
    const badgeText = getCalendarEventBadgeText(controller, event);
    const spanIndicator = getCalendarSpanIndicator(event);
    const metaLines = getCalendarEventMetaLines(controller, event, 'phone');

    return `
        <button
            type="button"
            class="calendar-phone-event"
            data-calendar-event-id="${event.id}"
            style="border-left-color:${palette.solid}; background:${palette.soft}; color:${palette.text};"
        >
            <span class="calendar-phone-event-time">${escapeHtml(formatLocalTimeRange(event.startDate, event.endDate, { includeDate: false }))}</span>
            <span class="calendar-phone-event-title">${escapeHtml(event.title)}</span>
            ${subtitle ? `<span class="calendar-phone-event-subtitle">${escapeHtml(subtitle)}</span>` : ''}
            ${badgeText ? `<span class="calendar-phone-event-badge">${escapeHtml(badgeText)}</span>` : ''}
            ${spanIndicator ? `<span class="calendar-phone-event-span">${escapeHtml(spanIndicator)}</span>` : ''}
            ${metaLines.map((line) => `<span class="calendar-phone-event-meta">${escapeHtml(line)}</span>`).join('')}
        </button>
    `;
}

function renderAvailableCalendarModalRole(role, event) {
    const filled = Number(role.filled_count || 0);
    const required = Number(role.required_count || 0);
    const isFull = required > 0 && filled >= required;
    const isCancelled = String(role.status || 'OPEN').toUpperCase() === 'CANCELLED'
        || String(event.status || 'OPEN').toUpperCase() === 'CANCELLED';
    const capacityPercent = getCalendarRoleCapacityPercent(filled, required);
    const canVolunteerSignup = currentUserHasRole('VOLUNTEER');
    const isPast = Boolean(event.isPast);

    let buttonLabel = 'Sign Up';
    let disabled = false;
    if (!canVolunteerSignup) {
        buttonLabel = 'Volunteer Only';
        disabled = true;
    } else if (isPast) {
        buttonLabel = 'Past';
        disabled = true;
    } else if (isCancelled) {
        buttonLabel = 'Unavailable';
        disabled = true;
    } else if (isFull) {
        buttonLabel = 'Full';
        disabled = true;
    }

    return `
        <div class="calendar-modal-role-item">
            <div class="calendar-modal-role-info">
                <div class="calendar-modal-role-title">${escapeHtml(role.role_title || 'Volunteer Role')}</div>
                <div class="calendar-modal-role-meta">${filled}/${required} filled</div>
                <div class="calendar-modal-role-capacity" aria-hidden="true">
                    <div class="calendar-modal-role-capacity-track">
                        <div
                            class="calendar-modal-role-capacity-fill${isFull ? ' is-full' : ''}${isCancelled ? ' is-cancelled' : ''}"
                            style="width:${capacityPercent}%"
                        ></div>
                    </div>
                    <div class="calendar-modal-role-capacity-label">${escapeHtml(getCalendarRoleCapacityLabel(filled, required, isCancelled))}</div>
                </div>
            </div>
            <button
                type="button"
                class="btn ${disabled ? 'btn-secondary' : 'btn-success'} btn-sm"
                data-calendar-action="${disabled ? '' : 'signup-role'}"
                data-role-id="${disabled ? '' : role.shift_role_id}"
                ${disabled ? 'disabled' : ''}
            >${buttonLabel}</button>
        </div>
    `;
}

function renderMyShiftCalendarModalActions(event) {
    const signupStatus = String(event.signup_status || 'UNKNOWN').toUpperCase();
    const shiftStatus = String(event.shift_status || 'OPEN').toUpperCase();
    const showCancelByTime = canCancelSignup(event, new Date());
    const nonActionableStatuses = new Set(['CANCELLED', 'WAITLISTED']);
    const showCancel = showCancelByTime
        && !nonActionableStatuses.has(signupStatus)
        && shiftStatus !== 'CANCELLED';
    const isPendingReconfirm = signupStatus === 'PENDING_CONFIRMATION';
    const reconfirmAvailable = Boolean(event.reconfirm_available);

    if (isPendingReconfirm) {
        return `
            <div class="calendar-modal-actions">
                ${reconfirmAvailable
                    ? `<button type="button" class="btn btn-success" data-calendar-action="confirm-signup" data-signup-id="${event.signup_id}">Confirm</button>`
                    : '<span class="reconfirm-note">Role is full or unavailable for reconfirmation.</span>'}
                <button type="button" class="btn btn-danger" data-calendar-action="cancel-reconfirm-signup" data-signup-id="${event.signup_id}">Cancel</button>
            </div>
        `;
    }

    if (showCancel) {
        return `
            <div class="calendar-modal-actions">
                <button type="button" class="btn btn-danger" data-calendar-action="cancel-signup" data-signup-id="${event.signup_id}">Cancel Signup</button>
            </div>
        `;
    }

    return '<div class="calendar-modal-actions"><span class="calendar-modal-action-note">No actions available for this shift.</span></div>';
}

function getCalendarRoleCapacityPercent(filled, required) {
    if (required <= 0) {
        return 0;
    }
    return Math.max(0, Math.min(100, Math.round((filled / required) * 100)));
}

function getCalendarRoleCapacityLabel(filled, required, isCancelled) {
    if (isCancelled) {
        return 'Shift unavailable';
    }
    if (required <= 0) {
        return 'Capacity not set';
    }
    const remaining = Math.max(0, required - filled);
    if (remaining === 0) {
        return 'No spots left';
    }
    return `${remaining} spot${remaining === 1 ? '' : 's'} left`;
}

function getCalendarVisibleRangeForController(controller) {
    if (controller.state.view === 'day') {
        return {
            start: startOfCalendarDay(controller.state.selectedDate),
            end: endOfCalendarDay(controller.state.selectedDate)
        };
    }
    if (controller.state.view === 'week') {
        const start = startOfCalendarWeek(controller.state.selectedDate);
        return {
            start,
            end: endOfCalendarDay(addDays(start, 6))
        };
    }

    const monthStart = startOfCalendarMonth(controller.state.selectedDate);
    const start = startOfCalendarWeek(monthStart);
    const end = endOfCalendarDay(addDays(start, 41));
    return { start, end };
}

function isEventInVisibleCalendarRange(controller, event) {
    const visibleRange = getCalendarVisibleRangeForController(controller);
    return event.endDate >= visibleRange.start && event.startDate <= visibleRange.end;
}

function getCalendarRangeLabel(controller) {
    if (controller.state.view === 'day') {
        return formatCalendarDateLabel(controller.state.selectedDate, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
    }
    if (controller.state.view === 'week') {
        const weekStart = startOfCalendarWeek(controller.state.selectedDate);
        const weekEnd = addDays(weekStart, 6);
        return formatCalendarWeekRangeLabel(weekStart, weekEnd);
    }
    return formatCalendarDateLabel(controller.state.selectedDate, { month: 'long', year: 'numeric' });
}

function formatCalendarWeekRangeLabel(weekStart, weekEnd) {
    const sameYear = weekStart.getFullYear() === weekEnd.getFullYear();
    const sameMonth = sameYear && weekStart.getMonth() === weekEnd.getMonth();
    if (sameMonth) {
        const monthLabel = formatCalendarDateLabel(weekStart, { month: 'short' });
        return `${monthLabel} ${weekStart.getDate()} - ${weekEnd.getDate()}, ${weekStart.getFullYear()}`;
    }
    if (sameYear) {
        const startLabel = formatCalendarDateLabel(weekStart, { month: 'short', day: 'numeric' });
        const endLabel = formatCalendarDateLabel(weekEnd, { month: 'short', day: 'numeric' });
        return `${startLabel} - ${endLabel}, ${weekStart.getFullYear()}`;
    }
    const startLabel = formatCalendarDateLabel(weekStart, { month: 'short', day: 'numeric', year: 'numeric' });
    const endLabel = formatCalendarDateLabel(weekEnd, { month: 'short', day: 'numeric', year: 'numeric' });
    return `${startLabel} - ${endLabel}`;
}

function shiftCalendarAnchorForController(controller, direction) {
    if (controller.state.view === 'day') {
        controller.state.selectedDate = addDays(controller.state.selectedDate, direction);
        controller.state.miniDate = startOfCalendarMonth(controller.state.selectedDate);
        return;
    }
    if (controller.state.view === 'week') {
        controller.state.selectedDate = addDays(controller.state.selectedDate, direction * 7);
        controller.state.miniDate = startOfCalendarMonth(controller.state.selectedDate);
        return;
    }
    controller.state.selectedDate = addMonths(controller.state.selectedDate, direction);
    controller.state.miniDate = startOfCalendarMonth(controller.state.selectedDate);
}

function getCalendarHourBounds(events) {
    if (!events || events.length === 0) {
        return { startHour: 8, endHour: 18 };
    }

    let minHour = 23;
    let maxHour = 0;
    events.forEach((event) => {
        const startHour = event.startDate.getHours() + (event.startDate.getMinutes() / 60);
        const visualEnd = getCalendarDisplayEndDate(event);
        const endHour = visualEnd.getHours() + (visualEnd.getMinutes() / 60) + (visualEnd.getSeconds() / 3600);
        minHour = Math.min(minHour, Math.floor(startHour));
        maxHour = Math.max(maxHour, Math.ceil(endHour));
    });

    minHour = Math.max(6, minHour - 1);
    maxHour = Math.min(24, maxHour + 1);
    if (maxHour - minHour < 8) {
        maxHour = Math.min(24, minHour + 8);
    }
    return { startHour: minHour, endHour: maxHour };
}

function getCalendarPantryList() {
    return normalizeCalendarPantryList(allPublicPantries);
}

function getCalendarPantriesFromEvents(events) {
    const byPantry = new Map();
    (Array.isArray(events) ? events : []).forEach((event) => {
        if (!event || event.pantry_id === undefined || event.pantry_id === null) {
            return;
        }
        const pantryKey = String(event.pantry_id);
        if (!byPantry.has(pantryKey)) {
            byPantry.set(pantryKey, {
                pantry_id: intValue(event.pantry_id),
                name: event.pantry_name || `Pantry ${event.pantry_id}`
            });
        }
    });
    return normalizeCalendarPantryList([...byPantry.values()]);
}

function normalizeCalendarPantryList(items) {
    return Array.isArray(items)
        ? [...items]
            .filter(Boolean)
            .map((pantry) => ({
                pantry_id: intValue(pantry.pantry_id),
                name: pantry.name || `Pantry ${pantry.pantry_id}`
            }))
            .sort((left, right) => String(left.name || '').localeCompare(String(right.name || '')))
        : [];
}

function getCalendarPantryNameById(controller, pantryId) {
    const pantry = controller.getPantryList().find((item) => intValue(item.pantry_id) === intValue(pantryId));
    return pantry ? pantry.name : '';
}

function getCalendarPantryPalette(pantryId) {
    const normalizedId = Math.abs(intValue(pantryId));
    return CALENDAR_COLOR_PALETTE[normalizedId % CALENDAR_COLOR_PALETTE.length];
}

function getCalendarEventPalette(event) {
    if (event && event.isPast) {
        return CALENDAR_NEUTRAL_PALETTE;
    }
    return getCalendarPantryPalette(event?.pantry_id);
}

function getCalendarEventBadgeText(controller, event) {
    return typeof controller.config.getEventBadgeText === 'function'
        ? controller.config.getEventBadgeText(event, controller)
        : '';
}

function getCalendarEventMetaLines(controller, event, view) {
    return typeof controller.config.getEventMetaLines === 'function'
        ? controller.config.getEventMetaLines(event, view, controller) || []
        : [];
}

function getCalendarEmptyText(controller) {
    return controller.state.events.length === 0
        ? (controller.config.noEventsText || 'No shifts available.')
        : (controller.config.noMatchesText || 'No shifts match the selected range and filters.');
}

function getMyShiftCalendarBadgeText(event) {
    const signupStatus = String(event.signup_status || '').toUpperCase();
    const shiftStatus = String(event.shift_status || '').toUpperCase();
    if (shiftStatus === 'CANCELLED') {
        return 'Shift Cancelled';
    }
    if (signupStatus === 'PENDING_CONFIRMATION') {
        return 'Needs Reconfirm';
    }
    if (signupStatus === 'SHOW_UP') {
        return 'Attended';
    }
    if (signupStatus === 'NO_SHOW') {
        return 'Missed';
    }
    if (signupStatus === 'WAITLISTED') {
        return 'Waitlisted';
    }
    if (event.isPast) {
        return 'Past';
    }
    return formatCalendarStatusLabel(signupStatus || 'CONFIRMED');
}

function formatCalendarStatusLabel(value) {
    const normalized = String(value || '').trim();
    if (!normalized) {
        return '';
    }
    return normalized
        .toLowerCase()
        .replace(/_/g, ' ')
        .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function renderCalendarRoleSummary(roles) {
    if (!Array.isArray(roles) || roles.length === 0) {
        return 'No roles available';
    }
    return roles.map((role) => `${role.role_title || 'Role'} (${role.filled_count || 0}/${role.required_count || 0})`).join(', ');
}

function resolveCalendarTimeBucket(date) {
    const hour = date.getHours();
    if (hour < 12) {
        return 'morning';
    }
    if (hour < 17) {
        return 'afternoon';
    }
    return 'evening';
}

function isCalendarMultiDayEvent(event) {
    return getCalendarDateKey(event.startDate) !== getCalendarDateKey(event.endDate);
}

function getCalendarDisplayEndDate(event) {
    const endOfStartDay = endOfCalendarDay(event.startDate);
    return event.endDate.getTime() > endOfStartDay.getTime() ? endOfStartDay : event.endDate;
}

function getCalendarSpanIndicator(event) {
    if (!isCalendarMultiDayEvent(event)) {
        return '';
    }

    const daySpan = Math.round(
        (startOfCalendarDay(event.endDate).getTime() - startOfCalendarDay(event.startDate).getTime()) / (24 * 60 * 60 * 1000)
    );
    return daySpan > 1 ? 'Multi-day' : 'Continues next day';
}

function capitalizeCalendarLabel(value) {
    const normalized = String(value || '').trim();
    return normalized ? normalized.charAt(0).toUpperCase() + normalized.slice(1) : '';
}

function intValue(value) {
    return parseInt(String(value || '0'), 10) || 0;
}

function startOfCalendarDay(value) {
    const date = new Date(value);
    date.setHours(0, 0, 0, 0);
    return date;
}

function endOfCalendarDay(value) {
    const date = startOfCalendarDay(value);
    date.setHours(23, 59, 59, 999);
    return date;
}

function startOfCalendarWeek(value) {
    const date = startOfCalendarDay(value);
    const dayIndex = (date.getDay() + 6) % 7;
    date.setDate(date.getDate() - dayIndex);
    return date;
}

function startOfCalendarMonth(value) {
    const date = startOfCalendarDay(value);
    date.setDate(1);
    return date;
}

function addDays(value, amount) {
    const date = new Date(value);
    date.setDate(date.getDate() + amount);
    return date;
}

function addMonths(value, amount) {
    const date = new Date(value);
    const previousDay = date.getDate();
    date.setDate(1);
    date.setMonth(date.getMonth() + amount);
    date.setDate(Math.min(previousDay, new Date(date.getFullYear(), date.getMonth() + 1, 0).getDate()));
    return date;
}

function getCalendarDateKey(date) {
    const normalized = startOfCalendarDay(date);
    const year = normalized.getFullYear();
    const month = String(normalized.getMonth() + 1).padStart(2, '0');
    const day = String(normalized.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

function parseCalendarDateKey(value) {
    if (!value) {
        return null;
    }
    const date = new Date(`${value}T00:00:00`);
    return Number.isNaN(date.getTime()) ? null : startOfCalendarDay(date);
}

function isSameCalendarDay(left, right) {
    return getCalendarDateKey(left) === getCalendarDateKey(right);
}

function formatCalendarDateLabel(value, options = {}) {
    const date = getDateInstance(value);
    if (!date) {
        return '';
    }

    const formatterOptions = { timeZone: getDisplayTimeZone() };
    if (options.weekday !== undefined) formatterOptions.weekday = options.weekday;
    if (options.month !== undefined) formatterOptions.month = options.month;
    if (options.day !== undefined) formatterOptions.day = options.day;
    if (options.year !== undefined) formatterOptions.year = options.year;
    return new Intl.DateTimeFormat('en-US', formatterOptions).format(date);
}

function formatCalendarHourLabel(value) {
    const date = getDateInstance(value);
    if (!date) {
        return '';
    }

    return new Intl.DateTimeFormat('en-US', {
        timeZone: getDisplayTimeZone(),
        hour: 'numeric',
        minute: '2-digit',
        hour12: true
    }).format(date);
}

function loadCalendarShifts(forceReload = true) {
    const controller = getCalendarController('available');
    return controller ? controller.load(forceReload) : Promise.resolve();
}

function syncCalendarPantryOptions() {
    ensureCalendarControllersRegistered();
    calendarControllers.forEach((controller) => controller.syncPantryOptions());
}

function setMyShiftsCalendarItems(items, forceReload = true) {
    const controller = getCalendarController('my-shifts');
    return controller ? controller.setSourceItems(items, forceReload) : Promise.resolve();
}

window.getCalendarController = getCalendarController;
window.initializeCalendarUi = initializeCalendarUi;
window.loadCalendarShifts = loadCalendarShifts;
window.syncCalendarPantryOptions = syncCalendarPantryOptions;
window.setMyShiftsCalendarItems = setMyShiftsCalendarItems;
