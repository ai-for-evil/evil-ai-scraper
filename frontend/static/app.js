/**
 * Evil AI Scraper v2 — Frontend JavaScript
 */

document.addEventListener('DOMContentLoaded', () => {
    initURLForm();
    initSourceForm();
    initRunDetailFindings();
});

// ===== Toast Notifications =====
function showToast(message, type = 'info') {
    const toast = document.getElementById('status-toast');
    const toastMsg = document.getElementById('toast-message');
    if (!toast || !toastMsg) return;

    toastMsg.textContent = message;
    toast.className = `toast toast-${type}`;
    toast.classList.remove('hidden');

    setTimeout(() => {
        toast.classList.add('hidden');
    }, 5000);
}

// ===== URL Scrape Form =====
function initURLForm() {
    const form = document.getElementById('url-form');
    if (!form) return;

    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        const urlInput = document.getElementById('url-input');
        const submitBtn = document.getElementById('url-submit');
        const btnText = submitBtn.querySelector('.btn-text');
        const btnLoader = submitBtn.querySelector('.btn-loader');
        const url = urlInput.value.trim();

        if (!url) return;

        const reviewerInput = document.getElementById('reviewer-name');
        const reviewer_name = reviewerInput ? reviewerInput.value.trim() : '';
        if (!reviewer_name) {
            showToast('Please enter your reviewer name first', 'error');
            if (reviewerInput) reviewerInput.focus();
            return;
        }

        submitBtn.disabled = true;
        btnText.classList.add('hidden');
        btnLoader.classList.remove('hidden');

        try {
            const resp = await fetch('/api/scrape/url', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url, reviewer_name }),
            });

            const data = await resp.json();

            if (resp.ok) {
                window.location.href = `/run/${data.run_id}`;
                return;
            } else {
                showToast(`❌ ${data.error || 'Failed to start scrape'}`, 'error');
            }
        } catch (err) {
            showToast(`❌ Network error: ${err.message}`, 'error');
        } finally {
            submitBtn.disabled = false;
            btnText.classList.remove('hidden');
            btnLoader.classList.add('hidden');
        }
    });
}

// ===== Source Scrape Form =====
function initSourceForm() {
    const form = document.getElementById('source-form');
    if (!form) return;

    const manifestCb = document.getElementById('source-manifest');
    const manifestOpts = document.getElementById('manifest-options');
    if (manifestCb && manifestOpts) {
        const syncManifestUi = () => {
            manifestOpts.classList.toggle('hidden', !manifestCb.checked);
        };
        manifestCb.addEventListener('change', syncManifestUi);
        syncManifestUi();
    }

    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        const checkboxes = form.querySelectorAll('input[name="sources"]:checked');
        const sources = Array.from(checkboxes).map(cb => cb.value);

        if (manifestCb && manifestCb.checked) {
            const presetEl = document.getElementById('manifest-preset');
            const preset = presetEl ? presetEl.value : 'high_yield';
            sources.push(`manifest:${preset}`);
        }

        if (sources.length === 0) {
            showToast('Please select at least one source', 'error');
            return;
        }

        const reviewerInput = document.getElementById('reviewer-name');
        const reviewer_name = reviewerInput ? reviewerInput.value.trim() : '';
        if (!reviewer_name) {
            showToast('Please enter your reviewer name first', 'error');
            if (reviewerInput) reviewerInput.focus();
            return;
        }

        const maxResultsInput = document.getElementById('max-results-input');
        const max_results = maxResultsInput ? parseInt(maxResultsInput.value, 10) : 60;
        const manifest_fresh = document.getElementById('manifest-fresh')?.checked || false;

        const submitBtn = document.getElementById('source-submit');
        const btnText = submitBtn.querySelector('.btn-text');
        const btnLoader = submitBtn.querySelector('.btn-loader');

        submitBtn.disabled = true;
        btnText.classList.add('hidden');
        btnLoader.classList.remove('hidden');

        try {
            const resp = await fetch('/api/scrape/sources', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ sources, reviewer_name, max_results, manifest_fresh }),
            });

            const data = await resp.json();

            if (resp.ok) {
                window.location.href = `/run/${data.run_id}`;
                return;
            } else {
                showToast(`❌ ${data.error || 'Failed to start scrape'}`, 'error');
            }
        } catch (err) {
            showToast(`❌ Network error: ${err.message}`, 'error');
        } finally {
            submitBtn.disabled = false;
            btnText.classList.remove('hidden');
            btnLoader.classList.add('hidden');
        }
    });
}

