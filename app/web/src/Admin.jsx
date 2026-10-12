import React, { useEffect, useState } from 'react';
import { api, setCsrf } from './api.js';

const TABS = ['Overview', 'Data', 'Testers', 'Settings', 'Capacity', 'Allocation', 'Logs', 'Exports', 'Reset'];
const when = (iso) => (iso ? new Date(iso).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : '—');

function useAction() {
  const [msg, setMsg] = useState(null);
  const run = async (fn, okText) => {
    setMsg(null);
    try {
      const r = await fn();
      if (okText) setMsg({ ok: true, text: okText });
      return r;
    } catch (e) {
      setMsg({ ok: false, text: e.message });
      return null;
    }
  };
  const note = msg && <p className={`note ${msg.ok ? 'good' : 'bad'}`} role="alert">{msg.text}</p>;
  return [run, note];
}

function AdminSignIn({ onDone }) {
  const [secret, setSecret] = useState('');
  const [run, note] = useAction();
  return (
    <main>
      <form className="card" onSubmit={async (e) => {
        e.preventDefault();
        const r = await run(() => api('/api/admin/login', { method: 'POST', body: { secret } }));
        if (r) { setCsrf(r.csrf); onDone(); }
      }}>
        <h2>Admin sign in</h2>
        <label htmlFor="secret">Admin secret</label>
        <input id="secret" type="password" value={secret} onChange={(e) => setSecret(e.target.value)} autoComplete="current-password" required />
        {note}
        <p><button className="primary">Sign in</button></p>
      </form>
    </main>
  );
}

function Stat({ label, value }) { return <div className="stat"><b>{value ?? '—'}</b><span className="small muted">{label}</span></div>; }

function ParseReport({ report }) {
  const c = report.courses; const t = report.timetable;
  return (
    <>
      <div className="stats">
        <Stat label="rows read" value={c.rows} /><Stat label="courses" value={c.courses} /><Stat label="course-slot offerings" value={c.offerings} />
        <Stat label="slot names" value={t.slot_names} /><Stat label="lab slots" value={t.lab_slots} /><Stat label="rows not parsed" value={report.unparsed_rows.length} />
        <Stat label="unknown slot names" value={report.unknown_slot_names.length} /><Stat label="courses without credits" value={c.courses_without_credits} />
      </div>
      <p className="small">Days: {t.days.join(', ')} · By type: {Object.entries(c.by_type).map(([k, v]) => `${k} ${v}`).join(', ')}</p>
      <p className="small"><span className="tag syn">Not in the PDFs</span> {report.not_in_source.join('; ')}</p>
      {(report.unparsed_rows.length > 0 || report.unknown_slot_names.length > 0 || report.credit_notes.length > 0) && (
        <details><summary>Details ({report.unparsed_rows.length + report.unknown_slot_names.length + report.credit_notes.length})</summary>
          <pre>{[...report.unparsed_rows, ...report.unknown_slot_names.map((s) => `unknown slot: ${s}`), ...report.credit_notes].join('\n')}</pre></details>
      )}
    </>
  );
}

function Overview({ o, reload }) {
  const [run, note] = useAction();
  const set = (v) => run(() => api('/api/admin/settings', { method: 'PUT', body: { window_override: v } }), 'Window updated.').then(reload);
  const t = o.timing;
  return (
    <>
      <div className="card">
        <h2>Registration window: {o.window_state}</h2>
        <p className="small">Scheduled {when(o.settings.window_open)} to {when(o.settings.window_close)}.
          {o.settings.window_override ? <> Currently forced <b>{o.settings.window_override}</b>.</> : ' Following the schedule.'}</p>
        <div className="row">
          <button onClick={() => set('open')}>Open now</button>
          <button onClick={() => set('closed')}>Close now</button>
          <button onClick={() => set('')}>Follow the schedule</button>
        </div>
        {note}
      </div>
      <div className="card">
        <h2>Beta so far</h2>
        <div className="stats">
          <Stat label="testers" value={o.counts.testers} /><Stat label="submitted" value={o.counts.submitted} />
          <Stat label="feedback forms" value={o.counts.feedback} /><Stat label="mean SUS score (0–100)" value={o.sus_mean} />
          <Stat label="median minutes to submit" value={t.median_minutes} /><Stat label="mean minutes to submit" value={t.mean_minutes} />
          <Stat label="survey baseline minutes" value={t.baseline_minutes} />
        </div>
        <p className="small muted">Time is measured from a tester’s first step to their first submission ({t.completed} completed).</p>
      </div>
      <div className="card"><h2>Current data</h2><ParseReport report={o.catalogue_report} /></div>
    </>
  );
}

