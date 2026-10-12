import React from 'react';

const DAYS = ['TUE', 'WED', 'THU', 'FRI', 'SAT'];
const DAY_START = 8 * 60;
const DAY_END = 19 * 60 + 10;
const LAB = new Set(['ELA', 'LO']);

export const clock = (m) => `${Math.floor(m / 60)}:${String(m % 60).padStart(2, '0')}`;

// Week grid for one combination. `classes` come from the API: {course, title, type, slot, cells}.
export default function Timetable({ classes }) {
  const span = DAY_END - DAY_START;
  const hours = [8, 10, 12, 14, 16, 18];
  return (
    <div>
      <div className="tt" aria-hidden="true">
        <div className="tt-hours">
          {hours.map((h) => (
            <span key={h} style={{ top: `${((h * 60 - DAY_START) / span) * 100}%` }}>{h}:00</span>
          ))}
        </div>
        {DAYS.map((d) => (
          <div className="tt-day" key={d}>
            <div className="tt-dayname">{d[0] + d.slice(1).toLowerCase()}</div>
            <div className="tt-col">
              {classes.flatMap((c) => c.cells.filter((x) => x[0] === d).map((x) => (
                <div
                  key={c.offering + x[1]}
                  className={`tt-block ${LAB.has(c.type) ? 'lab' : ''}`}
                  style={{ top: `${((x[1] - DAY_START) / span) * 100}%`, height: `${((x[2] - x[1]) / span) * 100}%` }}
                  title={`${c.course} ${c.title} ${clock(x[1])}-${clock(x[2])}`}
                >
                  {c.course.slice(3)}
                </div>
              )))}
            </div>
          </div>
        ))}
      </div>
      <table className="slots">
        <caption className="sr-only">Courses and slots in this timetable</caption>
        <tbody>
          {classes.map((c) => (
            <tr key={c.offering}>
              <th scope="row">{c.course}<span className="muted"> {LAB.has(c.type) ? 'lab' : 'theory'}</span></th>
              <td>{c.title}</td>
              <td className="nowrap">{c.slot}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