// ===== Run detail — findings search, filters, sort =====
function initRunDetailFindings() {
    const list = document.getElementById('findings-list');
    if (!list) return;

    const cards = Array.from(list.querySelectorAll('.finding-card'));
    if (cards.length === 0) return;

    const searchInput = document.getElementById('findings-search');
    const statusFilter = document.getElementById('findings-filter-status');
    const sourceFilter = document.getElementById('findings-filter-source');
    const categoryFilter = document.getElementById('findings-filter-category');
    const cocFilter = document.getElementById('findings-filter-coc');
    const repoFilter = document.getElementById('findings-filter-repo');
    const sortSelect = document.getElementById('findings-sort');
    const countEl = document.getElementById('findings-count');
    const emptyFiltered = document.getElementById('findings-empty-filtered');

    function numMaxConf(el) {
        const v = Number(el.dataset.maxConfidence);
        return Number.isFinite(v) ? v : -1;
    }

    function apply() {
        const q = (searchInput && searchInput.value ? searchInput.value : '').trim().toLowerCase();
        const st = (statusFilter && statusFilter.value) || 'all';
        const src = (sourceFilter && sourceFilter.value) || 'all';
        const cat = (categoryFilter && categoryFilter.value) || 'all';
        const coc = (cocFilter && cocFilter.value) || 'all';
        const repo = (repoFilter && repoFilter.value) || 'all';

        const visible = [];
        cards.forEach((card) => {
            const blob = (card.dataset.searchBlob || '').toLowerCase();
            const statuses = (card.dataset.statusTags || '').split(',').map(s => s.trim()).filter(Boolean);
            const source = card.dataset.source || '';
            const categories = (card.dataset.categories || '').split('|||').filter(Boolean);
            const cocVals = (card.dataset.coc || '').split('|||').filter(Boolean);
            const repoVals = (card.dataset.repo || '').split('|||').filter(Boolean);

            let show = true;
            if (q && !blob.includes(q)) show = false;
            if (show && st !== 'all' && !statuses.includes(st)) show = false;
            if (show && src !== 'all' && source !== src) show = false;
            if (show && cat !== 'all' && !categories.includes(cat)) show = false;
            if (show && coc !== 'all' && !cocVals.includes(coc)) show = false;
            if (show && repo !== 'all' && !repoVals.includes(repo)) show = false;

            card.style.display = show ? '' : 'none';
            if (show) visible.push(card);
        });

        const sortVal = (sortSelect && sortSelect.value) || 'conf-desc';
        visible.sort((a, b) => {
            if (sortVal === 'conf-desc') return numMaxConf(b) - numMaxConf(a);
            if (sortVal === 'conf-asc') return numMaxConf(a) - numMaxConf(b);
            if (sortVal === 'title-asc') {
                return (a.dataset.titleSort || '').localeCompare(b.dataset.titleSort || '', undefined, { sensitivity: 'base' });
            }
            if (sortVal === 'cat-asc') {
                return (a.dataset.categories || '').localeCompare(b.dataset.categories || '', undefined, { sensitivity: 'base' });
            }
            return 0;
        });

        const hidden = cards.filter(c => c.style.display === 'none');
        visible.forEach(c => list.appendChild(c));
        hidden.forEach(c => list.appendChild(c));

        if (countEl) countEl.textContent = `Showing ${visible.length} of ${cards.length} finding(s)`;
        if (emptyFiltered) emptyFiltered.classList.toggle('hidden', visible.length > 0);
    }

    [searchInput, statusFilter, sourceFilter, categoryFilter, cocFilter, repoFilter, sortSelect].forEach((el) => {
        if (!el) return;
        el.addEventListener(el.tagName === 'SELECT' ? 'change' : 'input', apply);
    });
    apply();
}

// ===== Poll Run Status =====
function pollRunStatus(runId) {
    const interval = setInterval(async () => {
        try {
            const resp = await fetch(`/api/run/${runId}`);
            const data = await resp.json();

            if (data.status === 'completed') {
                clearInterval(interval);
                showToast(`✅ Run #${runId} completed! Found ${data.evil_found} evil AI(s)`, 'success');
                setTimeout(() => {
                    window.location.href = `/run/${runId}`;
                }, 1500);
            } else if (data.status === 'failed') {
                clearInterval(interval);
                showToast(`❌ Run #${runId} failed: ${data.error_message || 'Unknown error'}`, 'error');
                setTimeout(() => location.reload(), 2000);
            }
        } catch (err) {
            // Silently retry
        }
    }, 3000);

    // Safety timeout — stop polling after 10 minutes
    setTimeout(() => {
        clearInterval(interval);
    }, 600000);
}