function Data({ reload }) {
  const [report, setReport] = useState(null);
  const [run, note] = useAction();
  async function upload(e) {
    e.preventDefault();
    const form = new FormData(e.target);
    const r = await run(() => api('/api/admin/import', { method: 'POST', form }));
    if (r) setReport(r.report);
  }
  return (
    <div className="card">
      <h2>Re-import course data</h2>
      <p>Upload both Annexure PDFs. You get a parse report first; nothing changes until you confirm.</p>
      <form onSubmit={upload}>
        <label htmlFor="f1">Annexure I (slot timetable)</label><input id="f1" name="timetable" type="file" accept="application/pdf" required />
        <label htmlFor="f2">Annexure II (courses and slots)</label><input id="f2" name="courses" type="file" accept="application/pdf" required />
        <p><button className="primary">Read the PDFs</button></p>
      </form>
      {note}
      {report && (<>
        <h3>Parse report (not applied yet)</h3><ParseReport report={report} />
        <p><button className="primary" onClick={async () => { if (await run(() => api('/api/admin/import/confirm', { method: 'POST' }), 'New data is live.')) { setReport(null); reload(); } }}>Confirm and use this data</button></p>
      </>)}
    </div>
  );
}

function Testers({ tiers }) {
  const [rows, setRows] = useState([]);
  const [csv, setCsv] = useState('');
  const [codes, setCodes] = useState(null);
  const [run, note] = useAction();
  const load = () => api('/api/admin/testers').then(setRows).catch(() => {});
  useEffect(() => { load(); }, []);
  async function importCsv() {
    const r = await run(() => api('/api/admin/testers/import', { method: 'POST', body: { csv } }));
    if (r) { setCodes(r); load(); }
  }
  return (
    <>
      <div className="card">
        <h2>Add or update testers</h2>
        <p className="small">CSV columns: <code>alias, program, year, semester, tier, required_courses, backlog_courses</code>. Use aliases, not registration numbers. Leave <code>required_courses</code> empty to use the curriculum for that program and semester.</p>
        <label htmlFor="csvfile">Choose a CSV file, or paste below</label>
        <input id="csvfile" type="file" accept=".csv,text/csv" onChange={async (e) => setCsv(await e.target.files[0]?.text() || '')} />
        <label htmlFor="csv" className="sr-only">CSV text</label>
        <textarea id="csv" rows="5" value={csv} onChange={(e) => setCsv(e.target.value)} placeholder={'alias,program,year,semester,tier,required_courses,backlog_courses\nriya,B.Tech CSE,3,5,All students,,MAT1003'} />
        <p><button className="primary" disabled={!csv.trim()} onClick={importCsv}>Import</button></p>
        {note}
        {codes && (<div className="note warn">
          <b>{codes.created} created, {codes.updated} updated.</b> Invite codes are shown once only — copy them now.
          {codes.problems.map((p) => <p key={p}>Problem: {p}</p>)}
          <pre>{codes.codes.map(([a, c]) => `${a}\t${c}`).join('\n') || 'No new codes.'}</pre>
        </div>)}
      </div>
      <div className="card scroll">
        <h2>Testers ({rows.length})</h2>
        <table className="data"><thead><tr><th>Alias</th><th>Program</th><th>Tier</th><th>Courses</th><th>Submitted</th><th>Code expires</th><th></th></tr></thead>
          <tbody>{rows.map((t) => (
            <tr key={t.id}>
              <td>{t.alias}{t.synthetic && <span className="tag syn">synthetic</span>}</td>
              <td>{t.program} · sem {t.semester}</td>
              <td><select aria-label={`Tier for ${t.alias}`} value={t.tier} onChange={(e) => run(() => api(`/api/admin/testers/${t.id}/tier`, { method: 'PUT', body: { tier: e.target.value } })).then(load)}>
                {tiers.map((x) => <option key={x}>{x}</option>)}</select></td>
              <td className="small">{t.required.join(' ')}{t.backlog.length ? ` · backlog ${t.backlog.join(' ')}` : ''}</td>
              <td>{t.submitted_at ? `${when(t.submitted_at)} (×${t.submit_count})` : 'no'}</td>
              <td>{when(t.code_expires)}</td>
              <td className="nowrap">
                <button className="small" onClick={async () => { const r = await run(() => api(`/api/admin/testers/${t.id}/code`, { method: 'POST' })); if (r) { setCodes({ created: 1, updated: 0, problems: [], codes: [[t.alias, r.code]] }); load(); } }}>New code</button>{' '}
                <button className="small danger" onClick={() => window.confirm(`Delete ${t.alias} and everything they entered?`) && run(() => api(`/api/admin/testers/${t.id}`, { method: 'DELETE' })).then(load)}>Delete</button>
              </td>
            </tr>))}</tbody></table>
      </div>
    </>
  );
}

