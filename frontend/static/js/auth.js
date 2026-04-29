let authConfig = null;
let firebaseAuthInstance = null;
let googleProvider = null;
let pendingGoogleIdToken = null;
const AUTH_APP_TOUR_PENDING_COOKIE = 'volunteerAppTourPendingSignup';

document.addEventListener('DOMContentLoaded', async () => {
    bindAuthEventListeners();
    await bootstrapAuthShell();
});

async function bootstrapAuthShell() {
    setAuthLoading(true, 'Checking authentication...');
    clearAuthMessage();

    try {
        authConfig = await apiGet('/api/auth/config');
        updateAuthProviderLabel(authConfig.provider);
        configureProviderUi(authConfig);

        if (authConfig.provider === 'firebase') {
            initializeFirebaseClient(authConfig.firebase || {});
        }

        try {
            await getCurrentUser();
            await enterApp();
            return;
        } catch (error) {
            if (error.status && error.status !== 401) {
                throw error;
            }
        }

        showAuthShell();
        setAuthLoading(false);
    } catch (error) {
        console.error('Failed to bootstrap auth shell:', error);
        showAuthShell();
        showAuthMessage(error.message || 'Failed to load authentication', 'error');
        setAuthLoading(false);
    }
}

function bindAuthEventListeners() {
    document.getElementById('google-login-btn')?.addEventListener('click', async (event) => {
        await withButtonLock(event.currentTarget, () => startGoogleFlow('login'));
    });

    document.getElementById('google-signup-btn')?.addEventListener('click', async (event) => {
        await withButtonLock(event.currentTarget, () => startGoogleFlow('signup'));
    });

    document.getElementById('google-signup-form')?.addEventListener('submit', async (event) => {
        event.preventDefault();
        await completeGoogleSignup(getSubmitButtonFromEvent(event));
    });

    document.getElementById('cancel-signup-btn')?.addEventListener('click', async (event) => {
        await withButtonLock(event.currentTarget, async () => {
            await resetPendingGoogleSignup();
            hideGoogleSignupForm();
            clearAuthMessage();
        });
    });

    document.getElementById('logout-btn')?.addEventListener('click', async (event) => {
        await withButtonLock(event.currentTarget, handleLogout);
    });
}

function configureProviderUi(config) {
    const provider = config.provider === 'firebase' ? 'firebase' : 'memory';
    document.getElementById('auth-provider-memory')?.classList.toggle('app-hidden', provider !== 'memory');
    document.getElementById('auth-provider-firebase')?.classList.toggle('app-hidden', provider !== 'firebase');

    if (provider === 'memory') {
        renderMemoryAccounts(config.memory_accounts || []);
    }
}

function initializeFirebaseClient(config) {
    if (!window.firebase) {
        throw new Error('Firebase SDK failed to load in the browser');
    }
    const missing = ['apiKey', 'authDomain', 'projectId', 'appId'].filter((key) => !config[key]);
    if (missing.length > 0) {
        throw new Error(`Missing Firebase browser config: ${missing.join(', ')}`);
    }

    const app = window.firebase.apps.length > 0 ? window.firebase.app() : window.firebase.initializeApp(config);
    firebaseAuthInstance = window.firebase.auth(app);
    googleProvider = new window.firebase.auth.GoogleAuthProvider();
    googleProvider.setCustomParameters({ prompt: 'select_account' });
}

function renderMemoryAccounts(accounts) {
    const container = document.getElementById('memory-login-list');
    if (!container) {
        return;
    }

    if (!accounts || accounts.length === 0) {
        container.innerHTML = '<p class="auth-empty">No sample accounts are configured.</p>';
        return;
    }

    container.innerHTML = accounts
        .map((account) => `
            <button class="auth-account-card" data-memory-account="${account.id}">
                <span class="auth-account-label">${escapeAuthHtml(account.label || account.id)}</span>
                <span class="auth-account-email">${escapeAuthHtml(account.email || '')}</span>
                <span class="auth-account-description">${escapeAuthHtml(account.description || '')}</span>
            </button>
        `)
        .join('');

    container.querySelectorAll('[data-memory-account]').forEach((button) => {
        button.addEventListener('click', async () => {
            const sampleAccountId = button.dataset.memoryAccount;
            await withButtonLock(button, () => loginWithMemory(sampleAccountId));
        });
    });
}

