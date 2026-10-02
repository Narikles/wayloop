import { useState } from "react";
import { Copy } from "lucide-react";
import type { InterviewItem } from "../../api/types";
import { useAction, useApi, useToast } from "../../lib/ctx";
import { isoToLocalInput, localInputToIso } from "../../lib/format";
import { Button, Field, Modal } from "../../ui/kit";

export function CopyButton({ text, label = "Copier", size = "sm" }: { text: string; label?: string; size?: "sm" | "" }) {
  const notify = useToast();
  return (
    <button className={`btn ${size}`} type="button" onClick={async () => {
      try { await navigator.clipboard.writeText(text); notify("Lien copié"); } catch { notify("Copie impossible : sélectionnez le lien.", "bad"); }
    }}><Copy size={14} /> {label}</button>
  );
}

/** Date d'entretien convenue avec le candidat : il reçoit la confirmation et un rappel la veille. */
export function ScheduleModal({ iv, defaultLocation, onClose, onDone }: {
  iv: Pick<InterviewItem, "id" | "name" | "start" | "location">; defaultLocation?: string | null; onClose: () => void; onDone: () => void;
}) {
  const api = useApi();
  const run = useAction();
  const [when, setWhen] = useState(isoToLocalInput(iv.start));
  const [location, setLocation] = useState(iv.location || defaultLocation || "");
  return (
    <Modal title={iv.start ? `Modifier la date — ${iv.name}` : `Fixer la date — ${iv.name}`} onClose={onClose}
      sub="La personne reçoit la confirmation avec une invitation d'agenda, puis un rappel la veille."
      foot={<><button className="btn" onClick={onClose}>Annuler</button>
        <Button variant="primary" disabled={!when} onClick={async () => {
          const r = await run(() => api.schedule(iv.id, localInputToIso(when), location), "Date confirmée au candidat");
          if (r) onDone();
        }}>Confirmer la date</Button></>}>
      <Field label="Date et heure" htmlFor="iv-when"><input id="iv-when" className="input" type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} /></Field>
      <Field label="Lieu ou lien visio" htmlFor="iv-loc"><input id="iv-loc" className="input" value={location} onChange={(e) => setLocation(e.target.value)} /></Field>
    </Modal>
  );
}
