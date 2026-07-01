import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";
import { installGlobalFetchTimeout } from "@/lib/fetch-timeout";

// Must run before any page/module code issues a fetch() call.
installGlobalFetchTimeout();

createRoot(document.getElementById("root")!).render(<App />);
