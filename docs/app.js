import { createClient } from 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js/+esm'

// ==========================================
// CONFIGURATION
// ==========================================
// User: REPLACE THESE WITH YOUR SUPABASE URL AND ANON KEY
const SUPABASE_URL = 'https://bypylhidbypuxyzftnql.supabase.co'
const SUPABASE_KEY = 'sb_publishable_Exmk6eczWCZz79ScNdxsEg_HeSFKnFS'
const API_BASE = 'https://punk-vending-scary.ngrok-free.dev/api'

// Initialize Supabase Client
let supabase = null;
let currentUser = null;

if (SUPABASE_URL !== 'YOUR_SUPABASE_URL') {
    supabase = createClient(SUPABASE_URL, SUPABASE_KEY);
}

// Icons (Coolicons SVG)
const icons = {
    search: `<svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>`,
    shield: `<svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>`,
    alert: `<svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>`,
    check: `<svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>`,
    google: `<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M12.545,10.239v3.821h5.445c-0.712,2.315-2.647,3.972-5.445,3.972c-3.332,0-6.033-2.701-6.033-6.032s2.701-6.032,6.033-6.032c1.498,0,2.866,0.549,3.921,1.453l2.814-2.814C17.503,2.988,15.139,2,12.545,2C7.021,2,2.543,6.477,2.543,12s4.478,10,10.002,10c8.396,0,10.249-7.85,9.426-11.761H12.545z"/></svg>`,
    link: `<svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path></svg>`
};

// ==========================================
// CORE UTILS
// ==========================================
async function fetchApi(endpoint, options = {}) {
    try {
        const res = await fetch(`${API_BASE}${endpoint}`, Object.assign({
            headers: { 
                'Content-Type': 'application/json',
                'ngrok-skip-browser-warning': 'any'
            }
        }, options));
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'API Error');
        return data;
    } catch (e) {
        alert(e.message);
        throw e;
    }
}

// Auth Handlers
async function initAuth() {
    const authSection = document.getElementById('auth-section');
    if (!supabase) {
        authSection.innerHTML = `<span class="badge pending">Auth Not Configured</span>`;
        return;
    }

    const { data: { session } } = await supabase.auth.getSession();
    currentUser = session?.user || null;

    supabase.auth.onAuthStateChange((_event, session) => {
        currentUser = session?.user || null;
        renderAuthUI();
        // Refresh view to apply auth lock checks
        router();
    });

    renderAuthUI();
}

function renderAuthUI() {
    const authSection = document.getElementById('auth-section');
    if (currentUser) {
        authSection.innerHTML = `
            <div class="flex-row">
                <span style="font-size: 0.9rem; font-weight:500;">${currentUser.email}</span>
                <button class="btn btn-secondary" onclick="signOut()" style="padding: 6px 12px; font-size: 0.8rem;">Sign Out</button>
            </div>
        `;
    } else {
        authSection.innerHTML = `
            <button class="btn" onclick="signInWithGoogle()">
                ${icons.google} Sign in with Google
            </button>
        `;
    }
}

window.signInWithGoogle = async () => {
    if (!supabase) return alert("Supabase JS is not configured in app.js");
    await supabase.auth.signInWithOAuth({ 
        provider: 'google',
        options: {
            redirectTo: window.location.origin + window.location.pathname
        }
    });
}

window.signOut = async () => {
    await supabase.auth.signOut();
}

// Router
function router() {
    const hash = window.location.hash || '#home';
    const appDiv = document.getElementById('app');
    appDiv.innerHTML = '<div style="text-align:center; padding: 40px; color: var(--text-secondary);">Loading...</div>';

    if (hash === '#home') {
        renderHome(appDiv);
    } else if (hash === '#leaderboard') {
        renderLeaderboard(appDiv);
    } else if (hash.startsWith('#run/')) {
        const runId = hash.split('/')[1];
        renderRunDetail(appDiv, runId);
    }
}

window.addEventListener('hashchange', router);

// ==========================================
// VIEWS
// ==========================================

