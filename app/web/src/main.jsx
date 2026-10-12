import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { resume, setCsrf } from './api.js';
import Student, { SignIn } from './Student.jsx';
import Admin from './Admin.jsx';
import './styles.css';

// Two areas in one page: "#/admin" is the protected admin area, everything else is the student flow.
function App() {
  const [session, setSession] = useState(undefined);       // undefined = still checking
  const [hash, setHash] = useState(window.location.hash);
  const check = () => resume().then((s) => setSession(s || {}));
  useEffect(() => {
    check();
    const onHash = () => setHash(window.location.hash);
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);
  if (session === undefined) return <main><p>Loading…</p></main>;
  if (hash.startsWith('#/admin')) return <Admin signedIn={!!session.admin} />;
  if (!session.student) {
    return (<>
      <header className="top"><h1>Course registration <span className="tag">beta</span></h1></header>
      <SignIn onDone={check} />
    </>);
  }
  return <Student onSignOut={() => { setCsrf(null); setSession({}); }} />;
}

createRoot(document.getElementById('root')).render(<App />);