async function loginWithMemory(sampleAccountId) {
    setAuthLoading(true, 'Signing in...');
    clearAuthMessage();

    try {
        await apiPost('/api/auth/login/memory', { sample_account_id: sampleAccountId });
        window.location.reload();
    } catch (error) {
        showAuthMessage(error.message || 'Memory login failed', 'error');
        setAuthLoading(false);
    }
}

async function startGoogleFlow(intent) {
    if (!firebaseAuthInstance || !googleProvider) {
        showAuthMessage('Firebase client is not ready.', 'error');
        return;
    }

    setAuthLoading(true, intent === 'signup' ? 'Connecting your Google account...' : 'Signing in with Google...');
    clearAuthMessage();

    try {
        const result = await firebaseAuthInstance.signInWithPopup(googleProvider);
        pendingGoogleIdToken = await result.user.getIdToken(true);

        const loginResponse = await apiPost('/api/auth/login/google', {
            id_token: pendingGoogleIdToken
        });

        if (loginResponse.signup_required) {
            showGoogleSignupForm(loginResponse);
            setAuthLoading(false);
            return;
        }

        await firebaseAuthInstance.signOut();
        window.location.reload();
    } catch (error) {
        console.error('Google auth flow failed:', error);
        await resetPendingGoogleSignup();
        showAuthMessage(error.message || 'Google sign-in failed', 'error');
        setAuthLoading(false);
    }
}

function showGoogleSignupForm(payload) {
    const signupForm = document.getElementById('google-signup-form');
    if (!signupForm) {
        return;
    }

    document.getElementById('signup-email-preview').textContent = payload.email || '';
    document.getElementById('signup-full-name').value = payload.display_name || '';
    document.getElementById('signup-phone-number').value = '';
    signupForm.classList.remove('app-hidden');
    document.getElementById('signup-full-name')?.focus();
    showAuthMessage('Complete your profile to finish signup.', 'info');
}

function hideGoogleSignupForm() {
    document.getElementById('google-signup-form')?.classList.add('app-hidden');
    document.getElementById('signup-email-preview').textContent = '';
    const form = document.getElementById('google-signup-form');
    form?.reset();
}

async function completeGoogleSignup(buttonEl = null) {
    if (!pendingGoogleIdToken) {
        showAuthMessage('Start with Google signup first.', 'error');
        return;
    }

    const fullName = document.getElementById('signup-full-name')?.value.trim() || '';
    const phoneNumber = document.getElementById('signup-phone-number')?.value.trim() || '';
    if (!fullName || !phoneNumber) {
        showAuthMessage('Name and phone number are required.', 'error');
        return;
    }

    await withButtonLock(buttonEl, async () => {
        setAuthLoading(true, 'Creating your account...');
        clearAuthMessage();

        try {
            await apiPost('/api/auth/signup/google', {
                id_token: pendingGoogleIdToken,
                full_name: fullName,
                phone_number: phoneNumber,
                timezone: getBrowserTimeZone()
            });
            if (window.Cookies) {
                window.Cookies.set(AUTH_APP_TOUR_PENDING_COOKIE, 'pending', { sameSite: 'Lax' });
            }
            await firebaseAuthInstance?.signOut();
            window.location.reload();
        } catch (error) {
            showAuthMessage(error.message || 'Signup failed', 'error');
            setAuthLoading(false);
        }
    });
}

async function resetPendingGoogleSignup() {
    pendingGoogleIdToken = null;
    if (firebaseAuthInstance) {
        try {
            await firebaseAuthInstance.signOut();
        } catch (_error) {
            // Ignore client-side cleanup failures.
        }
    }
}

async function handleLogout() {
    try {
        await apiCall('/api/auth/logout', { method: 'POST' });
    } catch (error) {
        console.error('Logout failed:', error);
    }

    await resetPendingGoogleSignup();
    window.location.reload();
}

