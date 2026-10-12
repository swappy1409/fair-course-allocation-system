import React, { useEffect, useMemo, useRef, useState } from 'react';
import { DndContext, KeyboardSensor, PointerSensor, closestCenter, useSensor, useSensors } from '@dnd-kit/core';
import { SortableContext, arrayMove, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { api, logEvent, setCsrf } from './api.js';
import Timetable from './Timetable.jsx';

const STEPS = [
  ['courses', 'Your courses'],
  ['electives', 'Choose electives'],
  ['pins', 'Pin a slot (optional)'],
  ['ranking', 'Rank timetable patterns'],
  ['review', 'Review and submit'],
];
const BASKETS = ['Program Elective', 'University Elective', 'Program Core', 'University Core'];
const ORD = ['1st', '2nd', '3rd'];
const ord = (n) => ORD[n - 1] || `${n}th`;
const when = (iso) => new Date(iso).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });

export function Privacy({ contact }) {
  return (
    <details className="small muted">
      <summary>Privacy: what this beta records</summary>
      <p>
        This is a student lab project, not the university registration system. Nothing you do here registers
        you for a real course. We store your alias, the courses and patterns you choose, the time you reach
        each step (to measure how long registration takes), any error messages, and the feedback you type.
        We do not store your name, registration number or password. The data is used only for this lab
        project and is deleted when it ends.{contact ? <> Questions or removal requests: <b>{contact}</b>.</> : null}
      </p>
    </details>
  );
}

export function SignIn({ onDone }) {
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      const r = await api('/api/login', { method: 'POST', body: { code: code.trim() } });
      setCsrf(r.csrf);
      onDone();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main>
      <form className="card" onSubmit={submit}>
        <h2>Sign in</h2>
        <p className="muted">Enter the invite code you were given. There is no password.</p>
        <label htmlFor="code">Invite code</label>
        <input id="code" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} autoComplete="off"
          autoCapitalize="characters" spellCheck="false" placeholder="ABCD-2345" required aria-describedby="code-err" />
        <div id="code-err" role="alert">{error && <p className="note bad">{error}</p>}</div>
        <p><button className="primary" disabled={busy || code.trim().length < 4}>{busy ? 'Signing in…' : 'Sign in'}</button></p>
        <Privacy />
      </form>
    </main>
  );
}

function Diagnosis({ d, onApply }) {
  return (
    <div className="note bad" role="alert">
      <b>{d.summary}</b>
      {d.conflicts.map((c) => <p key={c}>{c}</p>)}
      {d.relaxations.length > 0 && (
        <>
          <p><b>Smallest changes that fix it:</b></p>
          {d.relaxations.map((r) => (
            <div className="row" key={r.message} style={{ marginBottom: '.4rem' }}>
              <span className="grow">{r.message} <span className="muted">→ {r.unlocks_text}</span></span>
              <button type="button" className="small" onClick={() => onApply(r)}>Apply</button>
            </div>
          ))}
        </>
      )}
    </div>
  );
}

function CourseRow({ c, tag }) {
  return (
    <span className="grow">
      <span className="code">{c.code}</span> {c.title}
      <span className="tag">{c.credits} cr</span>
      {tag && <span className="tag">{tag}</span>}
    </span>
  );
}

function SortableItem({ item, index, total, never, onMove, onNever }) {
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id: item.id });
  return (
    <li ref={setNodeRef} style={{ transform: CSS.Transform.toString(transform), transition }} className={never ? 'never' : ''}>
      <button type="button" className="handle" {...attributes} {...listeners} aria-label={`Drag to reorder ${item.label}`}>⠿</button>
      <span className="pos">{never ? '–' : index + 1}</span>
      <span className="grow">
        <b>{item.label}</b> <span className="tag">{item.count} timetable{item.count === 1 ? '' : 's'}</span>
        <br /><span className="small muted">{item.description}</span>
        <br />
        <label style={{ display: 'inline-flex', gap: '.4rem', alignItems: 'center', fontWeight: 400, margin: '.2rem 0 0' }}>
          <input type="checkbox" checked={never} onChange={() => onNever(item.id)} /> Never give me this
        </label>
      </span>
      <span className="move">
        <button type="button" disabled={index === 0} onClick={() => onMove(index, index - 1)} aria-label={`Move ${item.label} up`}>▲</button>
        <button type="button" disabled={index === total - 1} onClick={() => onMove(index, index + 1)} aria-label={`Move ${item.label} down`}>▼</button>
      </span>
    </li>
  );
}

