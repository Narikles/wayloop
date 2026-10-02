import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { CalendarCheck, Clock, MapPin } from "lucide-react";
import type { Slot } from "../../api/types";
import { useAction, useApi, useLoad } from "../../lib/ctx";
import { fmtDateTime, fmtDay, fmtTime } from "../../lib/format";
import { Button, Card, ErrorBox, Notice, Spinner } from "../../ui/kit";
import PublicLayout from "./PublicLayout";

export default function Booking() {
  const { token = "" } = useParams();
  const api = useApi();
  const run = useAction();
  const [b, err, reload] = useLoad(() => api.booking(token), [token]);
  const [pick, setPick] = useState<string | null>(null);
  const [changing, setChanging] = useState(false);
  const [ask, setAsk] = useState(false);
  const byDay = useMemo(() => {
    const m = new Map<string, Slot[]>();
    for (const s of b?.slots || []) m.set(fmtDay(s.start), [...(m.get(fmtDay(s.start)) || []), s]);
    return [...m.entries()];
  }, [b]);
  const cancel = async () => { const ok = await run(() => api.cancelBooking(token).then(() => true), "L'entreprise est prévenue"); if (ok) { setAsk(false); await reload(); } };
  return (
    <PublicLayout company={b?.company}>
      <ErrorBox msg={err} />
      {!b && !err && <Spinner />}
      {b && <div className="stack lg" style={{ maxWidth: 640 }}>
        <div className="stack sm">
          <span className="eyebrow">Entretien · {b.title}</span>
          <h1>{b.status === "booked" && !changing ? "Votre entretien" : b.mode === "online" ? `${b.first_name ? `${b.first_name}, choisissez` : "Choisissez"} votre créneau` : "Votre entretien"}</h1>
          <div className="kv">
            <span><Clock size={15} /> Environ {b.minutes} minutes</span>
            {b.location && <span><MapPin size={15} /> {b.location}</span>}
          </div>
        </div>
        {b.closed ? <Notice>Cet entretien n'est plus d'actualité. Merci de votre intérêt.</Notice> : b.status === "booked" && !changing ? (
          <Card className="highlight" foot={ask ? <>
            <span className="small" style={{ marginRight: "auto" }}>Prévenir l'entreprise que vous ne pouvez pas venir ?</span>
            <button className="btn" onClick={() => setAsk(false)}>Non</button>
            <Button variant="primary" onClick={cancel}>Oui, prévenir</Button>
          </> : <>
            <button className="btn ghost" onClick={() => setAsk(true)}>Je ne peux pas venir</button>
            {b.mode === "online" && <Button onClick={() => setChanging(true)}>Changer de créneau</Button>}
          </>}>
            <CalendarCheck size={26} color="var(--ok)" />
            <h2 className="cap">{fmtDateTime(b.start)}</h2>
            <p className="muted">Rendez-vous confirmé. Vous recevrez un rappel la veille.</p>
          </Card>
        ) : b.mode === "manual" ? (
          <Card><p>{b.company} vous contacte pour convenir d'une date. Vous recevrez une confirmation par e-mail, puis un rappel la veille.</p></Card>
        ) : (
          <Card foot={<Button variant="primary" disabled={!pick} onClick={async () => { const ok = await run(() => api.book(token, pick!)); if (ok) { setChanging(false); setPick(null); await reload(); } }}>Confirmer ce créneau</Button>}>
            {byDay.length === 0 && <p>Plus aucun créneau libre : répondez à l'e-mail d'invitation, l'entreprise vous proposera une autre date.</p>}
            {byDay.map(([day, slots]) => (
              <div className="stack sm" key={day}>
                <b className="strong cap">{day}</b>
                <div className="slotgrid">{slots.map((s) => <button key={s.id} className={`btn ${pick === s.id ? "primary" : ""}`} onClick={() => setPick(s.id)} aria-pressed={pick === s.id}><span className="tnum">{fmtTime(s.start)}</span></button>)}</div>
              </div>
            ))}
          </Card>
        )}
      </div>}
    </PublicLayout>
  );
}