function Settings({ o, reload }) {
  const s = o.settings;
  const [f, setF] = useState({ ...s, tiers: s.tiers.join('\n') });
  const [run, note] = useAction();
  const num = (k, label, step = 1) => (<><label htmlFor={k}>{label}</label><input id={k} type="number" step={step} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></>);
  const txt = (k, label) => (<><label htmlFor={k}>{label}</label><input id={k} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></>);
  async function save(e) {
    e.preventDefault();
    const body = {
      tiers: f.tiers.split('\n').map((t) => t.trim()).filter(Boolean),
      credit_min: +f.credit_min, credit_max: +f.credit_max, seats_per_section: +f.seats_per_section,
      beta_seats_per_section: +f.beta_seats_per_section, use_beta_seats: !!f.use_beta_seats,
      window_open: f.window_open, window_close: f.window_close, allocation_seed: f.allocation_seed,
      earlier_miss_weight: +f.earlier_miss_weight, add_drop_changes_per_student: +f.add_drop_changes_per_student,
      privacy_contact: f.privacy_contact,
    };
    if (await run(() => api('/api/admin/settings', { method: 'PUT', body }), 'Saved.')) reload();
  }
  return (
    <form className="card" onSubmit={save}>
      <h2>Settings</h2>
      <label htmlFor="tiers">Priority tiers, highest first (one per line)</label>
      <textarea id="tiers" rows="3" value={f.tiers} onChange={(e) => setF({ ...f, tiers: e.target.value })} />
      <p className="small muted">Students are allocated tier by tier. Inside a tier the published equal-priority order applies.</p>
      {num('credit_min', 'Minimum credits')}{num('credit_max', 'Maximum credits')}
      {num('seats_per_section', 'Seats per section (synthetic)')}
      {num('beta_seats_per_section', 'Seats per section at beta scale (synthetic)')}
      <label style={{ display: 'flex', gap: '.5rem', alignItems: 'center' }}><input type="checkbox" checked={!!f.use_beta_seats} onChange={(e) => setF({ ...f, use_beta_seats: e.target.checked })} /> Use the beta-scale seats (so slots fill with few testers)</label>
      {txt('window_open', 'Window opens (ISO date-time with zone)')}{txt('window_close', 'Window closes')}
      {txt('allocation_seed', 'Published seed for the equal-priority order')}
      {num('earlier_miss_weight', 'Weight for moving up students who missed their top pattern earlier (0 = off)', 0.1)}
      {num('add_drop_changes_per_student', 'Add/drop changes allowed per student')}
      {txt('privacy_contact', 'Privacy contact shown to testers')}
      {note}
      <p><button className="primary">Save settings</button></p>
    </form>
  );
}