const SUS = [
  'I think that I would like to use this system frequently.',
  'I found the system unnecessarily complex.',
  'I thought the system was easy to use.',
  'I think that I would need the support of a technical person to be able to use this system.',
  'I found the various functions in this system were well integrated.',
  'I thought there was too much inconsistency in this system.',
  'I would imagine that most people would learn to use this system very quickly.',
  'I found the system very cumbersome to use.',
  'I felt very confident using the system.',
  'I needed to learn a lot of things before I could get going with this system.',
];

function Likert({ name, value, onChange, low = 'Strongly disagree', high = 'Strongly agree' }) {
  return (
    <>
      <div className="likert" role="radiogroup" aria-label={name}>
        {[1, 2, 3, 4, 5].map((n) => (
          <label key={n}><input type="radio" name={name} checked={value === n} onChange={() => onChange(n)} />{n}</label>
        ))}
      </div>
      <div className="row small muted" style={{ justifyContent: 'space-between', marginTop: '-.6rem' }}><span>1 = {low}</span><span>5 = {high}</span></div>
    </>
  );
}

function Feedback({ given, onDone }) {
  const [sus, setSus] = useState(Array(10).fill(0));
  const [ease, setEase] = useState(0);
  const [confused, setConfused] = useState('');
  const [comments, setComments] = useState('');
  const [state, setState] = useState(given ? 'sent' : 'form');
  const [error, setError] = useState('');
  if (state === 'sent') return <p className="note good">Thank you — your feedback is saved.</p>;
  const ready = sus.every(Boolean) && ease;
  async function send(e) {
    e.preventDefault();
    try {
      await api('/api/feedback', { method: 'POST', body: { sus, ease, confused, comments } });
      setState('sent');
      onDone?.();
    } catch (err) { setError(err.message); }
  }
  return (
    <form onSubmit={send}>
      <h2>Two minutes of feedback</h2>
      <p className="muted">This is the part that helps most. 1 = strongly disagree, 5 = strongly agree.</p>
      {SUS.map((q, i) => (
        <div key={q}>
          <p id={`sus${i}`}>{i + 1}. {q}</p>
          <Likert name={`Question ${i + 1}`} value={sus[i]} onChange={(n) => setSus(sus.map((v, j) => (j === i ? n : v)))} />
        </div>
      ))}
      <p>Overall, how easy was it to register here?</p>
      <Likert name="Ease" value={ease} onChange={setEase} low="Very hard" high="Very easy" />
      <label htmlFor="confused">What confused you?</label>
      <textarea id="confused" rows="3" maxLength="2000" value={confused} onChange={(e) => setConfused(e.target.value)} />
      <label htmlFor="comments">Anything else?</label>
      <textarea id="comments" rows="3" maxLength="4000" value={comments} onChange={(e) => setComments(e.target.value)} />
      {error && <p className="note bad" role="alert">{error}</p>}
      <p><button className="primary" disabled={!ready}>Send feedback</button>{!ready && <span className="small muted"> Answer all 11 ratings to send.</span>}</p>
    </form>
  );
}

