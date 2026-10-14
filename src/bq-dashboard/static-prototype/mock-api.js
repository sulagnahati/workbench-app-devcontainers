/* Sample-data stand-in for the dashboard server, used by the static prototype build.
 *
 * The real dashboards ask a Flask server (which queries BigQuery) for every number. A static host has no
 * server, so this file answers the same "api/..." requests in the browser with MADE-UP numbers that are
 * generated deterministically. Nothing here comes from production data. A banner on every page says so.
 */
(function () {
    'use strict';
    const CONFIGS = /*__CONFIGS__*/ {};

    // ---- deterministic random numbers ---------------------------------------------------------
    function hash(str) {
        let h = 2166136261;
        for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); }
        return h >>> 0;
    }
    function rng(seed) {
        let a = typeof seed === 'string' ? hash(seed) : seed;
        return function () {
            a |= 0; a = (a + 0x6D2B79F5) | 0;
            let t = Math.imul(a ^ (a >>> 15), 1 | a);
            t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
            return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
        };
    }
    const round = Math.round;
    const iso = d => d.toISOString().slice(0, 10);
    function mondayOf(d) { const x = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate())); const dow = (x.getUTCDay() + 6) % 7; x.setUTCDate(x.getUTCDate() - dow); return x; }
    const TODAY = (() => { const n = new Date(); return new Date(Date.UTC(n.getFullYear(), n.getMonth(), n.getDate())); })();
    const addDays = (d, n) => new Date(d.getTime() + n * 86400000);

    // ---- shared sample world --------------------------------------------------------------------
    const STATES = {
        Alabama: [32.8, -86.8], Alaska: [61.2, -149.9], Arizona: [34.3, -111.7], Arkansas: [34.9, -92.4], California: [36.8, -119.7],
        Colorado: [39.0, -105.5], Connecticut: [41.6, -72.7], Florida: [28.6, -82.4], Georgia: [32.7, -83.4], Hawaii: [21.3, -157.9],
        Idaho: [44.4, -114.6], Illinois: [40.0, -89.2], Indiana: [39.9, -86.3], Iowa: [42.0, -93.5], Kansas: [38.5, -98.4],
        Kentucky: [37.5, -85.3], Louisiana: [31.1, -92.0], Maine: [45.3, -69.2], Maryland: [39.0, -76.8], Massachusetts: [42.3, -71.8],
        Michigan: [44.3, -85.4], Minnesota: [46.3, -94.3], Mississippi: [32.7, -89.7], Missouri: [38.4, -92.5], Montana: [47.0, -109.6],
        Nebraska: [41.5, -99.8], Nevada: [39.3, -116.6], 'New Hampshire': [43.7, -71.6], 'New Jersey': [40.2, -74.7], 'New Mexico': [34.4, -106.1],
        'New York': [42.9, -75.5], 'North Carolina': [35.6, -79.4], Ohio: [40.3, -82.8], Oklahoma: [35.6, -97.5], Oregon: [44.1, -120.5],
        Pennsylvania: [40.9, -77.8], 'South Carolina': [33.9, -80.9], Tennessee: [35.8, -86.4], Texas: [31.5, -99.3], Utah: [39.3, -111.7],
        Virginia: [37.5, -78.8], Washington: [47.4, -120.6], Wisconsin: [44.6, -89.8],
    };
    const STATE_NAMES = Object.keys(STATES);
    const PLANTS = (() => {
        const out = [];
        STATE_NAMES.forEach(st => {
            const r = rng('plants:' + st);
            const n = 1 + Math.floor(r() * 5);
            for (let k = 1; k <= n; k++) {
                out.push({
                    name: `Sample plant ${out.length + 1}, ${st}`, state: st,
                    lat: STATES[st][0] + (r() - 0.5) * 3, lon: STATES[st][1] + (r() - 0.5) * 4,
                    population: round(Math.exp(10 + r() * 4.2)), factor: 0.4 + r() * 1.4,
                });
            }
        });
        return out;
    })();
    const STATE_FACTOR = Object.fromEntries(STATE_NAMES.map(s => [s, 0.5 + rng('sf:' + s)() * 1.2]));

    // ---- parse a request ------------------------------------------------------------------------
    function parse(url) {
        const u = new URL(url, 'http://sample.local/');
        return { path: u.pathname.replace(/^\//, ''), q: u.searchParams, all: k => u.searchParams.getAll(k) };
    }
    const sleep = ms => new Promise(r => setTimeout(r, ms));
    function respond(body, status) {
        return new Response(JSON.stringify(body), { status: status || 200, headers: { 'Content-Type': 'application/json' } });
    }
    const SAMPLE_SQL = '-- Sample data: no query runs in this prototype. The real dashboard shows the SQL generated from the definitions here.';

    // =============================================================================================
    // Member overview
    // =============================================================================================
    const TOTAL = 250000;
    const OV = {
        organization: { names: ['Sample Org A', 'Sample Org B', 'Sample Org C', 'Sample Org D', 'Sample Org E'], w: [0.45, 0.35, 0.12, 0.06, 0.02], active: [0.99, 0.995, 0.98, 0.97, 0.6] },
        care_program: { names: ['Program One', 'Program Two', 'Program Three'], w: [0.7, 0.2, 0.1], active: [0.99, 0.98, 0.95] },
        age_band: { names: ['Under 18', '18-29', '30-39', '40-49', '50-59', '60-69', '70+', 'Unknown'], w: [0.03, 0.18, 0.22, 0.21, 0.17, 0.12, 0.05, 0.02], active: [0.97, 0.98, 0.99, 0.99, 0.99, 0.98, 0.97, 0.9] },
        birth_sex: { names: ['F', 'M', 'UNK'], w: [0.58, 0.4, 0.02], active: [0.99, 0.985, 0.9] },
        account_status: { names: ['active', 'closed'], w: [0.97, 0.03], active: [1, 0] },
        language: { names: ['en', 'es'], w: [0.9, 0.1], active: [0.99, 0.97] },
        cohort: { names: ['None', 'Cardiometabolic'], w: [0.85, 0.15], active: [0.985, 0.995] },
    };
    (() => {
        const r = rng('ov-state');
        const raw = STATE_NAMES.map(() => 0.2 + r() * r() * 2);
        const s = raw.reduce((a, b) => a + b, 0);
        OV.state = { names: STATE_NAMES, w: raw.map(x => x / s), active: STATE_NAMES.map(n => 0.95 + rng('oa' + n)() * 0.045) };
    })();
    const MONTHS = (() => {
        const out = [];
        for (let i = 26; i >= 0; i--) { const d = new Date(Date.UTC(TODAY.getUTCFullYear(), TODAY.getUTCMonth() - i, 1)); out.push(iso(d)); }
        return out;
    })();
    const MONTH_W = (() => {
        const raw = MONTHS.map((_, i) => 0.01 + Math.exp(-Math.pow((i - 20) / 4.5, 2)) + 0.15 * Math.exp(-Math.pow((i - 24) / 3, 2)));
        const s = raw.reduce((a, b) => a + b, 0);
        return raw.map(x => x / s);
    })();

    function ovScope(filters) {
        let f = 1;
        const fixed = {};
        filters.forEach(([dim, value]) => {
            const d = OV[dim];
            if (!d) return;
            const i = d.names.indexOf(value);
            f *= i >= 0 ? d.w[i] : 0.05;
            fixed[dim] = value;
        });
        return { total: TOTAL * f, fixed };
    }
    function ovActiveRate(filters) {
        let a = 0, w = 0;
        filters.forEach(([dim, value]) => { const d = OV[dim]; if (d) { const i = d.names.indexOf(value); if (i >= 0) { a += d.active[i]; w++; } } });
        return w ? a / w : 0.992;
    }
    function ovKpis(filters) {
        const sc = ovScope(filters);
        const total = round(sc.total);
        if (total < 11) return { values: { total_members: null, active_members: null, active_share: null }, suppressed: true, sql: SAMPLE_SQL };
        const share = Math.min(1, ovActiveRate(filters));
        return { values: { total_members: total, active_members: round(total * share), active_share: share }, suppressed: false, sql: SAMPLE_SQL };
    }
    function ovGrouped(dim, measures, filters) {
        const sc = ovScope(filters);
        const key = filters.map(x => x.join('=')).join('&');
        if (dim === 'signup_month') {
            const rows = MONTHS.map((m, i) => {
                const n = round(sc.total * MONTH_W[i]);
                const act = round(n * (i > 22 ? 0.99 : 0.97 + 0.02 * rng('am' + i + key)()));
                return { d: m, total_members: n, active_members: Math.min(n, act), active_share: n ? Math.min(1, act / n) : null };
            }).filter(r => r.total_members >= 11);
            return { rows, sql: SAMPLE_SQL };
        }
        const d = OV[dim];
        if (!d) return null;
        // groups are scaled to add up to the total shown on the cards
        const raw = d.names.map((name, i) => sc.fixed[dim] ? (name === sc.fixed[dim] ? 1 : 0) : d.w[i] * (0.9 + 0.2 * rng('g' + dim + name + key)()));
        const rawSum = raw.reduce((a, b) => a + b, 0) || 1;
        let rows = d.names.map((name, i) => {
            const n = round(sc.total * raw[i] / rawSum);
            const share = Math.min(1, d.active[i] * (0.995 + 0.01 * rng('s' + dim + name + key)()));
            return { d: name, total_members: n, active_members: round(n * share), active_share: share };
        }).filter(r => r.total_members >= 11);
        rows.sort((a, b) => b[measures[0]] - a[measures[0]]);
        rows = rows.slice(0, 60);
        return { rows, sql: SAMPLE_SQL };
    }

    // =============================================================================================
    // Wastewater (sightline)
    // =============================================================================================
    const PATHOGENS = ['SARS-CoV-2', 'Norovirus GII', 'RSV', 'Hepatitis A', 'Influenza B', 'Candida auris', 'Human metapneumovirus', 'Enterovirus D68',
        'InfA_H5', 'Influenza A', 'Mpox virus', 'InfA_H1', 'MPXV Clade Ib', 'InfA_H3', 'Rotavirus', 'Adenovirus 40/41', 'Measles', 'Parvovirus B19', 'West Nile Virus'];
    const RARE = new Set(['Mpox virus', 'MPXV Clade Ib', 'Measles', 'West Nile Virus', 'Candida auris', 'InfA_H5']);
    const LINEAGES = ['XFG', 'NB.1.8.1', 'LF.7', 'BA.3.2', 'JN.1', 'BA.2.86', 'JN.1.16', 'KP.3', 'XBB', 'KP.2', 'Other'];
    const PRESET_MONTHS = { '3m': 3, '6m': 6, '12m': 12, '24m': 24 };

    function weeksFor(preset) {
        const months = PRESET_MONTHS[preset] || 12;
        const end = mondayOf(addDays(TODAY, -7));
        const n = Math.round(months * 4.35);
        const out = [];
        for (let i = n - 1; i >= 0; i--) out.push(addDays(end, -7 * i));
        return out;
    }
    function plantsIn(state, plant) {
        return PLANTS.filter(p => (!state || p.state === state) && (!plant || p.name === plant));
    }
    function level(pathogen, week, scopeFactor, salt) {
        const r = rng(`lv:${pathogen}:${iso(week)}:${salt}`);
        const pr = rng('pp:' + pathogen);
        const base = 0.00002 + pr() * 0.00008;
        const phase = pr() * Math.PI * 2;
        const amp = 0.5 + pr() * 0.45;
        const doy = (week.getTime() / 86400000) % 365.25;
        const season = 1 + amp * Math.sin(2 * Math.PI * doy / 365.25 + phase);
        let v = base * season * scopeFactor * (0.8 + 0.4 * r());
        if (RARE.has(pathogen) && r() < 0.8) v = 0;
        return v;
    }
    function scopeFactorFor(state, plant) {
        const ps = plantsIn(state, plant);
        if (!ps.length) return 0;
        return ps.reduce((a, p) => a + p.factor * STATE_FACTOR[p.state], 0) / ps.length;
    }
    function slKpis(a) {
        const ps = plantsIn(a.state, a.plant);
        const weeks = weeksFor(a.preset);
        const samples = round(ps.length * weeks.length * (2.2 + rng('k' + a.pathogen)()));
        return { row: { plants: ps.length, samples, latest: iso(addDays(TODAY, -4)) }, sql: SAMPLE_SQL };
    }
    function slTrend(a) {
        const weeks = weeksFor(a.preset);
        const f = scopeFactorFor(a.state, a.plant);
        const n = plantsIn(a.state, a.plant).length;
        return { rows: weeks.map(w => ({ d: iso(w), level: level(a.pathogen, w, f, a.state + a.plant), samples: round(n * 2.5) })), sql: SAMPLE_SQL };
    }
    function slRanking(a) {
        const weeks = weeksFor(a.preset).slice(-8);
        let rows;
        if (a.state) {
            rows = plantsIn(a.state).map(p => ({ d: p.name, level: weeks.reduce((s, w) => s + level(a.pathogen, w, p.factor * STATE_FACTOR[p.state], p.name), 0) / weeks.length, plants: 1, samples: 40 }));
        } else {
            rows = STATE_NAMES.filter(st => plantsIn(st).length).map(st => {
                const n = plantsIn(st).length;
                return { d: st, level: weeks.reduce((s, w) => s + level(a.pathogen, w, scopeFactorFor(st), st), 0) / weeks.length, plants: n, samples: n * 45 };
            });
        }
        rows = rows.filter(r => r.level > 0).sort((x, y) => y.level - x.level).slice(0, 40);
        return { rows, by: a.state ? 'plant' : 'state', sql: SAMPLE_SQL };
    }
    function slPlants(a) {
        const weeks = weeksFor(a.preset).slice(-8);
        const rows = plantsIn(a.state).map(p => ({
            name: p.name, state: p.state, lat: p.lat, lon: p.lon, population: p.population,
            level: weeks.reduce((s, w) => s + level(a.pathogen, w, p.factor * STATE_FACTOR[p.state], p.name), 0) / weeks.length, samples: 40,
        }));
        return { rows, sql: SAMPLE_SQL };
    }
    function slVariants(a) {
        const weeks = weeksFor(a.preset);
        const shift = (a.state || a.plant) ? (hash(a.state + a.plant) % 7) - 3 : 0;
        const noise = (a.state || a.plant) ? 0.12 : 0.05;
        const rows = [];
        const total = weeks.length;
        weeks.forEach((w, wi) => {
            const raw = LINEAGES.map((l, li) => {
                const center = total * (0.04 + 0.085 * li) + shift * 2;   // index 0 is the newest lineage, so it peaks most recently
                const width = total * 0.22;
                const wave = Math.exp(-Math.pow(((total - wi) - center) / width, 2));
                const base = li === LINEAGES.length - 1 ? 0.06 : 0.01;
                return Math.max(0.0005, wave + base + noise * rng(`vr:${l}:${wi}:${a.state}${a.plant}`)());
            });
            const s = raw.reduce((x, y) => x + y, 0);
            LINEAGES.forEach((l, li) => rows.push({ d: iso(w), lineage: l, share: raw[li] / s }));
        });
        return { rows, sql: SAMPLE_SQL };
    }

    // =============================================================================================
    // Lifelong funnel
    // =============================================================================================
    const LL_ORGS = ['Sample Base Org', 'Sample Lifelong Org', 'Sample Other Org', 'Sample Prerelease Org', 'Sample Internal Org'];
    const LL_STATUS = { active: 0.94, closed: 0.05, 'partially-closed': 0.01 };
    const LL_COHORT = { Cardiometabolic: 0.2, None: 0.8 };
    const DAYS = 330;
    const DAILY = (() => {
        const out = [];
        for (let i = DAYS - 1; i >= 0; i--) {
            const d = addDays(TODAY, -i);
            const r = rng('ll:' + iso(d));
            const trend = 0.4 + 1.1 * (1 - i / DAYS);
            out.push({ date: d, v: Math.max(0, (4 + 8 * r() * trend + (i === 20 ? 120 : 0))) });
        }
        return out;
    })();
    const DAILY_SUM = DAILY.reduce((a, d) => a + d.v, 0);
    const BASE = { interested: 3200, deferred: 900, eligible: 40000, consentEligible: 3000, signed: 1700, declined: 440, proposed: 280, draft: 700, revoked: 12 };

    function splitList(text) {
        const out = []; let cur = '', quoted = false;
        for (const ch of (text || '')) {
            if (ch === '"') quoted = !quoted; else if (ch === ',' && !quoted) { out.push(cur.trim()); cur = ''; } else cur += ch;
        }
        out.push(cur.trim());
        return out.filter(Boolean);
    }
    function dateCutoff(expr, dflt) {
        const e = (expr === undefined ? dflt : expr).trim();
        if (!e) return addDays(TODAY, -DAYS);
        let m = e.match(/^after (\d{4})\/(\d{2})\/(\d{2})$/);
        if (m) return new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
        m = e.match(/^(\d+) days?$/);
        if (m) return addDays(TODAY, -(+m[1]));
        return addDays(TODAY, -DAYS);
    }
    function llScope(f) {
        const orgs = splitList(f['Organization Name']);
        const baseOn = !orgs.length || orgs.includes('Sample Base Org');
        const lifeOn = !orgs.length || orgs.includes('Sample Lifelong Org');
        const otherOn = orgs.length ? orgs.filter(o => !['Sample Base Org', 'Sample Lifelong Org'].includes(o)).length : 3;
        const st = splitList(f['Account Status']);
        const statusF = st.length ? st.reduce((a, s) => a + (LL_STATUS[s] || 0), 0) : 1;
        const co = splitList(f['Cohort Eligibility']);
        const cohortF = co.length ? co.reduce((a, s) => a + (LL_COHORT[s] || 0), 0) : 1;
        const cutoff = dateCutoff(f['Date Filter (After 8/04/2025 Only)'], 'after 2025/10/17');
        const dflt = dateCutoff('after 2025/10/17', '');
        const frac = DAILY.filter(d => d.date >= cutoff).reduce((a, d) => a + d.v, 0) / DAILY_SUM;
        const fracDefault = DAILY.filter(d => d.date >= dflt).reduce((a, d) => a + d.v, 0) / DAILY_SUM;
        const common = statusF * cohortF * (frac / fracDefault);
        return { interest: (baseOn ? 1 : 0.02 * otherOn) * common, consent: (lifeOn ? 1 : 0.0) * common, cutoff };
    }
    function bucket(date, grain) {
        if (grain === 'week') return iso(mondayOf(date));
        if (grain === 'month') return iso(new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), 1)));
        if (grain === 'quarter') return iso(new Date(Date.UTC(date.getUTCFullYear(), Math.floor(date.getUTCMonth() / 3) * 3, 1)));
        return iso(date);
    }
    function llLine(title, f, scale, total) {
        const sc = llScope(f);
        const grain = f['Time Series Grain Toggle'] || 'date';
        const acc = new Map();
        DAILY.filter(d => d.date >= sc.cutoff).forEach(d => { const k = bucket(d.date, grain); acc.set(k, (acc.get(k) || 0) + d.v); });
        const sum = [...acc.values()].reduce((a, b) => a + b, 0) || 1;
        const k = (total * scale) / sum;
        return { type: 'line', label: title.includes('Consented') ? 'Signed consents' : 'Interested', points: [...acc.entries()].sort().map(([x, y]) => ({ x, y: round(y * k) })), sql: SAMPLE_SQL };
    }
    function llTile(id, filters) {
        const tile = CONFIGS.lifelong.tiles[id];
        if (!tile) return null;
        const sc = llScope(filters);
        const I = sc.interest, C = sc.consent;
        const interested = round(BASE.interested * I), deferred = round(BASE.deferred * I), eligible = round(BASE.eligible * I);
        const nonresp = Math.max(0, eligible - interested - deferred);
        const signed = round(BASE.signed * C), declined = round(BASE.declined * C), proposed = round(BASE.proposed * C), draft = round(BASE.draft * C);
        const single = {
            'Total Lifelong Eligible': eligible, 'Lifelong Interest Completion': interested, 'Interest Deferred': deferred,
            'Lifelong Non-Responders': nonresp, 'Total Consent Eligible': round(BASE.consentEligible * C), 'Lifelong Consent Completion': signed,
            'Lifelong Consent Declined': declined, 'Lifelong Consent Proposed': proposed, 'Lifelong Consent Draft': draft, 'Lifelong Consent Revoked': round(BASE.revoked * C),
        };
        const t = tile.title;
        if (t in single) return { type: 'single_value', label: t, value: single[t], sql: SAMPLE_SQL };
        if (t === 'Lifelong Interest Rates') return { type: 'donut', slices: [{ label: 'Count Lifelong Interested', value: interested }, { label: 'Count Lifelong Interest Deferred', value: deferred }, { label: 'Count Lifelong Nonresponders', value: nonresp }], sql: SAMPLE_SQL };
        if (t === 'Lifelong Consent Rates') return { type: 'donut', slices: [{ label: 'Count Lifelong Signed Consents', value: signed }, { label: 'Count Lifelong Declined Consents', value: declined }, { label: 'Count Lifelong Consent Incomplete', value: proposed + draft }], sql: SAMPLE_SQL };
        if (t === 'Lifelong Interest Over Time') return llLine(t, filters, 1, interested);
        if (t === 'Lifelong Consented Over Time') return llLine(t, filters, 1, signed);
        return null;
    }
    const LL_VALUES = {
        organization_compartment_name: LL_ORGS, verily_me_account_status: Object.keys(LL_STATUS), cohort_eligibility: Object.keys(LL_COHORT),
    };

    // =============================================================================================
    // routing
    // =============================================================================================
    function route(url) {
        const p = parse(url);
        const q = k => p.q.get(k) || '';
        const filters = p.all('filter').map(s => { const i = s.indexOf(':'); return [s.slice(0, i), s.slice(i + 1)]; });
        switch (p.path) {
            case 'api/overview/config': return CONFIGS.overview;
            case 'api/overview/kpis': return ovKpis(filters);
            case 'api/overview/grouped': return ovGrouped(q('dimension'), q('measures').split(','), filters);
            case 'api/sightline/config': return CONFIGS.sightline;
        }
        const a = { preset: q('preset') || '12m', pathogen: q('pathogen'), state: q('state'), plant: q('plant') };
        switch (p.path) {
            case 'api/sightline/values': return q('kind') === 'pathogen' ? PATHOGENS : q('kind') === 'state' ? STATE_NAMES.slice() : null;
            case 'api/sightline/kpis': return slKpis(a);
            case 'api/sightline/trend': return a.pathogen ? slTrend(a) : null;
            case 'api/sightline/ranking': return a.pathogen ? slRanking(a) : null;
            case 'api/sightline/plants': return a.pathogen ? slPlants(a) : null;
            case 'api/sightline/variants': return slVariants(a);
            case 'api/lifelong/config': return CONFIGS.lifelong;
            case 'api/lifelong/values': return LL_VALUES[q('field').split('.')[1]] || null;
            case 'api/lifelong/tile': return llTile(+q('id'), JSON.parse(q('filters') || '{}'));
        }
        return null;
    }

    const realFetch = window.fetch.bind(window);
    window.fetch = function (url, opts) {
        const u = String(url);
        if (!u.startsWith('api/')) return realFetch(url, opts);
        return sleep(120 + Math.random() * 280).then(() => {
            let body = null;
            try { body = route(u); } catch (e) { return respond({ error: String(e) }, 500); }
            return body === null ? respond({ error: 'Not available in the sample prototype' }, 404) : respond(body);
        });
    };

    // ---- banner: this is sample data -----------------------------------------------------------------
    window.addEventListener('DOMContentLoaded', () => {
        const bar = document.createElement('div');
        bar.setAttribute('role', 'note');
        bar.style.cssText = 'background:#d7e491;color:#122d28;text-align:center;font:600 13px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;padding:7px 12px;letter-spacing:.01em';
        bar.textContent = 'SAMPLE DATA: this prototype shows made-up numbers to demonstrate the design and interactions. It is not connected to real data.';
        document.body.insertBefore(bar, document.body.firstChild);
        document.title = 'Sample: ' + document.title;
    });
})();
