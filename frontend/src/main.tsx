import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { installGlobalErrorHandlers, logger } from "./lib/logger";
import "./index.css";

// #1741: install global error handlers + wrap the app in an ErrorBoundary so
// frontend crashes/rejections are logged and refluxed to the backend instead of
// disappearing into the DevTools console no beta tester opens.
installGlobalErrorHandlers();
logger.info("app starting");

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>,
);