function Result({ me, onAddDrop }) {
  const [r, setR] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => { api('/api/result').then(setR).catch((e) => setError(e.message)); }, []);
  if (error) return <p className="note bad" role="alert">{error}</p>;
  if (!r) return <p>Loading your result…</p>;
  if (!r.ready) {
    return (
      <div className="card">
        <h2>Your result</h2>
        <p>Seats have not been allocated yet. Registration closes {when(me.window.close)}; come back after that with the same invite code.</p>
      </div>
    );
  }
  const left = r.add_drop.allowed - r.add_drop.used;
  return (
    <>
      <div className="card">
        <h2>Your result</h2>
        <p className={`note ${r.status === 'placed' ? 'good' : 'warn'}`}>{r.explanation}</p>
        {r.timetable && <><h3>Your timetable: {r.timetable.label}</h3><Timetable classes={r.timetable.classes} /></>}
        {me.capacity_source === 'synthetic' && <p className="small muted"><span className="tag syn">Synthetic</span> Seat numbers in this beta are made up for testing, not the real section sizes.</p>}
      </div>
      <div className="card">
        <h3 style={{ marginTop: 0 }}>How the order was decided</h3>
        {r.position && <p>You were number <b>{r.position}</b> of {r.students} in round {r.round}.</p>}
        <p className="small">{r.method}</p>
        <p className="small">Published seed for this round: <code>{r.seed}</code></p>
      </div>
      <div className="card">
        <h3 style={{ marginTop: 0 }}>Add/drop</h3>
        {left > 0
          ? <><p>You can change your electives, pins or pattern order {left === 1 ? 'once' : `${left} times`}. The change is seated straight away from the seats that are left.</p>
            <button onClick={onAddDrop}>Change my choices</button></>
          : <p>You have used your add/drop change for this round.</p>}
      </div>
    </>
  );
}

