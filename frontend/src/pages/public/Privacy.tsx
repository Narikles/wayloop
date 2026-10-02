import { useParams } from "react-router-dom";
import { useApi, useLoad } from "../../lib/ctx";
import { Card, ErrorBox, Spinner } from "../../ui/kit";
import PublicLayout from "./PublicLayout";

export default function Privacy() {
  const { slug = "" } = useParams();
  const api = useApi();
  const [p, err] = useLoad(() => api.privacy(slug), [slug]);
  return (
    <PublicLayout company={p?.company} slug={slug}>
      <ErrorBox msg={err} />
      {!p && !err && <Spinner />}
      {p && <Card title="Vos données personnelles"><div className="pre">{p.text}</div></Card>}
    </PublicLayout>
  );
}