async function reauthenticateFirebaseUserForSensitiveAction(currentUser) {
    if (authConfig?.provider !== 'firebase') {
        throw new Error('Firebase-sensitive actions are unavailable in the current auth mode.');
    }
    if (!firebaseAuthInstance || !googleProvider) {
        throw new Error('Firebase client is not ready.');
    }
    if (!currentUser || !currentUser.auth_uid) {
        throw new Error('Your account is not linked to Firebase yet. Please sign in again with Google first.');
    }

    clearAuthMessage();

    try {
        // Force a fresh Google reauthentication before changing a security-sensitive field.
        await resetPendingGoogleSignup();
        const result = await firebaseAuthInstance.signInWithPopup(googleProvider);
        const signedInUser = result?.user;
        if (!signedInUser) {
            throw new Error('Google reauthentication did not return a user.');
        }
        if (signedInUser.uid !== currentUser.auth_uid) {
            throw new Error('Please reauthenticate with the same Google account that you use for this app.');
        }
        return signedInUser;
    } catch (error) {
        const code = error?.code || '';
        if (code === 'auth/popup-closed-by-user') {
            throw new Error('Google reauthentication was cancelled.');
        }
        throw error;
    }
}

async function requestFirebaseEmailChange(currentUser, newEmail) {
    try {
        const signedInUser = await reauthenticateFirebaseUserForSensitiveAction(currentUser);
        if (typeof signedInUser.verifyBeforeUpdateEmail !== 'function') {
            throw new Error('This Firebase client does not support verified email updates.');
        }

        await signedInUser.verifyBeforeUpdateEmail(newEmail);
        return {
            ok: true,
            message: `Verification sent to ${newEmail}. Open that email, confirm the change, then sign in again.`
        };
    } catch (error) {
        const code = error?.code || '';
        if (code === 'auth/email-already-in-use') {
            throw new Error('That email is already used by another Firebase account.');
        }
        if (code === 'auth/invalid-email') {
            throw new Error('Enter a valid email address.');
        }
        throw error;
    } finally {
        await resetPendingGoogleSignup();
    }
}

async function requestFirebaseAccountDeletion(currentUser) {
    try {
        const signedInUser = await reauthenticateFirebaseUserForSensitiveAction(currentUser);
        const idToken = await signedInUser.getIdToken(true);
        return { idToken };
    } finally {
        await resetPendingGoogleSignup();
    }
}

async function enterApp() {
    hideAuthShell();
    showAppShell();
    setAuthLoading(false);
    await window.initializeDashboardApp();
}

function showAuthShell() {
    document.getElementById('auth-shell')?.classList.remove('app-hidden');
    document.getElementById('app-shell')?.classList.add('app-hidden');
}

function hideAuthShell() {
    document.getElementById('auth-shell')?.classList.add('app-hidden');
}

function showAppShell() {
    document.getElementById('app-shell')?.classList.remove('app-hidden');
}

function setAuthLoading(isLoading, message = 'Loading...') {
    const loading = document.getElementById('auth-loading');
    if (!loading) {
        return;
    }

    loading.classList.toggle('app-hidden', !isLoading);
    const text = loading.querySelector('p');
    if (text) {
        text.textContent = message;
    }
}

function showAuthMessage(text, type = 'info') {
    const messageEl = document.getElementById('auth-message');
    if (!messageEl) {
        return;
    }
    messageEl.className = `message message-${type} show`;
    messageEl.textContent = text;
}

function clearAuthMessage() {
    const messageEl = document.getElementById('auth-message');
    if (!messageEl) {
        return;
    }
    messageEl.className = 'message';
    messageEl.textContent = '';
}

function updateAuthProviderLabel(provider) {
    const badge = document.getElementById('auth-mode-badge');
    if (!badge) {
        return;
    }
    badge.textContent = provider === 'firebase' ? 'Google / Firebase Auth' : 'In-Memory Demo Auth';
}

function escapeAuthHtml(value) {
    return String(value || '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
}

window.requestFirebaseEmailChange = requestFirebaseEmailChange;
window.requestFirebaseAccountDeletion = requestFirebaseAccountDeletion;
