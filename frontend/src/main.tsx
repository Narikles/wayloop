import "./ui/styles.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { HttpApi, type Api } from "./api/client";
import { applyTheme, storedTheme } from "./lib/ctx";

declare const __DEMO__: boolean;

async function boot() {
  applyTheme(storedTheme()); // clair par défaut ; sombre si choisi dans les paramètres
  let api: Api = HttpApi;
  if (__DEMO__) {
    const { createDemoApi } = await import("./api/demo");
    api = createDemoApi();
  }
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <App api={api} />
    </StrictMode>,
  );
}
void boot();