export default function Student({ onSignOut }) {
  const [me, setMe] = useState(null);
  const [courses, setCourses] = useState([]);
  const [choice, setChoice] = useState({ electives: [], pins: [], ranking: [], never: [] });
  const [step, setStep] = useState('courses');
  const [mode, setMode] = useState('register');       // 'register' or 'adddrop'
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [basket, setBasket] = useState(BASKETS[0]);
  const [query, setQuery] = useState('');
  const [submitted, setSubmitted] = useState(null);
  const started = useRef(false);
  const heading = useRef(null);

  useEffect(() => {
    Promise.all([api('/api/me'), api('/api/courses')]).then(([m, cs]) => {
      setMe(m);
      setCourses(cs);
      setChoice({ electives: m.preferences.electives, pins: m.preferences.pins, ranking: m.preferences.ranking, never: m.preferences.never });
      setSubmitted(m.preferences.submitted_at);
      if (m.has_result) setStep('result');
    }).catch((e) => setError(e.message));
    const onErr = (e) => logEvent('error', e.message || 'script error');
    window.addEventListener('error', onErr);
    return () => window.removeEventListener('error', onErr);
  }, []);

  // Live count: ask the server whenever the choice changes (debounced).
  const key = JSON.stringify(choice);
  useEffect(() => {
    if (!me) return undefined;
    setLoading(true);
    const t = setTimeout(() => {
      api('/api/preview', { method: 'POST', body: choice })
        .then((p) => { setPreview(p); setError(''); })
        .catch((e) => setError(e.message))
        .finally(() => setLoading(false));
    }, 350);
    return () => clearTimeout(t);
  }, [key, !!me]);

  useEffect(() => { heading.current?.focus(); window.scrollTo(0, 0); }, [step]);

  const byCode = useMemo(() => Object.fromEntries(courses.map((c) => [c.code, c])), [courses]);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }));

  if (error && !me) return <main><p className="note bad" role="alert">{error}</p><button onClick={onSignOut}>Back to sign in</button></main>;
  if (!me) return <main><p>Loading…</p></main>;

  const fixed = [...me.required, ...me.backlog];
  const selected = [...fixed, ...choice.electives.map((e) => byCode[e]).filter(Boolean)];
  const credits = selected.reduce((n, c) => n + (c.credits || 0), 0);
  const creditsOk = credits >= me.credit_min && credits <= me.credit_max;
  const open = me.window.state === 'open' || mode === 'adddrop';
  const stepIndex = STEPS.findIndex((s) => s[0] === step);

  // Patterns that exist for the current choice, in the student's order.
  const available = preview?.archetypes || [];
  const order = [...choice.ranking.filter((id) => available.some((a) => a.id === id)),
    ...available.map((a) => a.id).filter((id) => !choice.ranking.includes(id))];
  const ranked = order.map((id) => available.find((a) => a.id === id));
  const setRanking = (ids) => setChoice((c) => ({ ...c, ranking: ids }));

  function toggleElective(code) {
    setChoice((c) => {
      const on = c.electives.includes(code);
      return { ...c, electives: on ? c.electives.filter((e) => e !== code) : [...c.electives, code],
        pins: on ? c.pins.filter((p) => !p.startsWith(`${code}:`)) : c.pins };
    });
  }
  function setPin(code, type, slot) {
    setChoice((c) => ({ ...c, pins: [...c.pins.filter((p) => !p.startsWith(`${code}:${type}:`)), ...(slot ? [`${code}:${type}:${slot}`] : [])] }));
  }
  function go(to) {
    if (!started.current && step === 'courses') { started.current = true; logEvent('started'); }
    const marks = { electives: 'courses_chosen', pins: 'pins_set', ranking: 'ranking_saved' };
    if (marks[step] && STEPS.findIndex((s) => s[0] === to) > stepIndex) logEvent(marks[step]);
    if (me.window.state === 'open' && mode === 'register') api('/api/preferences', { method: 'PUT', body: { ...choice, ranking: order } }).catch(() => {});
    setStep(to);
  }
  async function submit() {
    setError('');
    try {
      const body = { ...choice, ranking: order };
      if (mode === 'adddrop') {
        await api('/api/adddrop', { method: 'POST', body });
        setMode('register');
        setStep('result');
      } else {
        await api('/api/submit', { method: 'POST', body });
        setSubmitted(new Date().toISOString());
        setStep('done');
      }
    } catch (e) {
      setError(e.message);
      logEvent('error', e.message);
    }
  }
  async function signOut() {
    await api('/api/logout', { method: 'POST' }).catch(() => {});
    onSignOut();
  }

  const header = (
    <header className="top">
      <h1>Course registration <span className="tag">beta</span></h1>
      <span className="row"><span className="small">{me.alias}</span><button className="small" onClick={signOut}>Sign out</button></span>
    </header>
  );

  if (step === 'result') {
    return (<>{header}<main>
      <h2 ref={heading} tabIndex="-1" className="sr-only">Your result</h2>
      <Result me={me} onAddDrop={() => { setMode('adddrop'); setStep('electives'); }} />
      {!me.feedback_given && <div className="card"><Feedback given={false} /></div>}
      <Privacy contact={me.privacy_contact} />
    </main></>);
  }
  if (step === 'done') {
    return (<>{header}<main>
      <div className="card">
        <h2 ref={heading} tabIndex="-1">Submitted</h2>
        <p className="note good">Your choices are saved. You can change them any time until {when(me.window.close)}.</p>
        <p>After the window closes, seats are allocated and your result appears here. Sign in again with the same invite code to see it.</p>
        <div className="row"><button onClick={() => setStep('electives')}>Edit my choices</button><button onClick={() => setStep('result')}>Check for my result</button></div>
      </div>
      <div className="card"><Feedback given={me.feedback_given} onDone={() => setMe({ ...me, feedback_given: true })} /></div>
      <Privacy contact={me.privacy_contact} />
    </main></>);
  }

  const shown = courses.filter((c) => !c.fixed && c.basket === basket
    && (!query || `${c.code} ${c.title}`.toLowerCase().includes(query.toLowerCase())));
  const canNext = step === 'courses' ? true : creditsOk && preview?.count > 0;
  const count = preview?.count ?? 0;

  return (
    <>
      {header}
      <main>
        <p className="small muted" style={{ margin: 0 }}>Step {stepIndex + 1} of {STEPS.length}{mode === 'adddrop' ? ' · add/drop change' : ''}</p>
        <ol className="steps" aria-hidden="true">{STEPS.map((s, i) => <li key={s[0]} className={i < stepIndex ? 'done' : i === stepIndex ? 'now' : ''} />)}</ol>
        <h2 ref={heading} tabIndex="-1">{STEPS[stepIndex][1]}</h2>

        {me.window.state === 'before' && <p className="note warn">Registration opens {when(me.window.open)}. You can look around, but you cannot submit yet.</p>}
        {me.window.state === 'closed' && mode === 'register' && <p className="note warn">The registration window has closed. Your last submitted choices stand.</p>}
        {submitted && mode === 'register' && me.window.state === 'open' && <p className="note good">You submitted on {when(submitted)}. Submitting again replaces it.</p>}

        {step === 'courses' && (
          <div className="card">
            <p>{me.program}, semester {me.semester}. These courses are already in your timetable; you only choose the rest.
              {me.synthetic && <span className="tag syn">Synthetic test profile</span>}</p>
            <h3>Required this semester</h3>
            <ul className="list">{me.required.map((c) => <li key={c.code}><div className="item"><CourseRow c={c} /></div></li>)}</ul>
            {me.backlog.length > 0 && <><h3>Re-registration (backlog)</h3>
              <ul className="list">{me.backlog.map((c) => <li key={c.code}><div className="item"><CourseRow c={c} tag="backlog" /></div></li>)}</ul></>}
            <p className="small muted">Registration is open {when(me.window.open)} to {when(me.window.close)}. You need {me.credit_min}–{me.credit_max} credits in total.</p>
            <p className="small muted"><span className="tag syn">Note</span> Credits are derived from the slot pattern and baskets are synthetic in this beta; they may differ from the official curriculum.</p>
            <Privacy contact={me.privacy_contact} />
          </div>
        )}

        {step === 'electives' && (
          <div className="card">
            <p>Pick electives until your total is between {me.credit_min} and {me.credit_max} credits.</p>
            {choice.electives.length > 0 && <p className="small">Chosen: {choice.electives.map((e) => (
              <button key={e} type="button" className="small" style={{ margin: '0 .25rem .25rem 0' }} onClick={() => toggleElective(e)} aria-label={`Remove ${e}`}>{e} ✕</button>))}</p>}
            <div className="tabs" role="tablist" aria-label="Basket">
              {BASKETS.map((b) => <button key={b} role="tab" aria-selected={b === basket} onClick={() => setBasket(b)}>{b}</button>)}
            </div>
            <label htmlFor="q" className="sr-only">Search courses</label>
            <input id="q" type="search" placeholder="Search by code or title" value={query} onChange={(e) => setQuery(e.target.value)} style={{ marginTop: '.4rem' }} />
            <ul className="list">
              {shown.map((c) => (
                <li key={c.code}><label>
                  <input type="checkbox" checked={choice.electives.includes(c.code)} onChange={() => toggleElective(c.code)} />
                  <CourseRow c={c} />
                </label></li>
              ))}
              {shown.length === 0 && <li className="muted" style={{ padding: '.6rem 0' }}>No courses match.</li>}
            </ul>
          </div>
        )}

        {step === 'pins' && (
          <div className="card">
            <p>If a course must be in a particular slot, choose it here. Leave everything on “Any slot” to keep the most options.</p>
            {selected.map((c) => c.components.map((comp) => {
              const id = `pin-${c.code}-${comp.type}`;
              const cur = choice.pins.find((p) => p.startsWith(`${c.code}:${comp.type}:`))?.split(':')[2] || '';
              const kind = ['ELA', 'LO'].includes(comp.type) ? 'lab' : 'theory';
              return (
                <div key={id}>
                  <label htmlFor={id}>{c.code} {kind} <span className="muted" style={{ fontWeight: 400 }}>{c.title}</span></label>
                  {comp.slots.length === 1
                    ? <p className="small muted" id={id}>Only offered in {comp.slots[0]}.</p>
                    : <select id={id} value={cur} onChange={(e) => setPin(c.code, comp.type, e.target.value)}>
                      <option value="">Any slot ({comp.slots.length} offered)</option>
                      {comp.slots.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>}
                </div>
              );
            }))}
          </div>
        )}

        {step === 'ranking' && (
          <div className="card">
            <p>Put the patterns in the order you want them. You rank the shape of the week, not single timetables. Drag, or use the arrows.</p>
            <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={({ active, over }) => {
              if (over && active.id !== over.id) setRanking(arrayMove(order, order.indexOf(active.id), order.indexOf(over.id)));
            }}>
              <SortableContext items={order} strategy={verticalListSortingStrategy}>
                <ol className="rank">
                  {ranked.map((a, i) => (
                    <SortableItem key={a.id} item={a} index={i} total={ranked.length} never={choice.never.includes(a.id)}
                      onMove={(from, to) => setRanking(arrayMove(order, from, to))}
                      onNever={(id) => setChoice((c) => ({ ...c, ranking: order, never: c.never.includes(id) ? c.never.filter((n) => n !== id) : [...c.never, id] }))} />
                  ))}
                </ol>
              </SortableContext>
            </DndContext>
            {ranked.length > 0 && ranked.every((a) => choice.never.includes(a.id)) && <p className="note bad" role="alert">You have marked every pattern as “never”. Allow at least one.</p>}
            <p className="small muted">Inside a pattern, timetables with fewer idle hours and fewer days on campus come first.</p>
          </div>
        )}

        {step === 'review' && (
          <div className="card">
            <p><b>{credits} credits</b> · {selected.length} courses · {choice.pins.length} pin{choice.pins.length === 1 ? '' : 's'}</p>
            <p className="small">{selected.map((c) => c.code).join(', ')}</p>
            {preview?.top?.length > 0 && <p>The best timetable in each of your top {preview.top.length === 1 ? 'pattern' : `${preview.top.length} patterns`}. Which one you get depends on seats.</p>}
            {preview?.top?.map((t) => (
              <details key={t.archetype} open={t.choice === 1}>
                <summary><b>{ord(t.choice)} choice: {t.label}</b> <span className="small muted">{t.features.days_used} days · {t.features.gap_hours} idle hours</span></summary>
                <Timetable classes={t.classes} />
              </details>
            ))}
          </div>
        )}

        {preview?.diagnosis && step !== 'courses' && (step !== 'electives' || creditsOk) && (
          <Diagnosis d={preview.diagnosis} onApply={(r) => setChoice((c) => ({ ...c, electives: r.electives, pins: r.pins }))} />
        )}
        {error && <p className="note bad" role="alert">{error}</p>}
      </main>

      <div className="bar">
        <div className="bar-in">
          <div className="status" aria-live="polite">
            <span className={creditsOk ? 'ok' : 'no'}>{credits} credits <span className="muted" style={{ fontWeight: 400 }}>(need {me.credit_min}–{me.credit_max})</span></span>
            <span className={count > 0 ? 'ok' : 'no'}>{loading ? 'Checking…' : !creditsOk ? '' : count > 0 ? `${preview.exact ? '' : 'at least '}${count.toLocaleString()} combination${count === 1 ? '' : 's'} available` : 'No timetable possible'}</span>
          </div>
          <div className="nav">
            {stepIndex > 0 && <button onClick={() => go(STEPS[stepIndex - 1][0])}>Back</button>}
            {step !== 'review'
              ? <button className="primary" disabled={!canNext || loading} onClick={() => go(STEPS[stepIndex + 1][0])}>Next</button>
              : <button className="primary" disabled={!open || !count || loading} onClick={submit}>{mode === 'adddrop' ? 'Confirm change' : submitted ? 'Submit again' : 'Submit'}</button>}
          </div>
        </div>
      </div>
    </>
  );
}