// 1. HOME VIEW
async function renderHome(container) {
    let runsHtml = '';
    try {
        const runs = await fetchApi('/runs');

        if (runs.length === 0) {
            runsHtml = `<div class="empty-state">No scrapes executed yet.</div>`;
        } else {
            runsHtml = `
                <table>
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Status</th>
                            <th>Type</th>
                            <th>Input / Source</th>
                            <th>Evil Found</th>
                            <th>Date</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${runs.map(r => `
                            <tr>
                                <td>#${r.id}</td>
                                <td><span class="badge ${r.status}">${r.status}</span></td>
                                <td style="text-transform: capitalize;">${r.run_type}</td>
                                <td><div style="max-width:200px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="${r.input_url || r.sources.join(', ')}">${r.input_url || r.sources.join(', ')}</div></td>
                                <td style="font-weight:600; color: ${r.evil_found > 0 ? 'var(--danger-color)' : 'inherit'}">${r.evil_found}</td>
                                <td>${new Date(r.created_at).toLocaleString()}</td>
                                <td>
                                    <a href="#run/${r.id}" class="btn btn-secondary" style="padding: 4px 10px; font-size: 0.8rem;">View</a>
                                </td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            `;
        }
    } catch (e) {
        runsHtml = `<div class="empty-state" style="color:var(--danger-color)">Failed to load runs. Ensure local backend is running.</div>`;
    }

    const disableScrape = !supabase ? '' : (!currentUser ? 'disabled' : '');
    const authWarning = (!currentUser && supabase)
        ? `<div class="alert warning">${icons.alert} You must sign in to submit new scraping jobs.</div>`
        : ``;

    container.innerHTML = `
        ${authWarning}
        <div class="grid-2">
            <div class="card">
                <h2>${icons.search} Single URL Scrape</h2>
                <p class="text-secondary mb-4">Analyze a single website or document for AI risk signatures.</p>
                <div class="form-group">
                    <label>Target URL</label>
                    <input type="url" id="url-input" class="input" placeholder="https://example.com" ${disableScrape}>
                </div>
                <button class="btn" onclick="submitUrlScrape()" ${disableScrape}>Analyze URL</button>
            </div>

            <div class="card">
                <h2>${icons.shield} Source Directory Scrape</h2>
                <p class="text-secondary mb-4">Pull latest research and tools from major sources.</p>
                <form id="source-form">
                    <div class="grid-auto mb-4">
                        <label class="checkbox-group"><input type="checkbox" name="source" value="arxiv" ${disableScrape}> arXiv Papers</label>
                        <label class="checkbox-group"><input type="checkbox" name="source" value="github" ${disableScrape}> GitHub repos</label>
                        <label class="checkbox-group"><input type="checkbox" name="source" value="huggingface" ${disableScrape}> HuggingFace</label>
                        <label class="checkbox-group"><input type="checkbox" name="source" value="newsapi" ${disableScrape}> News API</label>
                        <label class="checkbox-group"><input type="checkbox" name="source" value="manifest:high_yield" ${disableScrape} checked> Manifest</label>
                    </div>
                    <div class="form-group">
                        <label>Max Results Limit</label>
                        <input type="number" id="max-results" class="input" value="10" max="100" ${disableScrape}>
                    </div>
                    <button type="button" class="btn" onclick="submitSourceScrape()" ${disableScrape}>Scan Selected Sources</button>
                </form>
            </div>
        </div>

        <div class="card mt-4">
            <h2>Recent Activity</h2>
            ${runsHtml}
        </div>
    `;
}

// Handling Submits
window.submitUrlScrape = async () => {
    const url = document.getElementById('url-input').value;
    if (!url) return;
    try {
        const body = { url };
        if (currentUser) {
            body.user_id = currentUser.id;
            body.user_name = currentUser.user_metadata?.full_name || currentUser.email;
        }

        const res = await fetchApi('/scrape/url', {
            method: 'POST',
            body: JSON.stringify(body)
        });
        window.location.hash = `#run/${res.run_id}`;
    } catch (e) { }
}

window.submitSourceScrape = async () => {
    const checkboxes = document.querySelectorAll('input[name="source"]:checked');
    const sources = Array.from(checkboxes).map(cb => cb.value);
    const maxResults = parseInt(document.getElementById('max-results').value || '10', 10);

    if (sources.length === 0) return alert("Select at least one source.");

    try {
        const body = { sources, max_results: maxResults };
        if (currentUser) {
            body.user_id = currentUser.id;
            body.user_name = currentUser.user_metadata?.full_name || currentUser.email;
        }

        const res = await fetchApi('/scrape/sources', {
            method: 'POST',
            body: JSON.stringify(body)
        });
        window.location.hash = `#run/${res.run_id}`;
    } catch (e) { }
}

// 2. RUN DETAIL VIEW
let currentPollInterval = null;

async function renderRunDetail(container, runId) {
    // Clear any previous polling
    if (currentPollInterval) clearInterval(currentPollInterval);

    try {
        const run = await fetchApi(`/run/${runId}`);
        const docs = await fetchApi(`/run/${runId}/documents`);

        let headerAlert = '';
        if (run.status === 'pending') {
            headerAlert = `<div class="alert warning">${icons.alert} <strong>Job in Queue.</strong> Position #${run.queue_position}... This page will automatically refresh.</div>`;
        } else if (run.status === 'running') {
            headerAlert = `<div class="alert">${icons.search} <strong>Job Running...</strong> Analyzing documents. This page will automatically refresh.</div>`;
        } else if (run.status === 'failed') {
            headerAlert = `<div class="alert" style="background-color: #f8d7da; color: #721c24;">${icons.alert} <strong>Job Failed.</strong> ${run.error_message || ''}</div>`;
        }

        let isCompleted = run.status === 'completed' || run.status === 'failed';

        // Render
        container.innerHTML = `
            ${headerAlert}
            <div class="flex-row justify-between mb-4">
                <div class="flex-row">
                    <a href="#home" class="btn btn-secondary">← Back</a>
                    <h1>Run #${run.id} Details</h1>
                    <span class="badge ${run.status}">${run.status}</span>
                </div>
                ${!isCompleted ? `<button class="btn btn-secondary" onclick="cancelRun(${run.id})" style="color:var(--danger-color); border-color:var(--danger-color)">Cancel Run</button>` : ''}
            </div>

            <div class="grid-auto mb-4">
                <div class="stat-card">
                    <span class="stat-label">Total Documents</span>
                    <span class="stat-value">${run.total_documents}</span>
                </div>
                <div class="stat-card">
                    <span class="stat-label">AI Systems Found</span>
                    <span class="stat-value" style="color:var(--danger-color)">${run.evil_found}</span>
                </div>
                <div class="stat-card">
                    <span class="stat-label">Avg Confidence</span>
                    <span class="stat-value">${Math.round(run.avg_confidence * 100)}%</span>
                </div>
            </div>
            
            <div class="card">
                <h2>Analysis Findings</h2>
                ${docs.length === 0 ? `<div class="empty-state">No documents matched yet.</div>` : `
                    <table>
                        <thead>
                            <tr>
                                <th>Source</th>
                                <th>Title / Link</th>
                                <th>Highest Confidence</th>
                                <th>Classifications</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${docs.map(d => `
                                <tr>
                                    <td><span class="badge" style="background:#eee">${d.source_name || d.url.split('/')[2]}</span></td>
                                    <td>
                                        <div style="font-weight: 500; margin-bottom:4px; max-width:400px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="${d.title}">${d.title || 'Untitled'}</div>
                                        <a href="${d.url}" target="_blank" class="text-secondary" style="text-decoration:none;font-size:0.8rem; display:flex; align-items:center; gap:4px">${icons.link} View Original</a>
                                    </td>
                                    <td>
                                        <div style="font-weight:600; color: ${d.max_confidence >= 0.7 ? 'var(--danger-color)' : (d.max_confidence >= 0.4 ? '#f59e0b' : 'inherit')}">
                                            ${Math.round(d.max_confidence * 100)}%
                                        </div>
                                    </td>
                                    <td>
                                        <div class="flex-col">
                                            ${d.classifications.map(c => `
                                                <div style="background:var(--bg-color); padding: 8px; border-radius: 6px; font-size:0.85rem;">
                                                    <strong>${c.ai_system_name || 'Unnamed Model'}</strong>: ${c.category_name} 
                                                    (<span class="badge ${c.status}" style="font-size:0.65rem;">${c.status}</span>)
                                                </div>
                                            `).join('')}
                                        </div>
                                    </td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                `}
            </div>
        `;

        if (!isCompleted) {
            currentPollInterval = setTimeout(() => renderRunDetail(container, runId), 3000);
        }

    } catch (e) {
        container.innerHTML = `<div class="empty-state" style="color:var(--danger-color)">Error loading run details: ${e.message}</div>
        <a href="#home" class="btn btn-secondary mt-4">Go Home</a>`;
    }
}

window.cancelRun = async (runId) => {
    try {
        await fetchApi(`/run/${runId}/cancel`, { method: 'POST' });
        router(); // Refresh view
    } catch (e) { }
}

// 3. LEADERBOARD VIEW
async function renderLeaderboard(container) {
    try {
        const board = await fetchApi('/leaderboard');

        container.innerHTML = `
            <div class="flex-row mb-4">
                <a href="#home" class="btn btn-secondary">← Back</a>
                <h1>Global Leaderboard</h1>
            </div>

            <div class="card">
                <p class="text-secondary mb-4">Ranking the top contributors uncovering risky AI deployments.</p>
                ${board.length === 0 ? `<div class="empty-state">No contributions yet. Be the first to analyze AI risks!</div>` : `
                    <table>
                        <thead>
                            <tr>
                                <th style="width: 50px;">Rank</th>
                                <th>Contributor</th>
                                <th style="text-align: right;">Total AI Systems Identified</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${board.map((u, i) => `
                                <tr>
                                    <td><span style="font-size: 1.2rem; font-weight:700; color: ${i === 0 ? '#ffd700' : (i === 1 ? '#c0c0c0' : (i === 2 ? '#cd7f32' : 'inherit'))}">#${i + 1}</span></td>
                                    <td style="font-weight: 500;">
                                        ${u.user_name 
                                            ? `${u.user_name} <br><span style="font-size: 0.8rem; font-family: monospace; font-weight:normal;" class="text-secondary">${u.user_id}</span>` 
                                            : `Anonymous Contributor <br><span style="font-size: 0.8rem; font-family: monospace; font-weight:normal;" class="text-secondary">${u.user_id}</span>`
                                        }
                                    </td>
                                    <td style="text-align: right; font-weight:600; color:var(--danger-color); font-size: 1.2rem;">${u.total_evil_found}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                `}
            </div>
        `;
    } catch (e) {
        container.innerHTML = `<div class="empty-state" style="color:var(--danger-color)">Error loading leaderboard: ${e.message}</div>`;
    }
}

// Init
initAuth().then(router);
