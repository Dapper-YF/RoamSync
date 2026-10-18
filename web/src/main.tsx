import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { DiscoveryApp } from "./discovery/DiscoveryApp";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <DiscoveryApp />
    </BrowserRouter>
  </StrictMode>,
);