function Capacity() {
  const [course, setCourse] = useState('');
  const [data, setData] = useState(null);
  const [run, note] = useAction();
  const load = (c = course) => run(() => api(`/api/admin/capacity?course=${encodeURIComponent(c)}`)).then((r) => r && setData(r));
  useEffect(() => { load(''); }, []);
  const save = (id, seats) => run(() => api('/api/admin/capacity', { method: 'PUT', body: { offering_id: id, seats } }), 'Saved.').then(() => load());
  return (
    <div className="card">
      <h2>Seat capacity <span className="tag syn">synthetic</span></h2>
      <p className="small">Annexure II has no capacities. Default seats = sections × seats per section{data ? ` (currently ${data.per_section})` : ''}. Override any course-slot here. With no course entered, the overrides are listed.</p>
      <form className="row" onSubmit={(e) => { e.preventDefault(); load(); }}>
        <label htmlFor="cc" className="sr-only">Course code</label>
        <input id="cc" className="grow" placeholder="Course code, e.g. CSE2001" value={course} onChange={(e) => setCourse(e.target.value.toUpperCase())} />
        <button>Show</button>
      </form>
      {note}
      {data && (<div className="scroll"><table className="data"><thead><tr><th>Course-slot</th><th>Sections</th><th>Taken</th><th>Seats</th><th></th></tr></thead>
        <tbody>{data.offerings.map((o) => (
          <tr key={o.id}><td>{o.course} {o.type} {o.slot}{o.overridden && <span className="tag">override</span>}</td><td>{o.sections}</td><td>{o.taken}</td>
            <td><input aria-label={`Seats for ${o.id}`} type="number" min="0" defaultValue={o.seats} style={{ width: '6rem' }} onBlur={(e) => +e.target.value !== o.seats && save(o.id, +e.target.value)} /></td>
            <td>{o.overridden && <button className="small" onClick={() => save(o.id, null)}>Use default</button>}</td></tr>))}
          {data.offerings.length === 0 && <tr><td colSpan="5" className="muted">Nothing to show.</td></tr>}</tbody></table></div>)}
    </div>
  );
}

function Fairness({ r }) {
  return (
    <>
      <div className="stats">
        <Stat label="students" value={r.students} /><Stat label="got 1st-choice pattern" value={r.first_choice} />
        <Stat label="got 2nd choice" value={r.second_choice} /><Stat label="got 3rd choice" value={r.third_choice} />
        <Stat label="4th or lower" value={r.fourth_or_lower} /><Stat label="unplaced (add/drop)" value={r.unplaced} />
        <Stat label="mean choice" value={r.mean_choice} /><Stat label="spread (std dev)" value={r.choice_spread} />
        <Stat label="mean choice, first quarter of order" value={r.mean_choice_first_quarter} />
        <Stat label="mean choice, last quarter of order" value={r.mean_choice_last_quarter} />
        <Stat label="course-slots full" value={r.course_slots_full} /><Stat label="capacity exceeded (must be 0)" value={r.capacity_exceeded} />
        {r.missed_top_choice_last_round !== undefined && <Stat label="missed top choice last round → improved now" value={`${r.missed_top_choice_last_round} → ${r.of_those_improved_this_round}`} />}
      </div>
      {Object.keys(r.by_tier).length > 1 && <p className="small">By tier: {Object.entries(r.by_tier).map(([t, v]) => `${t}: ${v.first_choice}/${v.students} first choice, mean ${v.mean_choice ?? '—'}`).join(' · ')}</p>}
    </>
  );
}

function Allocation({ o, reload }) {
  const [round, setRound] = useState(1);
  const [result, setResult] = useState(null);
  const [sim, setSim] = useState(null);
  const [simCfg, setSimCfg] = useState({ students: 200, seats_per_section: 3, rounds: 2 });
  const [busy, setBusy] = useState('');
  const [run, note] = useAction();
  async function allocate(kind) {
    if (kind === 'final' && !window.confirm('Run the FINAL allocation? Testers will see their results.')) return;
    setBusy(kind);
    const r = await run(() => api('/api/admin/allocate', { method: 'POST', body: { kind, round: +round } }), kind === 'final' ? 'Final run saved. Testers can now see results.' : 'Dry run finished. Nothing was saved.');
    setBusy('');
    if (r) { setResult(r); reload(); }
  }
  async function simulate() {
    setBusy('sim');
    const r = await run(() => api('/api/admin/simulate', { method: 'POST', body: simCfg }));
    setBusy('');
    if (r) setSim(r);
  }
  return (
    <>
      <div className="card">
        <h2>Run allocation</h2>
        <p className="small">{o.method}</p>
        <p className="small">Seed: <code>{o.settings.allocation_seed}</code> · window is <b>{o.window_state}</b> · {o.counts.submitted} of {o.counts.testers} testers submitted.</p>
        <div className="row">
          <label htmlFor="round" style={{ margin: 0 }}>Round</label>
          <input id="round" type="number" min="1" value={round} onChange={(e) => setRound(e.target.value)} style={{ width: '5rem' }} />
          <button disabled={!!busy} onClick={() => allocate('dry')}>{busy === 'dry' ? 'Running…' : 'Dry run (saves nothing)'}</button>
          <button className="primary" disabled={!!busy} onClick={() => allocate('final')}>{busy === 'final' ? 'Running…' : 'Final run'}</button>
        </div>
        {note}
        {o.runs.length > 0 && <p className="small">Saved runs: {o.runs.map((r) => (
          <button key={r.id} className="link" onClick={() => run(() => api(`/api/admin/runs/${r.id}`)).then((x) => x && setResult(x))}>#{r.id} round {r.round} ({when(r.created)})</button>))}</p>}
      </div>
      {result && (
        <div className="card">
          <h2>Fairness report — {result.saved ? `final run #${result.run_id}` : 'dry run'}, round {result.report.round}</h2>
          <Fairness r={result.report} />
          <div className="scroll"><table className="data"><thead><tr><th>#</th><th>Alias</th><th>Tier</th><th>Result</th><th>Why</th></tr></thead>
            <tbody>{result.assignments.map((a) => (
              <tr key={a.alias}><td>{a.position ?? '—'}</td><td>{a.alias}</td><td>{a.tier}</td>
                <td>{a.status === 'placed' ? `choice ${a.choice_rank}: ${a.archetype}` : 'unplaced'}</td><td className="small">{a.explanation}</td></tr>))}</tbody></table></div>
        </div>
      )}
      <div className="card">
        <h2>Simulation <span className="tag syn">synthetic</span></h2>
        <p className="small">Generates students with varied choices to show behaviour at scale. Nothing is saved and no tester data is used. Larger runs take up to a minute.</p>
        <div className="row">
          {[['students', 'Students'], ['seats_per_section', 'Seats per section'], ['rounds', 'Rounds']].map(([k, label]) => (
            <span key={k}><label htmlFor={`sim-${k}`}>{label}</label><input id={`sim-${k}`} type="number" min="1" value={simCfg[k]} onChange={(e) => setSimCfg({ ...simCfg, [k]: +e.target.value })} style={{ width: '7rem' }} /></span>))}
          <button disabled={!!busy} onClick={simulate} style={{ alignSelf: 'flex-end' }}>{busy === 'sim' ? 'Simulating…' : 'Run simulation'}</button>
        </div>
        {sim && (<>
          <p className="note warn">{sim.label}. {sim.students} students, {sim.seats_per_section} seats per section, seed <code>{sim.seed}</code>.</p>
          {sim.rounds.map((r) => <div key={r.round}><h3>Round {r.round}</h3><Fairness r={r} /></div>)}
        </>)}
      </div>
    </>
  );
}

function Logs() {
  const [diag, setDiag] = useState([]);
  const [timing, setTiming] = useState([]);
  useEffect(() => { api('/api/admin/diagnostics').then(setDiag).catch(() => {}); api('/api/admin/timing').then(setTiming).catch(() => {}); }, []);
  return (
    <>
      <div className="card scroll">
        <h2>Time to complete</h2>
        <table className="data"><thead><tr><th>Alias</th><th>Started</th><th>Submitted</th><th>Minutes</th><th>Steps reached</th><th>Errors</th></tr></thead>
          <tbody>{timing.map((t) => <tr key={t.alias}><td>{t.alias}</td><td>{when(t.started)}</td><td>{when(t.submitted)}</td><td>{t.minutes ?? '—'}</td><td className="small">{t.steps.join(' › ')}</td><td>{t.errors}</td></tr>)}</tbody></table>
      </div>
      <div className="card scroll">
        <h2>Diagnostics and errors (latest 200)</h2>
        <table className="data"><thead><tr><th>When</th><th>Alias</th><th>Type</th><th>Detail</th></tr></thead>
          <tbody>{diag.map((d, i) => <tr key={i}><td className="nowrap">{when(d.ts)}</td><td>{d.alias || '—'}</td><td>{d.type}</td><td className="small">{d.detail?.conflicts?.join(' ') || JSON.stringify(d.detail)}</td></tr>)}
            {diag.length === 0 && <tr><td colSpan="4" className="muted">Nothing logged yet.</td></tr>}</tbody></table>
      </div>
    </>
  );
}

function Exports() {
  return (
    <div className="card">
      <h2>Exports (CSV)</h2>
      <div className="row">
        {[['results.csv', 'Allocation results'], ['feedback.csv', 'Feedback and SUS scores'], ['timing.csv', 'Time to complete'], ['events.csv', 'Full event log']].map(([f, label]) => (
          <a key={f} className="btn" href={`/api/admin/export/${f}`} download>{label}</a>))}
      </div>
      <p className="small muted">Exports contain aliases only.</p>
    </div>
  );
}

function Reset({ reload }) {
  const [text, setText] = useState('');
  const [run, note] = useAction();
  return (
    <div className="card">
      <h2>Reset the beta</h2>
      <p>Deletes all testers, choices, allocation runs, logs, feedback and capacity overrides. Settings and course data stay. A backup of the database is taken first.</p>
      <label htmlFor="rs">Type RESET to confirm</label>
      <input id="rs" value={text} onChange={(e) => setText(e.target.value)} />
      {note}
      <p className="row">
        <button className="danger" disabled={text !== 'RESET'} onClick={async () => { const r = await run(() => api('/api/admin/reset', { method: 'POST', body: { confirm: text } })); if (r) { setText(''); await run(async () => r, `Beta reset. Backup saved as ${r.backup}.`); reload(); } }}>Reset everything</button>
        <button onClick={() => run(() => api('/api/admin/backup', { method: 'POST' })).then((r) => r && run(async () => r, `Backup saved as ${r.file}.`))}>Back up now</button>
      </p>
    </div>
  );
}

export default function Admin({ signedIn }) {
  const [ok, setOk] = useState(signedIn);
  const [tab, setTab] = useState('Overview');
  const [o, setO] = useState(null);
  const [error, setError] = useState('');
  const reload = () => api('/api/admin/overview').then(setO).catch((e) => { if (e.status === 401 || e.status === 403) setOk(false); else setError(e.message); });
  useEffect(() => { if (ok) reload(); }, [ok]);
  if (!ok) return (<><header className="top"><h1>Course allocation — admin</h1></header><AdminSignIn onDone={() => setOk(true)} /></>);
  return (
    <>
      <header className="top"><h1>Course allocation — admin</h1>
        <button className="small" onClick={async () => { await api('/api/logout', { method: 'POST' }).catch(() => {}); setOk(false); setO(null); }}>Sign out</button></header>
      <main className="wide">
        <div className="tabs" role="tablist">{TABS.map((t) => <button key={t} role="tab" aria-selected={t === tab} onClick={() => setTab(t)}>{t}</button>)}</div>
        {error && <p className="note bad" role="alert">{error}</p>}
        {!o ? <p>Loading…</p> : (
          <div style={{ marginTop: '.8rem' }}>
            {tab === 'Overview' && <Overview o={o} reload={reload} />}
            {tab === 'Data' && <Data reload={reload} />}
            {tab === 'Testers' && <Testers tiers={o.settings.tiers} />}
            {tab === 'Settings' && <Settings key={JSON.stringify(o.settings)} o={o} reload={reload} />}
            {tab === 'Capacity' && <Capacity />}
            {tab === 'Allocation' && <Allocation o={o} reload={reload} />}
            {tab === 'Logs' && <Logs />}
            {tab === 'Exports' && <Exports />}
            {tab === 'Reset' && <Reset reload={reload} />}
          </div>)}
      </main>
    </>
  );
}
